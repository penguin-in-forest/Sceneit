import unittest

from sceneit.checks import check_cuts, check_subs, close_gaps, parse_length, roles, transitions
from sceneit.presets import load, names

KO = load("roblox_ko")["checks"]
EN = load("roblox_en")["checks"]


def cut(src, t0, t1):
    return {"src": src, "t0": t0, "t1": t1}


def sub(t0, t1, role=None, size=1.0, text="자막"):
    s = {"t0": t0, "t1": t1, "text": text, "size": size}
    if role:
        s["role"] = role
    return s


class Length(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_length("20~30"), (20.0, 30.0))
        self.assertEqual(parse_length("45-60"), (45.0, 60.0))
        self.assertEqual(parse_length(""), None)


class Transitions(unittest.TestCase):
    def test_contiguous_cuts_are_one_scene(self):
        trans, total = transitions([cut(0, 0, 10), cut(0, 10, 20)], {})
        self.assertEqual((trans, total), ([], 20))

    def test_jump_and_source_scene_change(self):
        # 0~10초 컷(원본 5초에 장면 전환) + 30~40초 컷 → 완성본 5초, 10초에 전환
        trans, total = transitions([cut(0, 0, 10), cut(0, 30, 40)], {0: [5.0, 9.9, 35.0]})
        self.assertEqual(total, 20)
        self.assertEqual(trans, [5.0, 10.0, 15.0])  # 9.9는 컷 경계에 붙어 있어서 뺀다


class Rhythm(unittest.TestCase):
    def test_one_take_fails(self):
        problems, m = check_cuts([cut(0, 0, 25)], {}, "20~30", KO)
        self.assertEqual(m["transitions"], 0)
        self.assertTrue(any("원테이크" in p for p in problems))
        self.assertTrue(any("25.0초 동안" in p for p in problems))

    def test_every_12s_passes(self):
        problems, m = check_cuts([cut(0, 0, 12), cut(0, 40, 52)], {}, "20~30", KO)
        self.assertEqual(problems, [])
        self.assertEqual(m["transitions"], 1)

    def test_too_fast_fails(self):
        cuts = [cut(0, i * 10, i * 10 + 2) for i in range(12)]  # 2초 컷 12개
        problems, m = check_cuts(cuts, {}, "20~30", KO)
        self.assertTrue(any("10초에 3번 이하" in p for p in problems))

    def test_length(self):
        problems, _ = check_cuts([cut(0, 0, 12), cut(0, 40, 52), cut(0, 80, 92)], {}, "20~30", KO)
        self.assertTrue(any("36.0초" in p for p in problems))
        problems, _ = check_cuts([cut(0, 0, 50)], {}, "45~60", EN)
        self.assertEqual(problems, [])  # 영어는 리듬 검사가 없다


class Subs(unittest.TestCase):
    def test_roles_inferred(self):
        subs = [sub(0, 30, size=1.8), sub(1, 3), sub(4, 5, size=0.7)]
        self.assertEqual(roles(subs, 30), ["title", "body", "reaction"])

    def test_coverage_and_holes(self):
        data = {"subs": [sub(0, 30, "title"), sub(0.5, 10, "body"), sub(18, 30, "body")], "title_check": {"대상": "로블록스", "상황": "만남", "이유": "웃음"}}
        problems, m = check_subs(data, 30, KO)
        self.assertAlmostEqual(m["coverage"], 0.717, places=3)
        self.assertEqual(m["holes"], [[10.0, 18.0]])
        self.assertEqual(len(problems), 2)

    def test_showcase_skips_coverage(self):
        data = {"showcase": True, "subs": [sub(0, 30, "title")], "title_check": {"대상": "a", "상황": "b", "이유": "c"}}
        self.assertEqual(check_subs(data, 30, KO)[0], [])

    def test_title_check_required(self):
        data = {"subs": [sub(0, 30, "title"), sub(0, 30, "body")]}
        problems, _ = check_subs(data, 30, KO)
        self.assertTrue(any("title_check" in p for p in problems))
        self.assertEqual(check_subs(data, 30, EN)[0], [])  # 영어는 명확도 효과가 없어서 검사하지 않는다

    def test_close_small_gaps(self):
        subs = [sub(0, 30, "title"), sub(0, 2, "body"), sub(2.8, 5, "body"), sub(9, 29.5, "body")]
        self.assertEqual(close_gaps(subs, 30, 1.0), 2)
        self.assertEqual(subs[1]["t1"], 2.8)  # 0.8초 빈틈은 메움
        self.assertEqual(subs[2]["t1"], 5)  # 4초 빈틈은 그대로
        self.assertEqual(subs[3]["t1"], 30)  # 끝의 0.5초도 메움


class Presets(unittest.TestCase):
    def test_names_and_files(self):
        self.assertIn("roblox_ko", names())
        self.assertIn("roblox_en", names())
        ko = load("roblox_ko")
        self.assertEqual((ko["length"], ko["cut"], ko["frame"]), ("20~30", "rhythm", "black"))
        self.assertTrue(ko["style"].endswith("style.md"))


if __name__ == "__main__":
    unittest.main()
