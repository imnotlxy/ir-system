"""HTTP API server for the IR search backend."""

from __future__ import annotations

import argparse
import json
import ssl
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from backend.search_engine import SearchEngine, SearchResult, TeacherRecord


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


def _build_mode_info(results: list[SearchResult], baseline: bool) -> str:
    if baseline:
        return "基础系统（精确匹配）"
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

    def __init__(self, data_dir: str | Path | None = None):
        self.engine = SearchEngine(data_dir)
        self.engine.load_data()

    def metadata(self) -> dict[str, Any]:
        return {
            "record_count": len(self.engine.records),
            "college_names": self.engine.college_names,
        }

    def search(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")

        ranking = str(payload.get("ranking", "bm25"))
        college_filter = payload.get("college_filter") or None
        if college_filter is not None and not isinstance(college_filter, list):
            raise ValueError("college_filter must be a list")

        t0 = time.perf_counter()
        baseline = bool(payload.get("baseline", False))
        if baseline:
            results = self.engine.search_baseline(
                query,
                ranking=ranking,
                college_filter=college_filter,
                top_k=int(payload.get("top_k", 50)),
            )
        else:
            results = self.engine.search(
                query,
                match_mode=str(payload.get("match_mode", "exact")),
                ranking=ranking,
                college_filter=college_filter,
                research_filter=str(payload.get("research_filter", "")),
                auto_relax=bool(payload.get("auto_relax", False)),
                search_field=str(payload.get("search_field", "")),
                top_k=int(payload.get("top_k", 50)),
            )
        elapsed = time.perf_counter() - t0
        return {
            "results": [_result_to_dict(result) for result in results],
            "elapsed": elapsed,
            "mode_info": _build_mode_info(results, baseline),
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
            if self.path != "/search":
                self._send_error(HTTPStatus.NOT_FOUND, "not found")
                return

            try:
                payload = self._read_json()
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

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
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
    certfile: str | None = None,
    keyfile: str | None = None,
) -> None:
    api = SearchApi(data_dir)
    server = ThreadingHTTPServer((host, port), make_handler(api))
    scheme = "http"

    if certfile:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=certfile, keyfile=keyfile)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https"

    print(f"IR backend serving {len(api.engine.records)} records at {scheme}://{host}:{port}")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the IR search backend HTTP API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--certfile", default=None, help="TLS certificate for HTTPS")
    parser.add_argument("--keyfile", default=None, help="TLS private key for HTTPS")
    args = parser.parse_args()
    run_server(args.host, args.port, args.data_dir, args.certfile, args.keyfile)


if __name__ == "__main__":
    main()
