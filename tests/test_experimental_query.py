from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.experimental_query import ExperimentalQueryIndex, write_index


class ExperimentalQueryTest(unittest.TestCase):
    def _build_sample_index(self, root: Path) -> Path:
        teachers_dir = root / "teachers_by_college"
        teachers_dir.mkdir(parents=True)
        records = [
            {
                "schema_version": 2,
                "source": {
                    "college_id": 15,
                    "college_name": "计算机科学与技术学院",
                    "teacher_id": 1,
                },
                "profile": {
                    "name": "陈伟",
                    "research_directions": "知识图谱 时空数据分析",
                },
                "text": {"full_text": "陈伟研究知识图谱和时空数据分析"},
                "raw_api": {"collegeId": 15, "title": "陈伟"},
            },
            {
                "schema_version": 2,
                "source": {
                    "college_id": 85,
                    "college_name": "电子信息学院",
                    "teacher_id": 2,
                },
                "profile": {"name": "李明", "research_directions": "推荐系统"},
                "text": {"full_text": "李明研究推荐系统"},
                "raw_api": {"collegeId": 85, "title": "李明"},
            },
        ]
        with (teachers_dir / "sample.jsonl").open("w", encoding="utf-8") as file:
            for record in records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
        return write_index(root)

    def test_keywords_are_or_connected_and_body_fields_are_removed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index_path = self._build_sample_index(root)
            query_index = ExperimentalQueryIndex(index_path=index_path)

            response = query_index.query(
                {"name": None, "collegeId": None, "keywords": ["图谱", "推荐"]}
            )

            self.assertEqual(len(response["results"]), 2)
            self.assertEqual(
                {item["profile"]["name"] for item in response["results"]},
                {"陈伟", "李明"},
            )
            self.assertNotIn("text", response["results"][0])
            self.assertNotIn("detail_fields", response["results"][0])

    def test_name_and_college_id_filter_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index_path = self._build_sample_index(root)
            query_index = ExperimentalQueryIndex(index_path=index_path)

            response = query_index.query(
                {"name": "陈", "collegeId": 15, "keywords": ["推荐", "图谱"]}
            )

            self.assertEqual(len(response["results"]), 1)
            self.assertEqual(response["results"][0]["profile"]["name"], "陈伟")

    def test_name_filter_supports_full_pinyin_and_initials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index_path = self._build_sample_index(root)
            query_index = ExperimentalQueryIndex(index_path=index_path)

            full_pinyin_response = query_index.query(
                {"name": "chenwei", "collegeId": None, "keywords": []}
            )
            initials_response = query_index.query(
                {"name": "cw", "collegeId": None, "keywords": []}
            )

            self.assertEqual(len(full_pinyin_response["results"]), 1)
            self.assertEqual(
                full_pinyin_response["results"][0]["profile"]["name"], "陈伟"
            )
            self.assertEqual(len(initials_response["results"]), 1)
            self.assertEqual(initials_response["results"][0]["profile"]["name"], "陈伟")


if __name__ == "__main__":
    _ = unittest.main()
