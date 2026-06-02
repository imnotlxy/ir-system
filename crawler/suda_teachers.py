from __future__ import annotations

import argparse
import csv
import html
import json
import random
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


BASE_URL = "https://web.suda.edu.cn"
QUERY_URL = f"{BASE_URL}/_wp3services/generalQuery?queryObj=teacherHome"

SELECTED_COLLEGES = [
    {"collegeId": 15, "collegeName": "计算机科学与技术学院（软件学院）"},
    {"collegeId": 85, "collegeName": "电子信息学院"},
    {"collegeId": 110, "collegeName": "光电科学与工程学院"},
    {"collegeId": 78, "collegeName": "数学科学学院"},
    {"collegeId": 81, "collegeName": "商学院"},
]

ORG_RETURN_INFOS = [
    {"field": "collegeId", "name": "collegeId"},
    {"field": "collegeName", "pattern": [{"name": "lp", "value": "20"}], "name": "collegeName"},
    {"field": "collegeEnName", "name": "collegeEnName"},
    {"field": "url", "name": "url"},
    {"field": "count", "name": "count"},
    {"field": "fullDepartName", "name": "fullDepartName"},
    {"field": "departCategoryId", "name": "departCategoryId"},
]

TEACHER_RETURN_INFOS = [
    {"field": "title", "name": "title"},
    {"field": "career", "name": "career"},
    {"field": "visitCount", "name": "visitCount"},
    {"field": "headerPic", "name": "headerPic"},
    {"field": "cnUrl", "name": "cnUrl"},
    {"field": "department", "name": "department"},
    {"field": "publishStatus", "name": "publishStatus"},
]


class FieldPairParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._active: str | None = None
        self._parts: list[str] = []
        self.items: list[tuple[str, str]] = []
        self._pending_title: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "span":
            return
        attr_map = {name: value or "" for name, value in attrs}
        classes = set(attr_map.get("class", "").split())
        if "fws_displayTitle" in classes:
            self._start_capture("title")
        elif "fws_displayField" in classes:
            self._start_capture("field")

    def handle_data(self, data: str) -> None:
        if self._active is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "span" and self._active is not None:
            text = clean_text("".join(self._parts))
            if self._active == "title":
                self._pending_title = text.rstrip("：:")
            elif self._active == "field" and self._pending_title:
                self.items.append((self._pending_title, text))
                self._pending_title = None
            self._active = None
            self._parts = []

    def _start_capture(self, kind: str) -> None:
        self._active = kind
        self._parts = []


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.parts.append(data)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def fetch_bytes(url: str, data: dict[str, str] | None = None, retries: int = 3) -> bytes:
    payload = urlencode(data).encode("utf-8") if data is not None else None
    request = Request(
        url,
        data=payload,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ir-system crawler; +https://github.com/imnotlxy/ir-system)",
            "Accept": "application/json,text/html,application/xhtml+xml",
        },
        method="POST" if data is not None else "GET",
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=20) as response:
                return response.read()
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.0 * attempt)
    raise RuntimeError(f"fetch failed: {url}") from last_error


def post_json(data: dict[str, str]) -> dict[str, Any]:
    raw = fetch_bytes(QUERY_URL, data)
    return json.loads(raw.decode("utf-8"))


def get_all_colleges() -> list[dict[str, Any]]:
    result = post_json(
        {
            "siteId": "2",
            "pageIndex": "1",
            "rows": "200",
            "returnInfos": json.dumps(ORG_RETURN_INFOS, ensure_ascii=False, separators=(",", ":")),
            "articleType": "0",
            "isShowDepart": "1",
            "isDepartUrl": "0",
            "departmentSearch": "1",
            "parentDepartId": "0",
        }
    )
    return result["data"]


