# IR System

## 前后端拆分

检索系统已经拆到 `backend` 包中，Qt 客户端通过 HTTP/HTTPS 调用后端 API。

启动后端：

```bash
uv run python -m backend.server --host 127.0.0.1 --port 8000
```

启动 Qt 前端：

```bash
uv run python main.py --api-url http://127.0.0.1:8000
```

如果要直接使用安装后的脚本，也可以运行：

```bash
uv run ir-backend --host 127.0.0.1 --port 8000
uv run ir-client --api-url http://127.0.0.1:8000
```

后端接口：

- `GET /health`：健康检查。
- `GET /metadata`：返回导师总数和学院列表。
- `POST /search`：执行检索，请求体为 JSON，支持 `query`、`match_mode`、`ranking`、`college_filter`、`research_filter`、`auto_relax`、`search_field`、`baseline`。

## 爬虫与数据结构

爬虫位于 `crawler/suda_teachers.py`。重新爬取会保存原始 HTML，并输出 v2 JSONL：

```bash
uv run python -m crawler.suda_teachers
```

如果只想基于已有 `data/raw_pages/*.html` 重新生成结构化数据：

```bash
uv run python -m crawler.suda_teachers --from-cache
```

`data/teachers.jsonl` 每行一位教师，核心结构为：

- `source`：来源信息，包括 `detail_url`、`raw_html_path`、`college_id`、`college_name`、`teacher_id`。
- `profile`：可直接检索和展示的教师信息，包括 `name`、`gender`、`phone`、`email`、`title`、`representative_works`、`research_directions`。
- `text`：从 HTML 提取出的文本结构，包括清洗后的 `full_text` 和轻量段落结构 `sections[].heading / sections[].paragraphs`。
- `raw_api`：教师列表接口返回的原始元数据，便于追溯。

原始 HTML 不嵌入 JSONL，统一保留在 `data/raw_pages/`，JSONL 通过 `source.raw_html_path` 引用。

HTTPS 可以通过 `--certfile` 和 `--keyfile` 启用：

```bash
uv run python -m backend.server --certfile cert.pem --keyfile key.pem
```

## 隐私信息脱敏

公共脱敏组件位于 `common/privacy_sanitizer.py`，两套 IR 系统都可以复用。

```python
from common import sanitize_privacy, sanitize_file_to_file

raw_page = "电话：13800138000 邮箱：sombody@suda.edu.cn"
sanitized_page = sanitize_privacy(raw_page)
# "电话：XXX 邮箱：sombody at suda dot edu dot cn"
```

如果原始页面已经保存到文件，可以继续保留原文件，并另存脱敏副本：

```python
sanitize_file_to_file("data/raw/page.html", "data/sanitized/page.html")
```

脱敏规则：

- 电话号码替换为 `XXX`。
- 邮箱地址替换为 `name at domain dot tld` 形式。
- 支持常见手机号、带区号固话、`400/800` 服务号码、带 `转`/`分机`/`ext` 的号码，以及 `电话`/`Tel`/`Phone` 等标签后的本地号码。
