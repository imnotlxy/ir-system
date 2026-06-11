from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.search_engine import SearchEngine, default_search_index_path

ROOT = Path(__file__).resolve().parents[1]


class SearchEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._index_cache_dir = tempfile.TemporaryDirectory()
        cls.engine = SearchEngine(
            ROOT / "data",
            index_path=Path(cls._index_cache_dir.name) / "index.json",
        )
        cls.engine.load_data()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._index_cache_dir.cleanup()

    def _write_sample_data(self, root: Path) -> None:
        records = [
            {
                "schema_version": 2,
                "source": {
                    "college_id": 15,
                    "college_name": "计算机科学与技术学院",
                    "detail_url": "https://example.test/a",
                },
                "profile": {
                    "name": "陈伟",
                    "title": "教授",
                    "research_directions": "知识图谱 数据挖掘",
                    "representative_works": ["知识图谱论文"],
                },
                "text": {
                    "full_text": "陈伟教授研究知识图谱和数据挖掘",
                    "sections": [
                        {"heading": "个人简介", "paragraphs": ["长期从事知识图谱研究"]}
                    ],
                },
                "raw_api": {},
            },
            {
                "schema_version": 2,
                "source": {
                    "college_id": 85,
                    "college_name": "电子信息学院",
                    "detail_url": "https://example.test/b",
                },
                "profile": {
                    "name": "李明",
                    "title": "副教授",
                    "research_directions": "推荐系统",
                },
                "text": {"full_text": "李明研究推荐系统", "sections": []},
                "raw_api": {},
            },
        ]
        with (root / "teachers.jsonl").open("w", encoding="utf-8") as file:
            for record in records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def test_exact_teacher_name_ranks_first(self) -> None:
        results = self.engine.search("周国栋", top_k=3)

        self.assertTrue(results)
        self.assertEqual(results[0].record.name, "周国栋")

    def test_load_data_writes_search_index_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_sample_data(root)

            engine = SearchEngine(root)
            engine.load_data()

            cache_path = default_search_index_path(root)
            self.assertTrue(cache_path.exists())
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["source"], "teachers.jsonl")
            self.assertEqual(payload["record_count"], 2)
            self.assertIn("index", payload)
            self.assertIn("record_tokens", payload)
            self.assertEqual(engine.search("陈伟", top_k=1)[0].record.name, "陈伟")

    def test_load_data_reuses_valid_search_index_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_sample_data(root)

            first_engine = SearchEngine(root)
            first_engine.load_data()
            cache_path = default_search_index_path(root)
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            payload["index"]["cacheonly"] = [0]
            payload["doc_freq"]["cacheonly"] = 1
            payload["record_tokens"][0].append("cacheonly")
            payload["field_tokens"][0]["text"].append("cacheonly")
            payload["doc_lengths"][0] += 1
            payload["avg_dl"] = sum(payload["doc_lengths"]) / len(
                payload["doc_lengths"]
            )
            cache_path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )

            second_engine = SearchEngine(root)
            second_engine.load_data()
            results = second_engine.search("cacheonly", top_k=1)

            self.assertTrue(results)
            self.assertEqual(results[0].record.name, "陈伟")

    def test_name_field_single_character_search_finds_names(self) -> None:
        results = self.engine.search("周", search_field="name", top_k=20)
        names = {result.record.name for result in results}

        self.assertIn("周国栋", names)
        self.assertIn("周建康", names)

    def test_name_field_single_character_index_supports_middle_character(self) -> None:
        results = self.engine.search("建", search_field="name", top_k=20)
        names = {result.record.name for result in results}

        self.assertIn("莫建华", names)
        self.assertIn("周建康", names)


if __name__ == "__main__":
    _ = unittest.main()
