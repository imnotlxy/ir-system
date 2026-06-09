"""Experimental boolean-query interface backed by a prebuilt inverted index."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

INDEX_SCHEMA_VERSION = 1
DEFAULT_INDEX_SUBDIR = "experimental_query_index"
DEFAULT_INDEX_FILENAME = "index.json"
BODY_FIELD_KEYS = {
    "detail_fields",
    "detail_sections",
    "search_text",
    "sections",
    "text",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


def default_data_dir() -> Path:
    """Return the repository data directory."""
    return Path(__file__).resolve().parents[1] / "data"


def default_index_path(data_dir: str | Path | None = None) -> Path:
    """Return the default prebuilt experimental-index path."""
    root = Path(data_dir) if data_dir is not None else default_data_dir()
    return root / DEFAULT_INDEX_SUBDIR / DEFAULT_INDEX_FILENAME


def tokenize(text: str, *, for_query: bool = False) -> list[str]:
    """Tokenize text without external dependencies.

    English/digit runs are lower-cased as whole terms. Chinese runs are indexed as
    character n-grams up to length 3. Query-time Chinese terms longer than one
    character skip unigrams to avoid matching almost every document by a common
    single character.
    """
    tokens: list[str] = []
    for match in TOKEN_RE.finditer(text or ""):
        part = match.group(0)
        if not part:
            continue
        if re.fullmatch(r"[A-Za-z0-9_]+", part):
            tokens.append(part.lower())
            continue

        length = len(part)
        min_n = 2 if for_query and length > 1 else 1
        max_n = min(3, length)
        for n in range(min_n, max_n + 1):
            for i in range(0, length - n + 1):
                tokens.append(part[i : i + n])
    return tokens


def _iter_scalars(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_scalars(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_scalars(item)
    elif value is not None:
        yield str(value)


def _searchable_text(record: dict[str, Any]) -> str:
    return " ".join(_iter_scalars(record))


def strip_body_fields(record: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a teacher record without heavyweight body fields."""
    copied = deepcopy(record)
    for key in BODY_FIELD_KEYS:
        copied.pop(key, None)
    return copied


