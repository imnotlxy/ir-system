from __future__ import annotations

import unittest
from pathlib import Path

from crawler.suda_teachers import parse_teacher_page


ROOT = Path(__file__).resolve().parents[1]


class SudaTeacherParserTest(unittest.TestCase):
    def test_parses_legacy_teacher_homepage(self) -> None:
        raw_path = ROOT / "data/raw_pages/15_13800_周国栋.html"
        raw_teacher = {
            "title": "周国栋",
            "career": "",
            "collegeId": 15,
            "collegeName": "计算机科学与技术学院（软件学院）",
            "columnId": 13800,
        }

        parsed = parse_teacher_page(
            "http://web.suda.edu.cn/gdzhou",
            raw_path.read_bytes(),
            raw_path.relative_to(ROOT),
            raw_teacher,
        )

        profile = parsed["profile"]
        self.assertEqual(profile["phone"], "0512-65214851 (办公室)")
        self.assertEqual(profile["email"], "gdzhou@suda.edu.cn")
        self.assertEqual(profile["title"], "特聘教授，博士生导师")
        self.assertEqual(profile["research_directions"], "自然语言处理、信息抽取、统计机器翻译、机器学习等")
        self.assertGreaterEqual(len(profile["representative_works"]), 5)
        self.assertGreaterEqual(len(parsed["text"]["sections"]), 5)

    def test_still_parses_structured_teacher_homepage(self) -> None:
        raw_path = ROOT / "data/raw_pages/15_23029_陈伟.html"
        raw_teacher = {
            "title": "陈伟",
            "career": "副教授",
            "collegeId": 15,
            "collegeName": "计算机科学与技术学院（软件学院）",
            "columnId": 23029,
        }

        parsed = parse_teacher_page(
            "http://web.suda.edu.cn/robertchen",
            raw_path.read_bytes(),
            raw_path.relative_to(ROOT),
            raw_teacher,
        )

        profile = parsed["profile"]
        self.assertEqual(profile["email"], "robertchen@suda.edu.cn")
        self.assertEqual(profile["title"], "副教授")
        self.assertIn("知识图谱", profile["research_directions"])
        self.assertTrue(parsed["text"]["sections"])


if __name__ == "__main__":
    _ = unittest.main()
