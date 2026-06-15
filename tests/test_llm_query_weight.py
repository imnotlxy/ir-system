from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.llm_query_weight import (
    LlmQueryWeightError,
    _parse_weights_response,
    compute_query_weights,
)
from backend.search_engine import SearchEngine


class ParseWeightsResponseTest(unittest.TestCase):
    def test_valid_response(self) -> None:
        response = '{"weights": {"自然语言": 2.0, "处理": 1.5, "教授": 0.5}}'
        tokens = ["自然语言", "处理", "教授"]
        weights = _parse_weights_response(response, tokens)
        self.assertEqual(weights, {"自然语言": 2.0, "处理": 1.5, "教授": 0.5})

    def test_missing_token_defaults_to_one(self) -> None:
        response = '{"weights": {"自然语言": 2.0}}'
        tokens = ["自然语言", "处理"]
        weights = _parse_weights_response(response, tokens)
        self.assertEqual(weights["自然语言"], 2.0)
        self.assertEqual(weights["处理"], 1.0)

    def test_weights_clamped_to_range(self) -> None:
        response = '{"weights": {"a": 10.0, "b": -1.0}}'
        tokens = ["a", "b"]
        weights = _parse_weights_response(response, tokens)
        self.assertEqual(weights["a"], 3.0)
        self.assertEqual(weights["b"], 0.1)

    def test_no_json_raises(self) -> None:
        with self.assertRaises(ValueError):
            _parse_weights_response("no json here", ["a"])

    def test_missing_weights_key_raises(self) -> None:
        with self.assertRaises(ValueError):
            _parse_weights_response('{"ranking": [1]}', ["a"])

    def test_non_numeric_weight_defaults_to_one(self) -> None:
        response = '{"weights": {"a": "high"}}'
        tokens = ["a"]
        weights = _parse_weights_response(response, tokens)
        self.assertEqual(weights["a"], 1.0)


class ComputeQueryWeightsTest(unittest.TestCase):
    def test_empty_tokens_returns_empty(self) -> None:
        result = compute_query_weights("test", [])
        self.assertEqual(result, {})

    def test_missing_api_key_raises(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(LlmQueryWeightError):
                compute_query_weights("test", ["a", "b"])


class SearchEngineWeightedScoringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        root = Path(cls._tmpdir.name)
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
                },
                "text": {
                    "full_text": "陈伟教授研究知识图谱和数据挖掘",
                    "sections": [],
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
                    "research_directions": "推荐系统 数据挖掘",
                },
                "text": {
                    "full_text": "李明研究推荐系统和数据挖掘",
                    "sections": [],
                },
                "raw_api": {},
            },
        ]
        with (root / "teachers.jsonl").open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        cls.engine = SearchEngine(root)
        cls.engine.load_data()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmpdir.cleanup()

    def test_token_weights_affect_ranking(self) -> None:
        """Boosting '知识' should push the knowledge-graph teacher higher."""
        baseline = self.engine.search("数据挖掘 知识图谱")
        weighted = self.engine.search(
            "数据挖掘 知识图谱",
            token_weights={"知识图谱": 3.0, "知识": 3.0, "图谱": 3.0, "数据": 0.3, "挖掘": 0.3, "数据挖掘": 0.3},
        )

        self.assertTrue(weighted)
        self.assertEqual(weighted[0].record.name, "陈伟")

        weighted_score = weighted[0].score
        baseline_chen = next(
            (r for r in baseline if r.record.name == "陈伟"), None
        )
        self.assertIsNotNone(baseline_chen)
        self.assertGreater(weighted_score, baseline_chen.score)

    def test_none_token_weights_is_same_as_baseline(self) -> None:
        baseline = self.engine.search("数据挖掘")
        weighted = self.engine.search("数据挖掘", token_weights=None)
        self.assertEqual(len(baseline), len(weighted))
        for b, w in zip(baseline, weighted):
            self.assertAlmostEqual(b.score, w.score)


if __name__ == "__main__":
    _ = unittest.main()
