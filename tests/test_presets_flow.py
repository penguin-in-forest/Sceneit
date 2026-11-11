"""presets.after_plan / after_subs 흐름: 검사 → (걸리면) 같은 대화로 한 번 더 묻기 → 더 나은 쪽 선택. Claude 호출은 가짜로 바꾼다."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sceneit import presets


def cfg_for(preset, w):
    pre = presets.load(preset)
    return {"name": "t", "model": "m", "length": pre["length"], "cut": pre["cut"], "checks": pre["checks"], "cost": {}, "cut_info": {"duration": 30.0}, "_w": w}


class PlanFlow(unittest.TestCase):
    def setUp(self):
        self.w = Path(tempfile.mkdtemp())
        (self.w / "plan").mkdir()
        (self.w / "scenes.json").write_text(json.dumps({"0": []}))

    def test_one_take_is_retried_in_same_session(self):
        cfg = cfg_for("roblox_ko", self.w)
        bad = {"cuts": [{"src": 0, "t0": 0, "t1": 25}]}
        good = {"cuts": [{"src": 0, "t0": 0, "t1": 12}, {"src": 0, "t0": 40, "t1": 52}]}
        calls = []

        def fake(prompt, cwd, model, tries=3, resume=None):
            calls.append((prompt, resume))
            return json.loads(json.dumps(good)), {"cost": 1.5, "seconds": 3, "session": "s1"}

        with mock.patch.object(presets.ai, "ask", side_effect=fake):
            plan, meta = presets.after_plan(cfg, bad, {"cost": 1.0, "seconds": 9, "session": "s1"}, "PROMPT", self.w / "plan", [100.0])
        self.assertEqual(len(calls), 1)
        prompt, resume = calls[0]
        self.assertEqual(resume, "s1")  # 같은 대화를 이어 간다
        self.assertNotIn("PROMPT", prompt)  # 처음 프롬프트(시트 목록)를 다시 보내지 않는다
        self.assertIn("원테이크", prompt)
        self.assertEqual(len(plan["cuts"]), 2)
        self.assertEqual(plan["checks"]["problems"], [])
        self.assertTrue(plan["checks"]["retried"])
        self.assertEqual(meta["cost"], 1.5)  # 같은 대화면 claude -p가 준 누적 비용 그대로

    def test_new_session_adds_cost_and_keeps_better(self):
        cfg = cfg_for("roblox_ko", self.w)
        bad = {"cuts": [{"src": 0, "t0": 0, "t1": 25}]}
        worse = {"cuts": [{"src": 0, "t0": 0, "t1": 50}]}  # 길이까지 어김 → 처음 것을 유지

        def fake(prompt, cwd, model, tries=3, resume=None):
            self.assertIsNone(resume)
            self.assertIn("PROMPT", prompt)  # 대화 id가 없으면 처음 프롬프트에 붙여 새로 묻는다
            return worse, {"cost": 0.7, "seconds": 3, "session": "s2"}

        with mock.patch.object(presets.ai, "ask", side_effect=fake):
            plan, meta = presets.after_plan(cfg, bad, {"cost": 1.0, "seconds": 9}, "PROMPT", self.w / "plan", [100.0])
        self.assertEqual(plan["cuts"], bad["cuts"])
        self.assertEqual(meta["cost"], 1.7)

    def test_failed_retry_keeps_first(self):
        cfg = cfg_for("roblox_ko", self.w)
        bad = {"cuts": [{"src": 0, "t0": 0, "t1": 25}]}
        with mock.patch.object(presets.ai, "ask", side_effect=RuntimeError("boom")):
            plan, meta = presets.after_plan(cfg, bad, {"cost": 1.0, "session": "s1"}, "PROMPT", self.w / "plan", [100.0])
        self.assertEqual(plan["cuts"], bad["cuts"])
        self.assertEqual(meta["cost"], 1.0)

    def test_no_preset_no_checks(self):
        plan, meta = presets.after_plan({"checks": {}}, {"cuts": []}, {"cost": 1}, "P", self.w / "plan", [])
        self.assertNotIn("checks", plan)

    def test_malformed_retry_keeps_the_original_cuts(self):
        cfg = cfg_for("roblox_ko", self.w)
        original = {"cuts": [{"src": 0, "t0": 0, "t1": 25}]}
        retry = {"cuts": [None, {"src": "bad", "t0": 0, "t1": 1}]}
        with mock.patch.object(presets.ai, "ask", return_value=(retry, {"cost": 1.5, "session": "s1"})):
            plan, _ = presets.after_plan(cfg, original, {"cost": 1.0, "session": "s1"}, "P", self.w / "plan", [100.0])
        self.assertEqual(plan["cuts"], original["cuts"])


class SubsFlow(unittest.TestCase):
    def setUp(self):
        self.w = Path(tempfile.mkdtemp())
        (self.w / "subs").mkdir()

    def test_low_coverage_retried_and_caption_saved(self):
        cfg = cfg_for("roblox_ko", self.w)
        tc = {"대상": "로블록스", "상황": "밟아봄", "이유": "공감"}
        thin = {"subs": [{"t0": 0, "t1": 30, "role": "title", "text": "제목"}, {"t0": 1, "t1": 3, "role": "body", "text": "a"}], "title_check": tc}
        full = {"subs": [{"t0": 0, "t1": 30, "role": "title", "text": "제목"}] + [{"t0": i * 3.0, "t1": i * 3.0 + 2.5, "role": "body", "text": "b"} for i in range(10)],
                "title_check": tc, "caption": "캡션\n#로블록스 #roblox"}

        with mock.patch.object(presets.ai, "ask", return_value=(full, {"cost": 0.9, "seconds": 2, "session": "s9"})):
            subs, meta = presets.after_subs(cfg, thin, {"cost": 0.5, "session": "s9"}, "PROMPT", self.w / "subs")
        self.assertEqual(len(subs["subs"]), 11)
        self.assertGreaterEqual(subs["checks"]["metrics"]["coverage"], 0.75)
        self.assertEqual(subs["checks"]["problems"], [])
        self.assertEqual((self.w / "caption.txt").read_text(), "캡션\n#로블록스 #roblox\n")
        self.assertEqual(meta["session"], "s9")

    def test_english_has_no_subtitle_checks(self):
        cfg = cfg_for("roblox_en", self.w)
        data = {"subs": [{"t0": 0, "t1": 30, "role": "title", "text": "pov"}]}
        with mock.patch.object(presets.ai, "ask", side_effect=AssertionError("should not be called")):
            subs, _ = presets.after_subs(cfg, data, {"cost": 0.5}, "PROMPT", self.w / "subs")
        self.assertNotIn("checks", subs)

    def test_malformed_retry_keeps_the_original_subtitles(self):
        cfg = cfg_for("roblox_ko", self.w)
        original = {"subs": [{"t0": 0, "t1": 2, "text": "본문"}]}
        retry = {"subs": [{"t0": 0, "t1": "NaN", "text": "잘못된 시간"}]}
        with mock.patch.object(presets.ai, "ask", return_value=(retry, {"cost": 1.0, "session": "s1"})):
            subs, _ = presets.after_subs(cfg, original, {"cost": 0.5, "session": "s1"}, "P", self.w / "subs")
        self.assertEqual(subs["subs"], original["subs"])


if __name__ == "__main__":
    unittest.main()