def _dict_field(record: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = record.get(key)
    return value if isinstance(value, Mapping) else {}


def extract_name(record: dict[str, Any]) -> str:
    profile = _dict_field(record, "profile")
    raw_api = _dict_field(record, "raw_api")
    return str(
        profile.get("name")
        or raw_api.get("title")
        or record.get("name")
        or record.get("title")
        or ""
    )


def extract_college_id(record: dict[str, Any]) -> int | None:
    source = _dict_field(record, "source")
    raw_api = _dict_field(record, "raw_api")
    value = (
        source.get("college_id") or raw_api.get("collegeId") or record.get("collegeId")
    )
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_teacher_id(record: dict[str, Any]) -> int | str:
    source = _dict_field(record, "source")
    raw_api = _dict_field(record, "raw_api")
    value = source.get("teacher_id") or raw_api.get("columnId") or ""
    return value if isinstance(value, int | str) else str(value)


def iter_teacher_records(data_dir: str | Path) -> Iterable[dict[str, Any]]:
    """Yield teacher records from data/teachers_by_college/*.jsonl."""
    teachers_dir = Path(data_dir) / "teachers_by_college"
    if not teachers_dir.exists():
        raise FileNotFoundError(f"Teacher directory not found: {teachers_dir}")

    for path in sorted(teachers_dir.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON in {path}:{line_number}") from exc
                if isinstance(record, dict):
                    yield record


def build_index(data_dir: str | Path | None = None) -> dict[str, Any]:
    """Build the experimental inverted index payload in memory."""
    root = Path(data_dir) if data_dir is not None else default_data_dir()
    records: list[dict[str, Any]] = []
    metadata: list[dict[str, Any]] = []
    postings: dict[str, set[int]] = defaultdict(set)

    for doc_id, record in enumerate(iter_teacher_records(root)):
        stored_record = strip_body_fields(record)
        records.append(stored_record)
        metadata.append(
            {
                "name": extract_name(stored_record),
                "collegeId": extract_college_id(stored_record),
                "teacherId": _source_teacher_id(stored_record),
            }
        )
        for token in set(tokenize(_searchable_text(record))):
            postings[token].add(doc_id)

    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "source": "teachers_by_college",
        "tokenizer": "regex-alnum-chinese-ngram-v1",
        "record_count": len(records),
        "records": records,
        "metadata": metadata,
        "index": {
            token: sorted(doc_ids) for token, doc_ids in sorted(postings.items())
        },
    }


def write_index(
    data_dir: str | Path | None = None, output: str | Path | None = None
) -> Path:
    """Build and write the experimental index to disk."""
    root = Path(data_dir) if data_dir is not None else default_data_dir()
    output_path = Path(output) if output is not None else default_index_path(root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_index(root)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return output_path


class ExperimentalQueryIndex:
    """Read-only experimental index with OR-connected keyword search."""

    def __init__(
        self, index_path: str | Path | None = None, data_dir: str | Path | None = None
    ):
        self.index_path = (
            Path(index_path) if index_path is not None else default_index_path(data_dir)
        )
        self.records: list[dict[str, Any]] = []
        self.metadata: list[dict[str, Any]] = []
        self.index: dict[str, set[int]] = {}
        self._loaded = False

    def load(self) -> None:
        if not self.index_path.exists():
            raise FileNotFoundError(
                f"Experimental query index not found: {self.index_path}. "
                "Build it with: python -m backend.experimental_query"
            )
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        if int(payload.get("schema_version") or 0) != INDEX_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported experimental index schema: {payload.get('schema_version')}"
            )

        records = payload.get("records")
        metadata = payload.get("metadata")
        raw_index = payload.get("index")
        if (
            not isinstance(records, list)
            or not isinstance(metadata, list)
            or not isinstance(raw_index, dict)
        ):
            raise ValueError(f"Malformed experimental query index: {self.index_path}")

        self.records = [record for record in records if isinstance(record, dict)]
        self.metadata = [item if isinstance(item, dict) else {} for item in metadata]
        self.index = {
            str(token): {int(doc_id) for doc_id in doc_ids}
            for token, doc_ids in raw_index.items()
            if isinstance(doc_ids, list)
        }
        self._loaded = True

    def query(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a boolean query.

        Request fields:
        - name: optional string, substring matched against the teacher name.
        - collegeId: optional int, exact matched against the teacher college id.
        - keywords: optional list[str], all keywords are connected with OR.
        """
        if not self._loaded:
            self.load()

        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")

        name = payload.get("name")
        if name is not None and not isinstance(name, str):
            raise ValueError("name must be a string or null")
        name = name.strip() if isinstance(name, str) else ""

        college_id = payload.get("collegeId")
        if college_id is not None:
            try:
                college_id = int(college_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("collegeId must be an integer or null") from exc

        keywords = payload.get("keywords", [])
        if keywords is None:
            keywords = []
        if not isinstance(keywords, list) or not all(
            isinstance(item, str) for item in keywords
        ):
            raise ValueError("keywords must be a list of strings")

        query_tokens: list[str] = []
        for keyword in keywords:
            keyword = keyword.strip()
            if keyword:
                query_tokens.extend(tokenize(keyword, for_query=True))
        unique_tokens = sorted(set(query_tokens))

        if unique_tokens:
            scores: Counter[int] = Counter()
            candidates: set[int] = set()
            for token in unique_tokens:
                doc_ids = self.index.get(token, set())
                candidates.update(doc_ids)
                scores.update(doc_ids)
        else:
            candidates = set(range(len(self.records)))
            scores = Counter()

        if name:
            lowered_name = name.lower()
            candidates = {
                doc_id
                for doc_id in candidates
                if lowered_name in str(self.metadata[doc_id].get("name", "")).lower()
            }

        if college_id is not None:
            candidates = {
                doc_id
                for doc_id in candidates
                if self.metadata[doc_id].get("collegeId") == college_id
            }

        sorted_doc_ids = sorted(
            candidates,
            key=lambda doc_id: (
                -scores[doc_id],
                str(self.metadata[doc_id].get("name", "")),
                doc_id,
            ),
        )
        return {"results": [self.records[doc_id] for doc_id in sorted_doc_ids]}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the precomputed experimental query inverted index."
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Directory containing teachers_by_college/*.jsonl",
    )
    parser.add_argument("--output", default=None, help="Output index JSON path")
    args = parser.parse_args()
    path = write_index(args.data_dir, args.output)
    print(f"Wrote experimental query index to {path}")


if __name__ == "__main__":
    main()
