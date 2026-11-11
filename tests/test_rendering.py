import json
import os
import subprocess
import tempfile
import unittest
from argparse import Namespace
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from sceneit import app, cut, export, run


class CutValidation(unittest.TestCase):
    def test_cuts_are_intersected_with_the_source_and_invalid_cuts_are_discarded(self):
        cuts = [
            {"t0": -2, "t1": 1, "scene": "start"},
            {"src": "0", "t0": 2.5, "t1": 5},
            {"t0": 12, "t1": 13}, {"t0": -5, "t1": -1},
            {"src": -1, "t0": 0, "t1": 1}, {"src": 1.5, "t0": 0, "t1": 1},
            {"src": "bad", "t0": 0, "t1": 1}, {"t0": "NaN", "t1": 1},
            {"t0": 0}, None,
        ]
        self.assertEqual(cut.clamp(cuts, [3]), [
            {"src": 0, "t0": 0, "t1": 1, "scene": "start"},
            {"src": 0, "t0": 2.5, "t1": 3},
        ])

    def test_missing_hdr_filters_fail_before_encoding(self):
        with patch.object(cut, "probe", return_value={"duration": 3, "hdr": True}), \
             patch.object(cut, "has_hdr_filters", return_value=False), \
             patch.object(cut.subprocess, "run") as ffmpeg:
            with self.assertRaisesRegex(RuntimeError, "zscale.*tonemap"):
                cut.render_cut(["hdr.mp4"], [{"t0": 0, "t1": 1}], "cut.mp4", "fit")
            ffmpeg.assert_not_called()


class ProjectRendering(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.work, self.studio = root / "work", root / "studio"
        stack.enter_context(patch.object(run, "WORK", self.work))
        stack.enter_context(patch.object(run, "STUDIO", self.studio))
        stack.enter_context(patch.object(app, "studio_up", return_value=False))
        (self.studio / "src" / "projects").mkdir(parents=True)

    def test_quote_safe_caption_and_style_values(self):
        source = self.studio / "source.mp4"
        source.write_bytes(b"source")
        subtitle = {'t0': 0, 't1': 4, 'text': '그가 "가자"라고 했다', 'font': 'bad"font', 'speed': 'nan'}
        export.write_project(self.studio, "sample", source, [subtitle], "fit", 1.5, 2)
        tsx = (self.studio / "src" / "projects" / "sample.tsx").read_text()
        for key, value in (("name", f"1 {subtitle['text']}"), ("text", subtitle["text"]), ("font", subtitle["font"])):
            self.assertIn(f"{key}={{{json.dumps(value, ensure_ascii=False)}}}", tsx)
        self.assertIn("durationInFrames={60}", tsx)
        self.assertIn("speed={1}", tsx)

    def test_new_projects_get_distinct_ids_and_existing_ids_are_preserved(self):
        args = Namespace(name="clip a", video=["fixture.mp4"], situation="test", layout="fit",
                         cut=None, style=None, rules=None, length=None, model="test")
        run.save({"name": args.name, "id": "clip-a"})
        with patch.object(run, "probe", return_value={"hdr": False}):
            old = run.cmd_new(args)
            args.name = "clip-a"
            new = run.cmd_new(args)
        self.assertEqual(old["id"], "clip-a")
        self.assertNotEqual(old["id"], new["id"])
        run.save({"name": "legacy collision", "id": "clip-a"})
        with self.assertRaisesRegex(ValueError, "편집 ID가 겹칩니다"):
            run.ensure_unique_id(old)

    def test_chat_can_create_a_project_using_the_same_stage_as_cli(self):
        source = self.work / "web" / "src" / "source.mp4"
        source.parent.mkdir(parents=True)
        source.touch()
        with patch.object(run, "probe", return_value={"width": 640, "height": 360, "hdr": False}), \
             patch.object(app, "start") as start:
            state = app.create({"name": "web", "files": [source.name], "situation": "test"})
        self.assertEqual((state["stage"], state["rev"]), ("cut", 0))
        self.assertEqual(state["chat"][0]["data"]["layout"], "fit")
        start.assert_called_once_with("web", app.job_cut)

    def test_failed_render_preserves_the_previous_mp4_and_stage(self):
        cfg = {"name": "render", "id": "render", "stage": "subs"}
        run.save(cfg)
        previous = self.work / "render" / "render.mp4"
        previous.write_bytes(b"previous render")

        def fail(command, **kwargs):
            Path(command[5]).write_bytes(b"incomplete render")
            raise subprocess.CalledProcessError(1, command)

        with patch.object(run.subprocess, "run", side_effect=fail):
            with self.assertRaises(subprocess.CalledProcessError):
                run.cmd_render(cfg)
        self.assertEqual(previous.read_bytes(), b"previous render")
        self.assertEqual(run.load("render")["stage"], "subs")
        self.assertEqual(list(previous.parent.glob(".render-*")), [])

    def test_legacy_cli_project_appears_at_the_stage_of_its_saved_files(self):
        cfg = {"name": "legacy", "id": "legacy", "cut_info": {"duration": 2}}
        run.save(cfg)
        folder = self.work / "legacy"
        source = run.studio_source(cfg)
        media = self.studio / "public" / "media" / "legacy.mp4"
        media.parent.mkdir(parents=True)
        files = [folder / "cut.mp4", folder / "subs.json", source, media, folder / "legacy.mp4"]
        for i, path in enumerate(files):
            path.touch()
            os.utime(path, (10 + i, 10 + i))
        self.assertEqual(app.projects()["projects"], [{"name": "legacy", "stage": "done"}])
        self.assertEqual(app.state("legacy")["rev"], 1)
        app.back("legacy")
        self.assertEqual(app.state("legacy")["stage"], "cut")
        with patch.object(app, "start") as start:
            self.assertEqual(app.confirm("legacy")["stage"], "subs")
            start.assert_not_called()

    def test_opening_legacy_cut_only_project_registers_its_preview(self):
        cfg = {"name": "legacy", "id": "legacy", "layout": "fit", "frame": "black",
               "cut_info": {"width": 640, "height": 360, "duration": 2}}
        run.save(cfg)
        (self.work / "legacy" / "cut.mp4").write_bytes(b"source")
        state = app.get_project("legacy")
        self.assertEqual((state["stage"], state["rev"]), ("cut", 1))
        tsx = run.studio_source(cfg)
        self.assertIn('bg="black"', tsx.read_text())
        tsx.write_text(tsx.read_text() + "\n// 사용자 편집\n")
        app.get_project("legacy")
        self.assertIn("// 사용자 편집", tsx.read_text())
