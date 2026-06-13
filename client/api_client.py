"""HTTP client and DTOs used by the Qt frontend."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


@dataclass
class TeacherRecord:
    raw: dict[str, Any]
    name: str = ""
    career: str = ""
    college: str = ""
    college_id: int = 0
    gender: str = ""
    research: str = ""
    papers: str = ""
    representative_works: list[str] | None = None
    email: str = ""
    phone: str = ""
    education: str = ""
    intro: str = ""
    projects: str = ""
    search_text: str = ""
    sections: list[dict[str, Any]] | None = None
    detail_url: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TeacherRecord":
        return cls(
            raw=payload.get("raw") or {},
            name=payload.get("name") or "",
            career=payload.get("career") or "",
            college=payload.get("college") or "",
            college_id=int(payload.get("college_id") or 0),
            gender=payload.get("gender") or "",
            research=payload.get("research") or "",
            papers=payload.get("papers") or "",
            representative_works=list(payload.get("representative_works") or []),
            email=payload.get("email") or "",
            phone=payload.get("phone") or "",
            education=payload.get("education") or "",
            intro=payload.get("intro") or "",
            projects=payload.get("projects") or "",
            search_text=payload.get("search_text") or "",
            sections=list(payload.get("sections") or []),
            detail_url=payload.get("detail_url") or "",
        )


@dataclass
class SearchResult:
    record: TeacherRecord
    score: float
    match_mode: str = "exact"
    relaxed: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SearchResult":
        return cls(
            record=TeacherRecord.from_dict(payload.get("record") or {}),
            score=float(payload.get("score") or 0.0),
            match_mode=payload.get("match_mode") or "exact",
            relaxed=bool(payload.get("relaxed", False)),
        )


class SearchApiClient:
    """Thin JSON-over-HTTP client for the search backend."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: float = 15.0):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout

    def metadata(self) -> dict[str, Any]:
        return self._request("GET", "metadata")

    def search(
        self,
        query: str,
        *,
        ranking: str = "bm25",
        college_filter: list[str] | None = None,
        research_filter: str = "",
        auto_relax: bool = False,
        search_field: str = "",
    ) -> tuple[list[SearchResult], float, str]:
        payload = {
            "query": query,
            "ranking": ranking,
            "college_filter": college_filter or [],
            "research_filter": research_filter,
            "auto_relax": auto_relax,
            "search_field": search_field,
        }
        data = self._request("POST", "search", payload)
        results = [SearchResult.from_dict(item) for item in data.get("results", [])]
        return results, float(data.get("elapsed") or 0.0), data.get("mode_info") or ""

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = urljoin(self.base_url, path)
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"

        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return self._decode_response(response.read())
        except HTTPError as exc:
            detail = self._decode_response(exc.read()).get("error", exc.reason)
            raise RuntimeError(f"后端返回错误 {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"无法连接检索后端 {self.base_url}: {exc.reason}") from exc

    @staticmethod
    def _decode_response(body: bytes) -> dict[str, Any]:
        if not body:
            return {}
        try:
            data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("后端返回的不是有效 JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError("后端返回的 JSON 顶层必须是对象")
        return data
