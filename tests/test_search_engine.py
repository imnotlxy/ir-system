from __future__ import annotations

import unittest
from pathlib import Path

from backend.search_engine import SearchEngine


ROOT = Path(__file__).resolve().parents[1]


class SearchEngineTest(unittest.TestCase):
    def test_exact_teacher_name_ranks_first(self) -> None:
        engine = SearchEngine(ROOT / "data")
        engine.load_data()

        results = engine.search("周国栋", top_k=3)

        self.assertTrue(results)
        self.assertEqual(results[0].record.name, "周国栋")


if __name__ == "__main__":
    _ = unittest.main()
