"""IR search engine with BM25/TF-IDF ranking, fuzzy matching, and query relaxation."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from difflib import get_close_matches

import jieba


@dataclass
class TeacherRecord:
    """A single teacher record with preprocessed fields for retrieval."""

    raw: dict
    name: str = ""
    career: str = ""
    college: str = ""
    college_id: int = 0
    research: str = ""
    papers: str = ""
    email: str = ""
    phone: str = ""
    education: str = ""
    intro: str = ""
    projects: str = ""
    search_text: str = ""
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

    def __init__(self, data_dir: str | Path | None = None):
        if data_dir is None:
            data_dir = Path(__file__).resolve().parents[1] / "data"
        self.data_dir = Path(data_dir)
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
        """Load teacher data from JSONL and build the index."""
        jsonl_path = self.data_dir / "teachers.jsonl"
        if not jsonl_path.exists():
            raise FileNotFoundError(f"Data file not found: {jsonl_path}")

        self.records.clear()
        self.inverted_index.clear()
        self.doc_freq.clear()
        self.doc_lengths.clear()

        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                record = self._parse_record(raw)
                self.records.append(record)

        # Build inverted index
        for idx, record in enumerate(self.records):
            token_set = set(record.tokens)
            self.doc_lengths.append(len(record.tokens))
            for token in token_set:
                self.inverted_index[token].add(idx)
                self.doc_freq[token] += 1

        total = sum(self.doc_lengths) if self.doc_lengths else 1
        self.avg_dl = total / len(self.doc_lengths) if self.doc_lengths else 1.0

        # Extract unique college names
        seen: set[str] = set()
        self.college_names = []
        for r in self.records:
            if r.college and r.college not in seen:
                seen.add(r.college)
                self.college_names.append(r.college)

        self._loaded = True

    def _parse_record(self, raw: dict) -> TeacherRecord:
        """Parse a raw JSON record into a TeacherRecord."""
        fields = raw.get("detail_fields", {})
        name = raw.get("title", "")
        career = raw.get("career", "")
        college = raw.get("collegeName", "")
        college_id = raw.get("collegeId", 0)
        research = fields.get("研究领域", fields.get("研究方向", ""))
        papers = fields.get("论文", "")
        email = fields.get("电子邮箱", "")
        phone = fields.get("联系电话", "")
        education = fields.get("教育经历", "")
        intro = fields.get("个人简介", "")
        projects = fields.get("科研项目", "")
        search_text = raw.get("search_text", "")
        detail_url = raw.get("detail_url", "")

        # Build a combined text for indexing
        combined = " ".join(
            filter(None, [name, career, college, research, papers, education, intro, projects, search_text])
        )
        tokens = self._tokenize(combined)

        # Build per-field tokens for field-specific search
        field_tokens = {
            "name": self._tokenize(name),
            "papers": self._tokenize(papers),
            "research": self._tokenize(research),
            "college": self._tokenize(college),
            "career": self._tokenize(career),
            "education": self._tokenize(education),
            "intro": self._tokenize(intro),
            "projects": self._tokenize(projects),
        }

        return TeacherRecord(
            raw=raw,
            name=name,
            career=career,
            college=college,
            college_id=college_id,
            research=research,
            papers=papers,
            email=email,
            phone=phone,
            education=education,
            intro=intro,
            projects=projects,
            search_text=search_text,
            detail_url=detail_url,
            tokens=tokens,
            field_tokens=field_tokens,
        )

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
        doc_len = math.sqrt(sum(v ** 2 for v in doc_counter.values())) or 1.0

        query_counter = Counter(query_tokens)
        query_len = math.sqrt(sum(v ** 2 for v in query_counter.values())) or 1.0

        score = 0.0
        for term, qtf in query_counter.items():
            df = self.doc_freq.get(term, 0)
            if df == 0:
                continue
            idf = math.log(n / (df + 1)) + 1.0
            dtf = doc_counter.get(term, 0)
            score += qtf * dtf * idf * idf

        return score / (doc_len * query_len) if (doc_len * query_len) > 0 else 0.0

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
                query_tokens, field=search_field, ranking=ranking,
                match_mode=match_mode, college_filter=college_filter,
                research_filter=research_filter, auto_relax=auto_relax,
                top_k=top_k,
            )

        # Phase 1: exact search
        results = self._ranked_search(
            query_tokens, ranking=ranking, match_mode="exact",
            college_filter=college_filter, research_filter=research_filter,
        )

        if results:
            return results[:top_k]

        # No results — try fuzzy if requested
        if match_mode == "fuzzy":
            fuzzy_tokens = self._fuzzy_expand(query_tokens)
            results = self._ranked_search(
                fuzzy_tokens, ranking=ranking, match_mode="fuzzy",
                college_filter=college_filter, research_filter=research_filter,
            )
            if results:
                return results[:top_k]

        # Still no results — try query relaxation (OR instead of AND)
        if auto_relax:
            results = self._relaxed_search(
                query_tokens, ranking=ranking,
                college_filter=college_filter, research_filter=research_filter,
            )
            if results:
                return results[:top_k]

            if match_mode == "fuzzy":
                fuzzy_tokens = self._fuzzy_expand(query_tokens)
                results = self._relaxed_search(
                    fuzzy_tokens, ranking=ranking,
                    college_filter=college_filter, research_filter=research_filter,
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
        top_k: int = 50,
    ) -> list[SearchResult]:
        """Baseline search: exact match only, no fuzzy, no relaxation."""
        if not self._loaded:
            self.load_data()

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        results = self._ranked_search(
            query_tokens, ranking=ranking, match_mode="exact",
            college_filter=college_filter, research_filter="",
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
            candidates = {idx for idx in candidates if self.records[idx].college in college_set}

        if research_filter:
            research_keywords = [kw.strip().lower() for kw in research_filter.split(",") if kw.strip()]
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
            score = score_fn(query_tokens, idx)
            if score > 0:
                results.append(SearchResult(
                    record=self.records[idx],
                    score=score,
                    match_mode=match_mode,
                    relaxed=False,
                ))

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
            candidates = {idx for idx in candidates if self.records[idx].college in college_set}

        if research_filter:
            research_keywords = [kw.strip().lower() for kw in research_filter.split(",") if kw.strip()]
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
            score = score_fn(query_tokens, idx)
            if score > 0:
                results.append(SearchResult(
                    record=self.records[idx],
                    score=score,
                    match_mode="relaxed",
                    relaxed=True,
                ))

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
            candidates = {idx for idx in candidates if self.records[idx].college in college_set}

        if research_filter:
            research_keywords = [kw.strip().lower() for kw in research_filter.split(",") if kw.strip()]
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
                results.append(SearchResult(
                    record=self.records[idx],
                    score=score,
                    match_mode=f"field:{field}",
                    relaxed=False,
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]
