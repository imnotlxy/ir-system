"""IR search engine with BM25/TF-IDF ranking, fuzzy matching, and query relaxation."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path

import jieba

SEARCH_INDEX_SCHEMA_VERSION = 2
DEFAULT_SEARCH_INDEX_SUBDIR = "search_index"
DEFAULT_SEARCH_INDEX_FILENAME = "index.json"


def default_search_index_path(data_dir: str | Path | None = None) -> Path:
    """Return the default cached search-index path."""
    root = (
        Path(data_dir)
        if data_dir is not None
        else Path(__file__).resolve().parents[1] / "data"
    )
    return root / DEFAULT_SEARCH_INDEX_SUBDIR / DEFAULT_SEARCH_INDEX_FILENAME


@dataclass
class TeacherRecord:
    """A single teacher record with preprocessed fields for retrieval."""

    raw: dict
    name: str = ""
    career: str = ""
    college: str = ""
    college_id: int = 0
    gender: str = ""
    research: str = ""
    representative_works: list[str] = field(default_factory=list)
    email: str = ""
    phone: str = ""
    education: str = ""
    intro: str = ""
    projects: str = ""
    search_text: str = ""
    sections: list[dict] = field(default_factory=list)
    detail_url: str = ""
    tokens: list[str] = field(default_factory=list)
    field_tokens: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class SearchResult:
    """A single search result with score information."""

    record: TeacherRecord
    score: float
    match_mode: str = "exact"
    relaxed: bool = False


class SearchEngine:
    """Full-text search engine with BM25, TF-IDF, fuzzy matching, and query relaxation."""

    def __init__(
        self,
        data_dir: str | Path | None = None,
        index_path: str | Path | None = None,
    ):
        if data_dir is None:
            data_dir = Path(__file__).resolve().parents[1] / "data"
        self.data_dir = Path(data_dir)
        self.index_path = (
            Path(index_path)
            if index_path is not None
            else default_search_index_path(self.data_dir)
        )
        self.records: list[TeacherRecord] = []
        self.inverted_index: dict[str, set[int]] = defaultdict(set)
        self.doc_freq: dict[str, int] = defaultdict(int)
        self.doc_lengths: list[int] = []
        self.avg_dl: float = 0.0
        self.college_names: list[str] = []
        self._loaded = False

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_data(self) -> None:
        """Load teacher data from JSONL and reuse or rebuild the cached index."""
        jsonl_path = self.data_dir / "teachers.jsonl"
        if not jsonl_path.exists():
            raise FileNotFoundError(f"Data file not found: {jsonl_path}")

        source_signature = self._source_signature(jsonl_path)
        cached_payload = self._read_index_cache(source_signature)
        use_cache = cached_payload is not None

        self.records.clear()
        self._reset_index_state()

        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                record = self._parse_record(raw, tokenize=not use_cache)
                self.records.append(record)

        if cached_payload is not None:
            try:
                self._apply_index_cache(cached_payload)
            except ValueError:
                use_cache = False
                self.records = [
                    self._parse_record(record.raw, tokenize=True)
                    for record in self.records
                ]

        if not use_cache:
            self._build_index_state()
            self._write_index_cache(source_signature)

        self._loaded = True

    @staticmethod
    def _source_signature(jsonl_path: Path) -> dict[str, int]:
        stat = jsonl_path.stat()
        return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}

    def _reset_index_state(self) -> None:
        self.inverted_index = defaultdict(set)
        self.doc_freq = defaultdict(int)
        self.doc_lengths = []
        self.avg_dl = 0.0
        self.college_names = []

    def _read_index_cache(self, source_signature: dict[str, int]) -> dict | None:
        if not self.index_path.exists():
            return None
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if int(payload.get("schema_version") or 0) != SEARCH_INDEX_SCHEMA_VERSION:
            return None
        if payload.get("source") != "teachers.jsonl":
            return None
        if payload.get("tokenizer") != "jieba-with-single-char-v1":
            return None
        if payload.get("source_signature") != source_signature:
            return None
        return payload

    def _apply_index_cache(self, payload: dict) -> None:
        record_count = payload.get("record_count")
        record_tokens = payload.get("record_tokens")
        field_tokens = payload.get("field_tokens")
        raw_index = payload.get("index")
        raw_doc_freq = payload.get("doc_freq")
        doc_lengths = payload.get("doc_lengths")
        college_names = payload.get("college_names")
        avg_dl = payload.get("avg_dl")

        if record_count != len(self.records):
            raise ValueError("Cached search index record count does not match data")
        if not isinstance(record_tokens, list) or len(record_tokens) != len(
            self.records
        ):
            raise ValueError("Cached search index has invalid record tokens")
        if not isinstance(field_tokens, list) or len(field_tokens) != len(self.records):
            raise ValueError("Cached search index has invalid field tokens")
        if not isinstance(raw_index, dict) or not isinstance(raw_doc_freq, dict):
            raise ValueError("Cached search index has invalid postings")
        if not isinstance(doc_lengths, list) or len(doc_lengths) != len(self.records):
            raise ValueError("Cached search index has invalid document lengths")
        if not isinstance(college_names, list):
            raise ValueError("Cached search index has invalid college names")

        for idx, tokens in enumerate(record_tokens):
            if not isinstance(tokens, list):
                raise ValueError("Cached search index has invalid record token list")
            self.records[idx].tokens = [str(token) for token in tokens]

        for idx, fields in enumerate(field_tokens):
            if not isinstance(fields, dict):
                raise ValueError("Cached search index has invalid field token map")
            self.records[idx].field_tokens = {
                str(field): [str(token) for token in tokens]
                for field, tokens in fields.items()
                if isinstance(tokens, list)
            }

        inverted_index: dict[str, set[int]] = {}
        for token, doc_ids in raw_index.items():
            if not isinstance(doc_ids, list):
                continue
            postings = {int(doc_id) for doc_id in doc_ids}
            if any(doc_id < 0 or doc_id >= len(self.records) for doc_id in postings):
                raise ValueError("Cached search index has out-of-range postings")
            inverted_index[str(token)] = postings
        self.inverted_index = defaultdict(set, inverted_index)
        self.doc_freq = defaultdict(
            int,
            {str(token): int(freq) for token, freq in raw_doc_freq.items()},
        )
        self.doc_lengths = [int(length) for length in doc_lengths]
        self.avg_dl = float(avg_dl) if isinstance(avg_dl, int | float) else 1.0
        self.college_names = [str(name) for name in college_names]

    def _build_index_state(self) -> None:
        self._reset_index_state()
        for idx, record in enumerate(self.records):
            token_set = set(record.tokens)
            self.doc_lengths.append(len(record.tokens))
            for token in token_set:
                self.inverted_index[token].add(idx)
                self.doc_freq[token] += 1

        total = sum(self.doc_lengths) if self.doc_lengths else 1
        self.avg_dl = total / len(self.doc_lengths) if self.doc_lengths else 1.0

        seen: set[str] = set()
        for record in self.records:
            if record.college and record.college not in seen:
                seen.add(record.college)
                self.college_names.append(record.college)

    def _write_index_cache(self, source_signature: dict[str, int]) -> None:
        payload = {
            "schema_version": SEARCH_INDEX_SCHEMA_VERSION,
            "source": "teachers.jsonl",
            "source_signature": source_signature,
            "tokenizer": "jieba-with-single-char-v1",
            "record_count": len(self.records),
            "doc_lengths": self.doc_lengths,
            "avg_dl": self.avg_dl,
            "college_names": self.college_names,
            "record_tokens": [record.tokens for record in self.records],
            "field_tokens": [record.field_tokens for record in self.records],
            "doc_freq": dict(sorted(self.doc_freq.items())),
            "index": {
                token: sorted(doc_ids)
                for token, doc_ids in sorted(self.inverted_index.items())
            },
        }
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.index_path.with_suffix(self.index_path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        tmp_path.replace(self.index_path)

    def _parse_record(self, raw: dict, *, tokenize: bool = True) -> TeacherRecord:
        """Parse a raw JSON record into a TeacherRecord."""
        if int(raw.get("schema_version") or 1) >= 2:
            profile = raw.get("profile", {})
            source = raw.get("source", {})
            text = raw.get("text", {})
            raw_api = raw.get("raw_api", {})
            sections = list(text.get("sections") or [])

            name = profile.get("name", "")
            career = profile.get("title", "") or raw_api.get("career", "")
            college = source.get("college_name", "")
            college_id = int(source.get("college_id") or 0)
            gender = profile.get("gender", "")
            research = profile.get("research_directions", "")
            representative_works = list(profile.get("representative_works") or [])
            email = profile.get("email", "")
            phone = profile.get("phone", "")
            education = self._section_text(sections, {"教育经历"})
            intro = self._section_text(sections, {"个人简介", "个人简历", "个人概况"})
            projects = self._section_text(sections, {"科研项目"})
            search_text = text.get("full_text", "")
            detail_url = source.get("detail_url", "")
        else:
            fields = raw.get("detail_fields", {})
            sections = self._legacy_sections(raw.get("detail_sections", []))
            name = raw.get("title", "")
            career = raw.get("career", "")
            college = raw.get("collegeName", "")
            college_id = raw.get("collegeId", 0)
            gender = fields.get("性别", "")
            research = fields.get("研究领域", fields.get("研究方向", ""))
            representative_works = self._split_legacy_works(fields.get("论文", ""))
            email = fields.get("电子邮箱", "")
            phone = fields.get("联系电话", "")
            education = fields.get("教育经历", "")
            intro = fields.get("个人简介", "")
            projects = fields.get("科研项目", "")
            search_text = raw.get("search_text", "")
            detail_url = raw.get("detail_url", "")

        works_text = " ".join(representative_works)
        section_text = " ".join(
            paragraph
            for section in sections
            for paragraph in section.get("paragraphs", [])
        )
        tokens: list[str] = []
        field_tokens: dict[str, list[str]] = {}
        if tokenize:
            combined = " ".join(
                filter(
                    None,
                    [
                        name,
                        career,
                        college,
                        gender,
                        research,
                        works_text,
                        education,
                        intro,
                        projects,
                        section_text,
                        search_text,
                    ],
                )
            )
            tokens = self._tokenize_for_index(combined)

            field_tokens = {
                "name": self._tokenize_for_index(name),
                "papers": self._tokenize_for_index(works_text),
                "works": self._tokenize_for_index(works_text),
                "research": self._tokenize_for_index(research),
                "college": self._tokenize_for_index(college),
                "career": self._tokenize_for_index(career),
                "title": self._tokenize_for_index(career),
                "education": self._tokenize_for_index(education),
                "intro": self._tokenize_for_index(intro),
                "projects": self._tokenize_for_index(projects),
                "profile": self._tokenize_for_index(
                    " ".join(
                        filter(None, [name, career, college, gender, email, phone])
                    )
                ),
                "text": self._tokenize_for_index(section_text or search_text),
        }

        return TeacherRecord(
            raw=raw,
            name=name,
            career=career,
            college=college,
            college_id=college_id,
            gender=gender,
            research=research,
            representative_works=representative_works,
            email=email,
            phone=phone,
            education=education,
            intro=intro,
            projects=projects,
            search_text=search_text,
            sections=sections,
            detail_url=detail_url,
            tokens=tokens,
            field_tokens=field_tokens,
        )

    @staticmethod
    def _section_text(sections: list[dict], headings: set[str]) -> str:
        paragraphs: list[str] = []
        for section in sections:
            heading = str(section.get("heading", "")).strip()
            if heading in headings:
                paragraphs.extend(str(item) for item in section.get("paragraphs", []))
        return " ".join(paragraphs)

    @staticmethod
    def _legacy_sections(sections: list[dict]) -> list[dict]:
        result: list[dict] = []
        for section in sections:
            paragraphs = []
            for item in section.get("items", []):
                label = item.get("label", "")
                value = item.get("value", "")
                if value:
                    paragraphs.append(f"{label}: {value}")
            if section.get("text"):
                paragraphs.append(section["text"])
            if section.get("title") or paragraphs:
                result.append(
                    {"heading": section.get("title", ""), "paragraphs": paragraphs}
                )
        return result

    @staticmethod
    def _split_legacy_works(text: str, limit: int = 5) -> list[str]:
        parts = re.split(r"(?=(?:^|\s)\d{1,2}[、.．])", text or "")
        works = [part.strip() for part in parts if part.strip()]
        return works[:limit] if works else []

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Tokenize Chinese + English text using jieba."""
        text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text, flags=re.UNICODE)
        tokens: list[str] = []
        for word in jieba.cut(text):
            word = word.strip()
            if word and len(word) > 0:
                tokens.append(word.lower())
        return tokens

    @staticmethod
    def _tokenize_for_index(text: str) -> list[str]:
        """Tokenize text for indexing, including Chinese single-character tokens."""
        tokens = SearchEngine._tokenize(text)
        seen = set(tokens)
        for char in re.findall(r"[\u4e00-\u9fff]", text):
            if char not in seen:
                tokens.append(char)
                seen.add(char)
        return tokens

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _bm25_score(
        self,
        query_tokens: list[str],
        doc_idx: int,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> float:
        """Compute BM25 score for a single document."""
        score = 0.0
        dl = self.doc_lengths[doc_idx]
        n = len(self.records)
        for term in query_tokens:
            df = self.doc_freq.get(term, 0)
            if df == 0:
                continue
            idf = math.log((n - df + 0.5) / (df + 0.5) + 1.0)
            # Count term frequency in doc
            tf = self.records[doc_idx].tokens.count(term)
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * dl / self.avg_dl)
            score += idf * numerator / denominator
        return score

    def _tfidf_score(self, query_tokens: list[str], doc_idx: int) -> float:
        """Compute TF-IDF cosine similarity score."""
        n = len(self.records)
        doc_tokens = self.records[doc_idx].tokens
        doc_counter = Counter(doc_tokens)
        doc_len = math.sqrt(sum(v**2 for v in doc_counter.values())) or 1.0

        query_counter = Counter(query_tokens)
        query_len = math.sqrt(sum(v**2 for v in query_counter.values())) or 1.0

        score = 0.0
        for term, qtf in query_counter.items():
            df = self.doc_freq.get(term, 0)
            if df == 0:
                continue
            idf = math.log(n / (df + 1)) + 1.0
            dtf = doc_counter.get(term, 0)
            score += qtf * dtf * idf * idf

        return score / (doc_len * query_len) if (doc_len * query_len) > 0 else 0.0

    @staticmethod
    def _name_match_boost(query_tokens: list[str], record: TeacherRecord) -> float:
        query_text = re.sub(r"\s+", "", "".join(query_tokens).lower())
        name = re.sub(r"\s+", "", record.name.lower())
        if query_text and query_text == name:
            return 100.0
        if query_text and query_text in name:
            return 20.0
        return 0.0

    # ------------------------------------------------------------------
    # Search methods
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        match_mode: str = "exact",
        ranking: str = "bm25",
        college_filter: list[str] | None = None,
        research_filter: str = "",
        auto_relax: bool = False,
        search_field: str = "",
        top_k: int = 50,
    ) -> list[SearchResult]:
        """Execute a search query with the specified options.

        Args:
            query: The search query string.
            match_mode: "exact" or "fuzzy".
            ranking: "bm25" or "tfidf".
            college_filter: Optional list of college names to filter by.
            research_filter: Optional comma-separated research keywords.
            auto_relax: If True, relax query when no results found.
            search_field: If set, restrict search to this field (e.g. "name", "papers").
            top_k: Maximum number of results to return.

        Returns:
            List of SearchResult sorted by score descending.
        """
        if not self._loaded:
            self.load_data()

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # Field-specific search
        if search_field:
            return self._field_search(
                query_tokens,
                field=search_field,
                ranking=ranking,
                match_mode=match_mode,
                college_filter=college_filter,
                research_filter=research_filter,
                auto_relax=auto_relax,
                top_k=top_k,
            )

        # Phase 1: exact search
        results = self._ranked_search(
            query_tokens,
            ranking=ranking,
            match_mode="exact",
            college_filter=college_filter,
            research_filter=research_filter,
        )

        if results:
            return results[:top_k]

        # No results — try fuzzy if requested
        if match_mode == "fuzzy":
            fuzzy_tokens = self._fuzzy_expand(query_tokens)
            results = self._ranked_search(
                fuzzy_tokens,
                ranking=ranking,
                match_mode="fuzzy",
                college_filter=college_filter,
                research_filter=research_filter,
            )
            if results:
                return results[:top_k]

        # Still no results — try query relaxation (OR instead of AND)
        if auto_relax:
            results = self._relaxed_search(
                query_tokens,
                ranking=ranking,
                college_filter=college_filter,
                research_filter=research_filter,
            )
            if results:
                return results[:top_k]

            if match_mode == "fuzzy":
                fuzzy_tokens = self._fuzzy_expand(query_tokens)
                results = self._relaxed_search(
                    fuzzy_tokens,
                    ranking=ranking,
                    college_filter=college_filter,
                    research_filter=research_filter,
                )
                if results:
                    return results[:top_k]

        return results[:top_k]

    def search_baseline(
        self,
        query: str,
        *,
        ranking: str = "bm25",
        college_filter: list[str] | None = None,
        research_filter: str = "",
        top_k: int = 50,
    ) -> list[SearchResult]:
        """Baseline search: exact match only, no fuzzy, no relaxation."""
        if not self._loaded:
            self.load_data()

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        results = self._ranked_search(
            query_tokens,
            ranking=ranking,
            match_mode="exact",
            college_filter=college_filter,
            research_filter=research_filter,
        )
        return results[:top_k]

    def _ranked_search(
        self,
        query_tokens: list[str],
        *,
        ranking: str,
        match_mode: str,
        college_filter: list[str] | None,
        research_filter: str,
    ) -> list[SearchResult]:
        """Score all candidate documents and return sorted results."""
        # Find candidate docs: intersection of all query tokens in inverted index
        candidate_sets: list[set[int]] = []
        for token in query_tokens:
            if token in self.inverted_index:
                candidate_sets.append(self.inverted_index[token])

        if not candidate_sets:
            return []

        candidates = candidate_sets[0]
        for s in candidate_sets[1:]:
            candidates = candidates & s

        if not candidates:
            return []

        # Apply filters
        if college_filter:
            college_set = set(college_filter)
            candidates = {
                idx for idx in candidates if self.records[idx].college in college_set
            }

        if research_filter:
            research_keywords = [
                kw.strip().lower() for kw in research_filter.split(",") if kw.strip()
            ]
            if research_keywords:
                filtered = set()
                for idx in candidates:
                    research_text = self.records[idx].research.lower()
                    if any(kw in research_text for kw in research_keywords):
                        filtered.add(idx)
                candidates = filtered

        if not candidates:
            return []

        # Score
        score_fn = self._bm25_score if ranking == "bm25" else self._tfidf_score
        results: list[SearchResult] = []
        for idx in candidates:
            score = score_fn(query_tokens, idx) + self._name_match_boost(
                query_tokens, self.records[idx]
            )
            if score > 0:
                results.append(
                    SearchResult(
                        record=self.records[idx],
                        score=score,
                        match_mode=match_mode,
                        relaxed=False,
                    )
                )

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _relaxed_search(
        self,
        query_tokens: list[str],
        *,
        ranking: str,
        college_filter: list[str] | None,
        research_filter: str,
    ) -> list[SearchResult]:
        """Relaxed search: union of any query token match (OR logic)."""
        candidates: set[int] = set()
        for token in query_tokens:
            if token in self.inverted_index:
                candidates |= self.inverted_index[token]

        if not candidates:
            return []

        if college_filter:
            college_set = set(college_filter)
            candidates = {
                idx for idx in candidates if self.records[idx].college in college_set
            }

        if research_filter:
            research_keywords = [
                kw.strip().lower() for kw in research_filter.split(",") if kw.strip()
            ]
            if research_keywords:
                filtered = set()
                for idx in candidates:
                    research_text = self.records[idx].research.lower()
                    if any(kw in research_text for kw in research_keywords):
                        filtered.add(idx)
                candidates = filtered

        if not candidates:
            return []

        score_fn = self._bm25_score if ranking == "bm25" else self._tfidf_score
        results: list[SearchResult] = []
        for idx in candidates:
            score = score_fn(query_tokens, idx) + self._name_match_boost(
                query_tokens, self.records[idx]
            )
            if score > 0:
                results.append(
                    SearchResult(
                        record=self.records[idx],
                        score=score,
                        match_mode="relaxed",
                        relaxed=True,
                    )
                )

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _fuzzy_expand(self, query_tokens: list[str], cutoff: float = 0.6) -> list[str]:
        """Expand query tokens with fuzzy matches from the vocabulary."""
        all_terms = list(self.inverted_index.keys())
        expanded: list[str] = list(query_tokens)
        for token in query_tokens:
            matches = get_close_matches(token, all_terms, n=3, cutoff=cutoff)
            for m in matches:
                if m not in expanded:
                    expanded.append(m)
        return expanded

    def _field_search(
        self,
        query_tokens: list[str],
        *,
        field: str,
        ranking: str,
        match_mode: str,
        college_filter: list[str] | None,
        research_filter: str,
        auto_relax: bool,
        top_k: int,
    ) -> list[SearchResult]:
        """Search restricted to a single field of each document."""
        candidates: set[int] = set()
        for idx, record in enumerate(self.records):
            ftokens = record.field_tokens.get(field, [])
            token_set = set(ftokens)
            # AND logic: all query tokens must appear in the field
            if all(t in token_set for t in query_tokens):
                candidates.add(idx)

        # Fallback: fuzzy expand
        if not candidates and match_mode == "fuzzy":
            fuzzy_tokens = self._fuzzy_expand(query_tokens)
            for idx, record in enumerate(self.records):
                ftokens = record.field_tokens.get(field, [])
                token_set = set(ftokens)
                if any(t in token_set for t in fuzzy_tokens):
                    candidates.add(idx)

        # Fallback: relax to OR
        if not candidates and auto_relax:
            for idx, record in enumerate(self.records):
                ftokens = record.field_tokens.get(field, [])
                token_set = set(ftokens)
                if any(t in token_set for t in query_tokens):
                    candidates.add(idx)

        if college_filter:
            college_set = set(college_filter)
            candidates = {
                idx for idx in candidates if self.records[idx].college in college_set
            }

        if research_filter:
            research_keywords = [
                kw.strip().lower() for kw in research_filter.split(",") if kw.strip()
            ]
            if research_keywords:
                filtered = set()
                for idx in candidates:
                    research_text = self.records[idx].research.lower()
                    if any(kw in research_text for kw in research_keywords):
                        filtered.add(idx)
                candidates = filtered

        if not candidates:
            return []

        # Score using field-specific tokens
        score_fn = self._bm25_score if ranking == "bm25" else self._tfidf_score
        results: list[SearchResult] = []
        for idx in candidates:
            score = score_fn(query_tokens, idx)
            if score > 0:
                results.append(
                    SearchResult(
                        record=self.records[idx],
                        score=score,
                        match_mode=f"field:{field}",
                        relaxed=False,
                    )
                )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]