def get_teachers(college_id: int, rows: int) -> dict[str, Any]:
    conditions = [
        {"field": "language", "value": 1, "judge": "="},
        {"field": "ownDepartment", "value": college_id, "judge": "="},
        {"field": "title", "value": "", "judge": "like"},
        {"field": "published", "value": 1, "judge": "="},
    ]
    return post_json(
        {
            "siteId": str(college_id),
            "pageIndex": "1",
            "rows": str(rows),
            "conditions": json.dumps(conditions, ensure_ascii=False, separators=(",", ":")),
            "orders": "",
            "returnInfos": json.dumps(TEACHER_RETURN_INFOS, ensure_ascii=False, separators=(",", ":")),
            "articleType": "1",
            "level": "0",
            "deptTecOrder": "1_1",
            "pageEvent": "dataSearchByPageIndex",
        }
    )


def parse_teacher_page(url: str, raw_html: bytes) -> dict[str, Any]:
    text = raw_html.decode("utf-8", errors="replace")
    field_parser = FieldPairParser()
    field_parser.feed(text)
    fields = {key: value for key, value in field_parser.items}

    text_parser = TextParser()
    text_parser.feed(text)
    page_text = clean_text(" ".join(text_parser.parts))

    return {
        "detail_url": url,
        "detail_fields": fields,
        "detail_text": page_text,
    }


def safe_name(value: str) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "_", value, flags=re.UNICODE).strip("_")
    return value or "college"


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = ["collegeId", "collegeName", "title", "department", "degree", "cnUrl"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl Soochow University teacher home data.")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[1] / "data")
    parser.add_argument("--detail-delay-min", type=float, default=0.15)
    parser.add_argument("--detail-delay-max", type=float, default=0.35)
    parser.add_argument("--pause-every", type=int, default=10)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    args = parser.parse_args()

    data_dir = args.data_dir
    by_college_dir = data_dir / "teachers_by_college"
    data_dir.mkdir(parents=True, exist_ok=True)
    by_college_dir.mkdir(parents=True, exist_ok=True)

    all_colleges = get_all_colleges()
    college_by_id = {int(item["collegeId"]): item for item in all_colleges}
    selected = []
    for college in SELECTED_COLLEGES:
        college_id = college["collegeId"]
        if college_id not in college_by_id:
            raise RuntimeError(f"collegeId not found in source data: {college_id}")
        selected.append(college_by_id[college_id])

    write_json(data_dir / "colleges_all.json", all_colleges)
    write_json(data_dir / "colleges_selected.json", selected)

    all_teachers: list[dict[str, Any]] = []
    detail_errors: list[dict[str, str]] = []
    detail_count = 0

    for college in selected:
        college_id = int(college["collegeId"])
        college_name = str(college["fullDepartName"])
        rows = int(college["count"])
        print(f"Fetching {college_name}: {rows} teachers")
        result = get_teachers(college_id, rows)
        teachers = result["data"]
        college_rows: list[dict[str, Any]] = []

        for teacher in teachers:
            detail_url = teacher.get("cnUrl", "")
            record = {
                "collegeId": college_id,
                "collegeName": college_name,
                "source_college": college,
                **teacher,
            }
            if detail_url:
                full_url = urljoin(BASE_URL, detail_url)
                try:
                    detail = parse_teacher_page(full_url, fetch_bytes(full_url))
                    record.update(detail)
                    detail_count += 1
                except Exception as exc:
                    detail_errors.append({"url": full_url, "error": str(exc)})
                if args.pause_every > 0 and detail_count % args.pause_every == 0:
                    time.sleep(args.pause_seconds)
                else:
                    time.sleep(random.uniform(args.detail_delay_min, args.detail_delay_max))
            college_rows.append(record)
            all_teachers.append(record)

        write_jsonl(by_college_dir / f"{college_id}_{safe_name(college_name)}.jsonl", college_rows)

    write_jsonl(data_dir / "teachers.jsonl", all_teachers)
    write_csv(data_dir / "teachers.csv", all_teachers)
    write_json(
        data_dir / "crawl_summary.json",
        {
            "source": BASE_URL,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "selected_college_count": len(selected),
            "teacher_count": len(all_teachers),
            "detail_page_success_count": detail_count,
            "detail_page_error_count": len(detail_errors),
            "detail_page_errors": detail_errors,
            "selected_colleges": selected,
        },
    )
    print(f"Wrote {len(all_teachers)} teachers to {data_dir}")


if __name__ == "__main__":
    main()
