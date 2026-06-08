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
from urllib.parse import quote, urlencode, urljoin, urlsplit, urlunsplit
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


SECTION_BREAK_TAGS = {"p", "li", "tr", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6"}
DROP_SECTION_TITLES = {"导航", "相关教师"}


class TeacherPageParser(HTMLParser):
    """Extract reusable facts and lightweight paragraph sections from a teacher page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fields: dict[str, str] = {}
        self.sections: list[dict[str, Any]] = []
        self.full_text_parts: list[str] = []
        self._skip_depth = 0
        self._current: dict[str, Any] | None = None
        self._section_depth = 0
        self._active_kind: str | None = None
        self._active_parts: list[str] = []
        self._active_span_depth = 0
        self._pending_field_label: str | None = None
        self._paragraph_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        attr_map = {name: value or "" for name, value in attrs}
        classes = set(attr_map.get("class", "").split())

        if self._active_kind == "field_value":
            if tag == "span":
                self._active_span_depth += 1
            if tag in SECTION_BREAK_TAGS:
                self._active_parts.append("\n")
            return

        if tag == "div" and "post" in classes and "mbox" in classes:
            self._finish_section()
            self._current = {"heading": "", "paragraphs": []}
            self._section_depth = 1
            self._paragraph_parts = []
            return

        if self._current is not None:
            if tag == "div":
                self._section_depth += 1
            if "title" in classes:
                self._start_capture("section_title")
            elif "fws_displayTitle" in classes:
                self._start_capture("field_title")
            elif "fws_displayField" in classes:
                self._start_capture("field_value", span_depth=1)
            elif tag in SECTION_BREAK_TAGS:
                self._finish_paragraph()

    def handle_data(self, data: str) -> None:
        if self._skip_depth or is_noise_text(data):
            return
        if self._active_kind is not None:
            self._active_parts.append(data)
            return
        text = clean_text(data)
        if not text:
            return
        self.full_text_parts.append(text)
        if self._current is not None:
            self._paragraph_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return

        if self._active_kind == "field_value" and tag == "span":
            self._active_span_depth -= 1
            if self._active_span_depth <= 0:
                self._finish_capture()
            return
        if self._active_kind == "field_value":
            if tag in SECTION_BREAK_TAGS:
                self._active_parts.append("\n")
            return

        if self._active_kind is not None and tag == "span":
            self._finish_capture()
            return

        if self._current is not None and tag in SECTION_BREAK_TAGS:
            self._finish_paragraph()

        if self._current is not None and tag == "div":
            self._section_depth -= 1
            if self._section_depth <= 0:
                self._finish_section()

    def close(self) -> None:
        super().close()
        self._finish_section()

    def _start_capture(self, kind: str, span_depth: int = 0) -> None:
        self._active_kind = kind
        self._active_parts = []
        self._active_span_depth = span_depth

    def _finish_capture(self) -> None:
        if self._current is None or self._active_kind is None:
            self._active_kind = None
            self._active_parts = []
            self._active_span_depth = 0
            return

        text = clean_text(" ".join(self._active_parts))
        kind = self._active_kind
        self._active_kind = None
        self._active_parts = []
        self._active_span_depth = 0

        if is_noise_text(text):
            return
        if kind == "section_title" and text:
            self._current["heading"] = text
        elif kind == "field_title":
            self._pending_field_label = text.rstrip("：:")
        elif kind == "field_value" and self._pending_field_label:
            label = self._pending_field_label
            self._pending_field_label = None
            self._add_field(label, text)

    def _add_field(self, label: str, value: str) -> None:
        if label and value and (label not in self.fields or len(value) > len(self.fields[label])):
            self.fields[label] = value
        if value and self._current is not None:
            self._current["paragraphs"].append(f"{label}: {value}")
            self.full_text_parts.append(f"{label}: {value}")

    def _finish_paragraph(self) -> None:
        if self._current is None or not self._paragraph_parts:
            self._paragraph_parts = []
            return
        text = clean_text(" ".join(self._paragraph_parts))
        self._paragraph_parts = []
        if text and not is_noise_text(text):
            self._current["paragraphs"].append(text)

    def _finish_section(self) -> None:
        if self._current is None:
            return
        self._finish_paragraph()
        heading = clean_text(self._current.get("heading", ""))
        paragraphs = dedupe_texts(self._current.get("paragraphs", []))
        if heading not in DROP_SECTION_TITLES and paragraphs:
            self._current["heading"] = heading
            self._current["paragraphs"] = paragraphs
            self.sections.append(self._current)
        self._current = None
        self._section_depth = 0


def clean_text(value: str) -> str:
    value = html.unescape(value).replace("\xa0", " ")
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def dedupe_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = clean_text(value)
        if not text or text in seen or is_noise_text(text) or is_boilerplate_text(text):
            continue
        seen.add(text)
        result.append(text)
    return result


def is_boilerplate_text(value: str) -> bool:
    text = clean_text(value)
    if re.fullmatch(r"\d+\s*访问", text):
        return True
    boilerplate_markers = (
        "Copyright 苏州大学",
        "推荐使用IE",
        "返回首页",
        "欢迎登录",
    )
    return any(marker in text for marker in boilerplate_markers)


def is_noise_text(value: str) -> bool:
    text = clean_text(value)
    if not text:
        return False
    noise_markers = (
        "mso-",
        "@font-face",
        "@page",
        "Style Definitions",
        "font-family:",
        "font-size:",
        "Normal 0",
    )
    return any(marker in text for marker in noise_markers)


def normalize_detail_url(url: str) -> str:
    parts = urlsplit(url)
    path = quote(parts.path, safe="/%")
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


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


def first_value(fields: dict[str, str], keys: list[str]) -> str:
    for key in keys:
        value = clean_text(fields.get(key, ""))
        if value:
            return value
    return ""


def split_numbered_items(text: str, limit: int = 5) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    parts = re.split(r"(?=(?:^|\s)(?:\d{1,2}[、.．]|[\[(（]?\d{1,2}[\])）]))", text)
    items = [clean_text(part) for part in parts if clean_text(part)]
    if len(items) <= 1:
        return [text]
    return items[:limit]


def extract_representative_works(fields: dict[str, str], sections: list[dict[str, Any]]) -> list[str]:
    explicit = first_value(fields, ["代表作", "代表性成果", "代表性论文", "代表论文"])
    if explicit:
        return split_numbered_items(explicit)

    for section in sections:
        paragraphs = section.get("paragraphs", [])
        for idx, paragraph in enumerate(paragraphs):
            if "代表作" not in paragraph and "代表性论文" not in paragraph:
                continue
            marker_text = re.split(r"代表作(?:（[^）]*）)?|代表性论文", paragraph, maxsplit=1)
            if len(marker_text) == 2 and marker_text[1].strip():
                inline_works = split_numbered_items(marker_text[1])
                if inline_works:
                    return inline_works
            works: list[str] = []
            for candidate in paragraphs[idx + 1 :]:
                if re.search(r"科研项目|招生信息|教育经历|工作经历|研究方向|研究领域", candidate):
                    break
                if re.match(r"^\s*\d{1,2}[、.．]", candidate) or re.search(r"\b(KDD|ICML|AAAI|WWW|IEEE|ACM|SCI|CCF)\b", candidate):
                    works.append(clean_text(candidate))
                if len(works) >= 5:
                    break
            if works:
                return works

    papers = first_value(fields, ["论文"])
    return split_numbered_items(papers, limit=5)


def build_profile(raw_teacher: dict[str, Any], fields: dict[str, str], sections: list[dict[str, Any]]) -> dict[str, Any]:
    research = first_value(fields, ["研究方向", "研究领域"])
    career = clean_text(str(raw_teacher.get("career", "")))
    return {
        "name": clean_text(str(raw_teacher.get("title", ""))),
        "gender": first_value(fields, ["性别"]),
        "phone": first_value(fields, ["联系电话", "办公电话", "电话"]),
        "email": first_value(fields, ["电子邮箱", "邮箱", "Email", "E-mail"]),
        "title": first_value(fields, ["专业技术职务", "职称"]) or career,
        "representative_works": extract_representative_works(fields, sections),
        "research_directions": research,
    }


def parse_teacher_page(url: str, raw_html: bytes, raw_html_path: Path, raw_teacher: dict[str, Any]) -> dict[str, Any]:
    text = raw_html.decode("utf-8", errors="replace")
    parser = TeacherPageParser()
    parser.feed(text)
    parser.close()
    fields = parser.fields
    sections = [
        section
        for section in parser.sections
        if section.get("heading") or section.get("paragraphs")
    ]
    profile = build_profile(raw_teacher, fields, sections)
    section_text = " ".join(
        paragraph
        for section in sections
        for paragraph in section.get("paragraphs", [])
    )
    full_text = clean_text(
        " ".join(
            str(value)
            for value in [
                profile.get("name", ""),
                profile.get("gender", ""),
                profile.get("phone", ""),
                profile.get("email", ""),
                profile.get("title", ""),
                profile.get("research_directions", ""),
                " ".join(profile.get("representative_works", [])),
                section_text,
            ]
            if value
        )
    )

    return {
        "schema_version": 2,
        "source": {
            "detail_url": url,
            "raw_html_path": raw_html_path.as_posix(),
            "college_id": raw_teacher.get("collegeId"),
            "college_name": raw_teacher.get("collegeName", ""),
            "teacher_id": raw_teacher.get("columnId"),
        },
        "profile": profile,
        "text": {
            "full_text": full_text,
            "sections": sections,
        },
        "raw_api": raw_teacher,
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
    columns = [
        "college_id",
        "college_name",
        "name",
        "gender",
        "phone",
        "email",
        "title",
        "research_directions",
        "detail_url",
        "raw_html_path",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            source = row.get("source", {})
            profile = row.get("profile", {})
            writer.writerow(
                {
                    "college_id": source.get("college_id", ""),
                    "college_name": source.get("college_name", ""),
                    "name": profile.get("name", ""),
                    "gender": profile.get("gender", ""),
                    "phone": profile.get("phone", ""),
                    "email": profile.get("email", ""),
                    "title": profile.get("title", ""),
                    "research_directions": profile.get("research_directions", ""),
                    "detail_url": source.get("detail_url", ""),
                    "raw_html_path": source.get("raw_html_path", ""),
                }
            )


def make_empty_record(raw_teacher: dict[str, Any], detail_url: str = "", raw_html_path: Path | None = None) -> dict[str, Any]:
    path = raw_html_path.as_posix() if raw_html_path else ""
    return {
        "schema_version": 2,
        "source": {
            "detail_url": detail_url,
            "raw_html_path": path,
            "college_id": raw_teacher.get("collegeId"),
            "college_name": raw_teacher.get("collegeName", ""),
            "teacher_id": raw_teacher.get("columnId"),
        },
        "profile": build_profile(raw_teacher, {}, []),
        "text": {"full_text": "", "sections": []},
        "raw_api": raw_teacher,
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def rebuild_from_cached_pages(data_dir: Path) -> list[dict[str, Any]]:
    old_path = data_dir / "teachers.jsonl"
    if not old_path.exists():
        raise FileNotFoundError(f"cached teacher metadata not found: {old_path}")

    rebuilt: list[dict[str, Any]] = []
    for old in load_jsonl(old_path):
        raw_api = old.get("raw_api") or {
            key: value
            for key, value in old.items()
            if key not in {"detail_fields", "detail_sections", "search_text", "detail_text"}
        }
        raw_api.setdefault("collegeId", old.get("collegeId") or old.get("source", {}).get("college_id"))
        raw_api.setdefault("collegeName", old.get("collegeName") or old.get("source", {}).get("college_name", ""))
        raw_api.setdefault("title", old.get("title") or old.get("profile", {}).get("name", ""))
        raw_api.setdefault("career", old.get("career") or old.get("profile", {}).get("title", ""))
        raw_api.setdefault("columnId", old.get("columnId") or old.get("source", {}).get("teacher_id"))

        raw_html_path_text = old.get("raw_html_path") or old.get("source", {}).get("raw_html_path", "")
        detail_url = old.get("detail_url") or old.get("source", {}).get("detail_url", "")
        if raw_html_path_text:
            raw_html_path = Path(raw_html_path_text)
            if not raw_html_path.is_absolute():
                raw_html_path = data_dir.parent / raw_html_path
            raw_html = raw_html_path.read_bytes()
            relative_path = raw_html_path.relative_to(data_dir.parent)
            rebuilt.append(parse_teacher_page(detail_url, raw_html, relative_path, raw_api))
        else:
            rebuilt.append(make_empty_record(raw_api, detail_url=detail_url))
    return rebuilt


def write_outputs(data_dir: Path, rows: list[dict[str, Any]], selected: list[dict[str, Any]], detail_errors: list[dict[str, str]]) -> None:
    by_college_dir = data_dir / "teachers_by_college"
    by_college_dir.mkdir(parents=True, exist_ok=True)

    rows_by_college: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        college_id = int(row.get("source", {}).get("college_id") or 0)
        rows_by_college.setdefault(college_id, []).append(row)

    for college_id, college_rows in rows_by_college.items():
        college_name = str(college_rows[0].get("source", {}).get("college_name") or college_id)
        write_jsonl(by_college_dir / f"{college_id}_{safe_name(college_name)}.jsonl", college_rows)

    write_jsonl(data_dir / "teachers.jsonl", rows)
    write_csv(data_dir / "teachers.csv", rows)
    write_json(
        data_dir / "crawl_summary.json",
        {
            "source": BASE_URL,
            "schema_version": 2,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "selected_college_count": len(selected),
            "teacher_count": len(rows),
            "detail_page_success_count": sum(1 for row in rows if row.get("source", {}).get("raw_html_path")),
            "detail_page_error_count": len(detail_errors),
            "detail_page_errors": detail_errors,
            "selected_colleges": selected,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl Soochow University teacher home data.")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[1] / "data")
    parser.add_argument("--from-cache", action="store_true", help="Rebuild v2 JSON/CSV from saved raw HTML pages.")
    parser.add_argument("--detail-delay-min", type=float, default=0.15)
    parser.add_argument("--detail-delay-max", type=float, default=0.35)
    parser.add_argument("--pause-every", type=int, default=10)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    args = parser.parse_args()

    data_dir = args.data_dir
    by_college_dir = data_dir / "teachers_by_college"
    raw_pages_dir = data_dir / "raw_pages"
    data_dir.mkdir(parents=True, exist_ok=True)
    by_college_dir.mkdir(parents=True, exist_ok=True)
    raw_pages_dir.mkdir(parents=True, exist_ok=True)

    if args.from_cache:
        selected_path = data_dir / "colleges_selected.json"
        selected = json.loads(selected_path.read_text(encoding="utf-8")) if selected_path.exists() else []
        rows = rebuild_from_cached_pages(data_dir)
        write_outputs(data_dir, rows, selected, [])
        print(f"Rebuilt {len(rows)} v2 teacher records from cached raw pages in {data_dir}")
        return

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
            v2_record = make_empty_record(record)
            if detail_url:
                full_url = normalize_detail_url(urljoin(BASE_URL, detail_url))
                try:
                    raw_html = fetch_bytes(full_url)
                    raw_html_path = raw_pages_dir / f"{college_id}_{teacher.get('columnId', 'unknown')}_{safe_name(str(teacher.get('title', 'teacher')))}.html"
                    raw_html_path.write_bytes(raw_html)
                    v2_record = parse_teacher_page(full_url, raw_html, raw_html_path.relative_to(data_dir.parent), record)
                    detail_count += 1
                except Exception as exc:
                    detail_errors.append({"url": full_url, "error": str(exc)})
                if args.pause_every > 0 and detail_count % args.pause_every == 0:
                    time.sleep(args.pause_seconds)
                else:
                    time.sleep(random.uniform(args.detail_delay_min, args.detail_delay_max))
            college_rows.append(v2_record)
            all_teachers.append(v2_record)

        write_jsonl(by_college_dir / f"{college_id}_{safe_name(college_name)}.jsonl", college_rows)

    write_outputs(data_dir, all_teachers, selected, detail_errors)
    print(f"Wrote {len(all_teachers)} teachers to {data_dir}")


if __name__ == "__main__":
    main()
