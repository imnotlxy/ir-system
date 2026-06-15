"""HTTP API server for the IR search backend."""

from __future__ import annotations

import argparse
import json
import logging
import ssl
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from backend.experimental_query import ExperimentalQueryIndex
from backend.llm_query_weight import LlmQueryWeightError, compute_query_weights
from backend.llm_rerank import LlmRerankError, rerank
from backend.search_engine import (
    RelatedTeacherResult,
    SearchEngine,
    SearchResult,
    TeacherRecord,
)

logger = logging.getLogger(__name__)


def _record_to_dict(record: TeacherRecord) -> dict[str, Any]:
    return {
        "raw": record.raw,
        "name": record.name,
        "career": record.career,
        "college": record.college,
        "college_id": record.college_id,
        "gender": record.gender,
        "research": record.research,
        "papers": "\n".join(record.representative_works),
        "representative_works": record.representative_works,
        "email": record.email,
        "phone": record.phone,
        "education": record.education,
        "intro": record.intro,
        "projects": record.projects,
        "search_text": record.search_text,
        "sections": record.sections,
        "detail_url": record.detail_url,
    }


def _result_to_dict(result: SearchResult) -> dict[str, Any]:
    return {
        "record": _record_to_dict(result.record),
        "score": result.score,
        "match_mode": result.match_mode,
        "relaxed": result.relaxed,
    }


def _related_result_to_dict(result: RelatedTeacherResult) -> dict[str, Any]:
    return {
        "record": _record_to_dict(result.record),
        "score": result.score,
        "reasons": result.reasons,
        "keywords": result.keywords,
    }


def _build_mode_info(results: list[SearchResult]) -> str:
    if not results:
        return "无结果"
    mode = results[0].match_mode
    relaxed = any(r.relaxed for r in results)
    info = f"匹配模式：{mode}"
    if relaxed:
        info += "（已放宽查询）"
    return info


class SearchApi:
    """Small application service around SearchEngine."""

    def __init__(self, data_dir: str | Path | None = None, advanced: bool = False):
        self.advanced = advanced
        self.engine = SearchEngine(data_dir)
        self.engine.load_data()
        self.experimental_index = ExperimentalQueryIndex(data_dir=data_dir)
        self.experimental_index.load()

    def metadata(self) -> dict[str, Any]:
        return {
            "record_count": len(self.engine.records),
            "college_names": self.engine.college_names,
            "advanced": self.advanced,
        }

    def experimental_query(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.experimental_index.query(payload)

    def related_teachers(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.advanced:
            raise ValueError("related_teachers requires advanced mode")

        record_payload = payload.get("record")
        if not isinstance(record_payload, dict):
            raise ValueError("record is required")

        top_k = int(payload.get("top_k") or 10)
        if top_k <= 0:
            top_k = 10

        results = self.engine.related_teachers(record_payload, top_k=top_k)
        return {"results": [_related_result_to_dict(result) for result in results]}

    def search(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")

        ranking = str(payload.get("ranking", "bm25"))
        college_filter = payload.get("college_filter") or None
        if college_filter is not None and not isinstance(college_filter, list):
            raise ValueError("college_filter must be a list")

        t0 = time.perf_counter()
        # Only allow advanced options when the backend is in advanced mode
        auto_relax = bool(payload.get("auto_relax", False)) and self.advanced
        llm_rerank = bool(payload.get("llm_rerank", False)) and self.advanced
        llm_query_weight = (
            bool(payload.get("llm_query_weight", False)) and self.advanced
        )

        token_weights: dict[str, float] | None = None
        if llm_query_weight:
            logger.info("Search request will use LLM query weighting: query=%r", query)
            try:
                query_tokens = self.engine._tokenize(query)
                token_weights = compute_query_weights(query, query_tokens)
                logger.info(
                    "LLM query weighting succeeded: query=%r weights=%s",
                    query,
                    token_weights,
                )
            except LlmQueryWeightError as exc:
                logger.error(
                    "LLM query weighting failed: query=%r error=%s", query, exc
                )

        results = self.engine.search(
            query,
            ranking=ranking,
            college_filter=college_filter,
            research_filter=str(payload.get("research_filter", "")),
            auto_relax=auto_relax,
            search_field=str(payload.get("search_field", "")),
            top_k=int(payload.get("top_k", 50)),
            token_weights=token_weights,
            pinyin_query=bool(payload.get("pinyin_query", False)),
        )

        mode_info = _build_mode_info(results)
        if token_weights:
            weights_summary = " ".join(f"{t}={w:.1f}" for t, w in token_weights.items())
            mode_info = f"{mode_info}（LLM 查询加权：{weights_summary}）"

        if llm_rerank and results:
            logger.info(
                "Search request will use LLM reranking: query=%r advanced=%s",
                query,
                self.advanced,
            )
            try:
                results = rerank(query, results)
                mode_info = f"{mode_info}（LLM 重排）"
                logger.info("LLM reranking succeeded: query=%r", query)
            except LlmRerankError as exc:
                mode_info = f"{mode_info}（LLM 重排失败：{exc}）"
                logger.error("LLM reranking failed: query=%r error=%s", query, exc)

        elapsed = time.perf_counter() - t0
        return {
            "results": [_result_to_dict(result) for result in results],
            "elapsed": elapsed,
            "mode_info": mode_info,
        }


def make_handler(api: SearchApi) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "IRSearchBackend/0.1"

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send_json({"status": "ok"})
            elif self.path == "/metadata":
                self._send_json(api.metadata())
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "not found")

        def do_POST(self) -> None:
            if self.path not in {
                "/search",
                "/experimental-query",
                "/query",
                "/related-teachers",
            }:
                self._send_error(HTTPStatus.NOT_FOUND, "not found")
                return

            try:
                payload = self._read_json()
                if self.path in {"/experimental-query", "/query"}:
                    self._send_json(api.experimental_query(payload))
                elif self.path == "/related-teachers":
                    self._send_json(api.related_teachers(payload))
                else:
                    self._send_json(api.search(payload))
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        def do_OPTIONS(self) -> None:
            self.send_response(HTTPStatus.NO_CONTENT)
            self._send_common_headers()
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            print(f"{self.address_string()} - {format % args}")

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            body = self.rfile.read(length)
            try:
                payload = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError("request body must be valid JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _send_json(
            self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK
        ) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._send_common_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, status: HTTPStatus, message: str) -> None:
            self._send_json({"error": message}, status)

        def _send_common_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    return Handler


def run_server(
    host: str,
    port: int,
    data_dir: str | Path | None = None,
    advanced: bool = False,
    certfile: str | None = None,
    keyfile: str | None = None,
) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    api = SearchApi(data_dir, advanced=advanced)
    server = ThreadingHTTPServer((host, port), make_handler(api))
    scheme = "http"

    if certfile:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=certfile, keyfile=keyfile)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https"

    logger.info(
        "IR backend serving %d records at %s://%s:%d (advanced=%s)",
        len(api.engine.records),
        scheme,
        host,
        port,
        advanced,
    )
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the IR search backend HTTP API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument(
        "--advanced",
        action="store_true",
        help="Enable advanced features (fuzzy match, auto-relax, etc.)",
    )
    parser.add_argument("--certfile", default=None, help="TLS certificate for HTTPS")
    parser.add_argument("--keyfile", default=None, help="TLS private key for HTTPS")
    args = parser.parse_args()
    run_server(
        args.host, args.port, args.data_dir, args.advanced, args.certfile, args.keyfile
    )


if __name__ == "__main__":
    main()
