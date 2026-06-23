"""Benchmark for related-teacher retrieval: Hit@1 / Hit@5.

用例存放在 ``bench/related_cases.json``。每条用例给出一个源教师，以及一个或
多个领域上可接受的相近教师。由于“相近教师”没有唯一标准答案，只要结果命中
任一期望教师，即计为命中。

用法::

    uv run python -m bench.related_benchmark
    uv run python -m bench.related_benchmark --strict
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from backend.search_engine import RelatedTeacherResult, SearchEngine, TeacherRecord

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CASES_PATH = Path(__file__).resolve().parent / "related_cases.json"


@dataclass
class RelatedCase:
    id: str
    source: dict
    expected: list[dict]
    note: str


@dataclass
class RelatedRow:
    case: RelatedCase
    source_record: TeacherRecord
    results: list[RelatedTeacherResult]
    rank1: int | None
    rank5: int | None


def load_cases(path: Path = CASES_PATH) -> list[RelatedCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        RelatedCase(
            id=str(c["id"]),
            source=dict(c["source"]),
            expected=list(c.get("expected", [])),
            note=str(c.get("note", "")),
        )
        for c in payload["cases"]
    ]


def _matches(record: TeacherRecord, expected_entries: list[dict]) -> bool:
    for entry in expected_entries:
        if record.name != entry["name"]:
            continue
        college = entry.get("college")
        if college and record.college != college:
            continue
        return True
    return False


def _hit_rank(
    results: list[RelatedTeacherResult], expected_entries: list[dict], k: int
) -> int | None:
    for i, result in enumerate(results[:k]):
        if _matches(result.record, expected_entries):
            return i + 1
    return None


def _find_source_record(engine: SearchEngine, source: dict) -> TeacherRecord:
    name = str(source.get("name", ""))
    college = str(source.get("college", ""))
    detail_url = str(source.get("detail_url", ""))

    for record in engine.records:
        if detail_url and record.detail_url == detail_url:
            return record

    name_matches = [record for record in engine.records if record.name == name]
    if college:
        for record in name_matches:
            if record.college == college:
                return record
    if len(name_matches) == 1:
        return name_matches[0]

    if not name_matches:
        raise ValueError(f"source teacher not found: {source}")
    raise ValueError(f"source teacher is ambiguous, add college/detail_url: {source}")


def _expected_label(expected: list[dict]) -> str:
    return "/".join(entry["name"] for entry in expected)


def _reason_label(result: RelatedTeacherResult | None) -> str:
    if result is None:
        return "-"
    return "；".join(result.reasons[:3]) or "-"


def run_cases(
    engine: SearchEngine, cases: list[RelatedCase], fetch_k: int
) -> list[RelatedRow]:
    rows: list[RelatedRow] = []
    for case in cases:
        source_record = _find_source_record(engine, case.source)
        results = engine.related_teachers(
            {"detail_url": source_record.detail_url},
            top_k=fetch_k,
        )
        rows.append(
            RelatedRow(
                case=case,
                source_record=source_record,
                results=results,
                rank1=_hit_rank(results, case.expected, 1),
                rank5=_hit_rank(results, case.expected, 5),
            )
        )
    return rows


def _print_report(rows: list[RelatedRow]) -> None:
    print("\n相近教师 benchmark  (Hit@1 / Hit@5)")
    print("ID | 源教师 | 期望相近教师 | Top-1 | Hit@1 | Hit@5 | 命中排名 | Top-1 依据 | 说明")
    hit1 = hit5 = 0
    for row in rows:
        h1 = row.rank1 is not None
        h5 = row.rank5 is not None
        hit1 += int(h1)
        hit5 += int(h5)
        top1 = row.results[0] if row.results else None
        top1_name = top1.record.name if top1 else "-"
        rank_str = str(row.rank5) if row.rank5 is not None else "-"
        print(
            f"{row.case.id} | {row.source_record.name} | "
            f"{_expected_label(row.case.expected)} | {top1_name} | "
            f"{'Y' if h1 else 'N'} | {'Y' if h5 else 'N'} | {rank_str} | "
            f"{_reason_label(top1)} | {row.case.note}"
        )

    n = len(rows)
    print(f"汇总 related: Hit@1={hit1}/{n} ({100 * hit1 / n:.0f}%)  "
          f"Hit@5={hit5}/{n} ({100 * hit5 / n:.0f}%)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run related-teacher benchmark (Hit@1 / Hit@5)."
    )
    parser.add_argument("--strict", action="store_true", help="有用例未进 Hit@5 时以非零码退出")
    args = parser.parse_args(argv)

    cases = load_cases()
    with tempfile.TemporaryDirectory() as tmp:
        engine = SearchEngine(DATA_DIR, index_path=Path(tmp) / "index.json")
        engine.load_data()
        rows = run_cases(engine, cases, fetch_k=5)

    _print_report(rows)
    all_hit = all(row.rank5 is not None for row in rows)
    return 1 if args.strict and not all_hit else 0


if __name__ == "__main__":
    sys.exit(main())
