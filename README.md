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
