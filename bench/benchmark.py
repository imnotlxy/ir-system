"""Benchmark for the IR retrieval system: Hit@1 / Hit@5 over a case set.

用例存放在 ``bench/cases.json``，每条用例给出查询与期望命中的教师。本程序
直接调用 ``SearchEngine``（无需启动后端），按不同配置跑全部用例，统计 Hit@1、
Hit@5，用于逐项评价高级版的各项优化（模糊查询、拼音查询、同义词扩展、LLM
查询加权、LLM 重排）。

每个配置尽量只打开一项优化，以便观察其单独的边际贡献；``advanced`` 为前三项
组合，``llm-*`` 在 advanced 基础上叠加 LLM 优化。

用法::

    uv run python -m bench.benchmark              # 跑全部确定性配置并对比
    uv run python -m bench.benchmark --include-llm  # 额外跑 LLM 配置（需 DEEPSEEK_API_KEY）
    uv run python -m bench.benchmark --config pinyin
    uv run python -m bench.benchmark --ranking tfidf
    uv run python -m bench.benchmark --strict     # 有用例未进 Hit@5 则返回非零
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from backend.search_engine import SearchEngine, SearchResult

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CASES_PATH = Path(__file__).resolve().parent / "cases.json"

ADVANCED_SEARCH = {
    "auto_relax": True,
    "pinyin_query": True,
    "use_synonyms": True,
}


@dataclass
class Config:
    name: str
    label: str
    search: dict[str, object] = field(default_factory=dict)
    llm_query_weight: bool = False
    llm_rerank: bool = False

    @property
    def requires_llm(self) -> bool:
        return self.llm_query_weight or self.llm_rerank


CONFIGS: dict[str, Config] = {
    "baseline": Config("baseline", "基线（精确匹配）"),
    "fuzzy": Config("fuzzy", "模糊查询（自动放宽）", search={"auto_relax": True}),
    "pinyin": Config("pinyin", "拼音姓名查询", search={"pinyin_query": True}),
    "synonym": Config("synonym", "同义词扩展", search={"use_synonyms": True}),
    "advanced": Config("advanced", "高级版前三项组合", search=dict(ADVANCED_SEARCH)),
    "llm-weight": Config(
        "llm-weight", "advanced + LLM 查询加权",
        search=dict(ADVANCED_SEARCH), llm_query_weight=True,
    ),
    "llm-rerank": Config(
        "llm-rerank", "advanced + LLM 重排",
        search=dict(ADVANCED_SEARCH), llm_rerank=True,
    ),
    "llm-all": Config(
        "llm-all", "advanced + LLM 加权 + LLM 重排",
        search=dict(ADVANCED_SEARCH), llm_query_weight=True, llm_rerank=True,
    ),
}


@dataclass
class Case:
    id: str
    query: str
    expected: list[dict]
    note: str


@dataclass
class Row:
    case: Case
    results: list[SearchResult]
    rank1: int | None
    rank5: int | None
    detail: str = ""


def load_cases(path: Path = CASES_PATH) -> list[Case]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        Case(
            id=str(c["id"]),
            query=str(c["query"]),
            expected=list(c.get("expected", [])),
            note=str(c.get("note", "")),
        )
        for c in payload["cases"]
    ]


def _matches(record, expected_entries: list[dict]) -> bool:
    for entry in expected_entries:
        if record.name != entry["name"]:
            continue
        college = entry.get("college")
        if college and record.college != college:
            continue
        return True
    return False


def _hit_rank(results: list[SearchResult], expected_entries: list[dict], k: int) -> int | None:
    for i, result in enumerate(results[:k]):
        if _matches(result.record, expected_entries):
            return i + 1
    return None


def _expected_label(expected: list[dict]) -> str:
    return "/".join(entry["name"] for entry in expected)


def _llm_available() -> bool:
    return bool(os.environ.get("DEEPSEEK_API_KEY", ""))


def _run_case(
    engine: SearchEngine, case: Case, config: Config, ranking: str, fetch_k: int
) -> Row:
    token_weights: dict[str, float] | None = None
    detail = ""

    if config.llm_query_weight:
        from backend.llm_query_weight import LlmQueryWeightError, compute_query_weights

        try:
            tokens = engine._tokenize(case.query)
            token_weights = compute_query_weights(case.query, tokens)
        except LlmQueryWeightError as exc:
            detail = f"加权失败回退：{exc}"

    results = engine.search(
        case.query, ranking=ranking, top_k=fetch_k, token_weights=token_weights,
        **config.search,
    )

    if config.llm_rerank and results:
        from backend.llm_rerank import LlmRerankError, rerank

        try:
            results = rerank(case.query, results)
        except LlmRerankError as exc:
            detail = (detail + " " if detail else "") + f"重排失败回退：{exc}"

    return Row(
        case=case,
        results=results,
        rank1=_hit_rank(results, case.expected, 1),
        rank5=_hit_rank(results, case.expected, 5),
        detail=detail,
    )


def run_config(
    engine: SearchEngine, cases: list[Case], config: Config, ranking: str, fetch_k: int
) -> list[Row]:
    return [_run_case(engine, case, config, ranking, fetch_k) for case in cases]


def _print_report(config: Config, ranking: str, rows: list[Row]) -> None:
    print(f"\n配置: {config.name} — {config.label}  (ranking={ranking})")
    print("ID | 查询 | 期望 | Top-1 | Hit@1 | Hit@5 | 命中排名 | 匹配模式 | 说明")
    hit1 = hit5 = 0
    for row in rows:
        h1 = row.rank1 is not None
        h5 = row.rank5 is not None
        hit1 += int(h1)
        hit5 += int(h5)
        top1 = row.results[0].record.name if row.results else "-"
        mode = row.results[0].match_mode if row.results else "-"
        rank_str = str(row.rank5) if row.rank5 is not None else "-"
        note = row.case.note + (f"  [{row.detail}]" if row.detail else "")
        print(
            f"{row.case.id} | {row.case.query} | {_expected_label(row.case.expected)} | "
            f"{top1} | {'Y' if h1 else 'N'} | {'Y' if h5 else 'N'} | "
            f"{rank_str} | {mode} | {note}"
        )
    n = len(rows)
    print(
        f"汇总 {config.name}: Hit@1={hit1}/{n} ({100 * hit1 / n:.0f}%)  "
        f"Hit@5={hit5}/{n} ({100 * hit5 / n:.0f}%)"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run IR retrieval benchmark (Hit@1 / Hit@5).")
    parser.add_argument("--config", choices=list(CONFIGS), help="只跑单个配置")
    parser.add_argument(
        "--include-llm", action="store_true",
        help="额外跑 LLM 配置（llm-weight / llm-rerank / llm-all），需设置 DEEPSEEK_API_KEY",
    )
    parser.add_argument("--ranking", default="bm25", choices=["bm25", "tfidf"])
    parser.add_argument("--top-k", type=int, default=5, help="每个用例取回的最大结果数")
    parser.add_argument("--strict", action="store_true", help="有用例未进 Hit@5 时以非零码退出")
    args = parser.parse_args(argv)

    fetch_k = max(args.top_k, 20)  # rerank 需要 enough 候选
    if args.config:
        selected = [CONFIGS[args.config]]
    else:
        selected = [
            cfg for cfg in CONFIGS.values()
            if not cfg.requires_llm or args.include_llm
        ]

    llm_ready = _llm_available()
    cases = load_cases()
    all_hit = True

    with tempfile.TemporaryDirectory() as tmp:
        engine = SearchEngine(DATA_DIR, index_path=Path(tmp) / "index.json")
        engine.load_data()
        for config in selected:
            if config.requires_llm and not llm_ready:
                print(f"\n配置: {config.name} — {config.label}  跳过（未设置 DEEPSEEK_API_KEY）")
                all_hit = False
                continue
            rows = run_config(engine, cases, config, args.ranking, fetch_k)
            _print_report(config, args.ranking, rows)
            if any(row.rank5 is None for row in rows):
                all_hit = False

    return 1 if args.strict and not all_hit else 0


if __name__ == "__main__":
    sys.exit(main())
