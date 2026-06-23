# IR System

## 前后端拆分

检索系统已经拆到 `backend` 包中，Qt 客户端通过 HTTP/HTTPS 调用后端 API。

### 普通版

```bash
# 启动后端
uv run python -m backend.server --host 127.0.0.1 --port 8000

# 启动前端
uv run python main.py --api-url http://127.0.0.1:8000
```

### 升级版（--advanced）

升级版启用模糊查询、拼音姓名查询、同义词扩展等高级功能，前端会自动从后端读取状态并显示对应 UI。

```bash
# 启动后端
uv run python -m backend.server --host 127.0.0.1 --port 8001 --advanced

# 启动前端
uv run python main.py --api-url http://127.0.0.1:8001
```

如果要直接使用安装后的脚本，也可以运行：

```bash
uv run ir-backend --host 127.0.0.1 --port 8000
uv run ir-backend --host 127.0.0.1 --port 8001 --advanced
uv run ir-client --api-url http://127.0.0.1:8000
```

## 后端接口

- `GET /health`：健康检查。
- `GET /metadata`：返回导师总数、学院列表及 `advanced` 状态。
- `POST /search`：执行检索，请求体为 JSON，支持 `query`、`ranking`、`college_filter`、`research_filter`、`auto_relax`、`search_field`、`pinyin_query`、`synonym_query`。其中 `auto_relax`、`pinyin_query`、`synonym_query` 仅在后端以 `--advanced` 启动时生效；`pinyin_query=true` 支持用教师姓名全拼和首字母匹配，例如 `zhouguodong` / `zgd` 命中“周国栋”。

  主搜索引擎会把分词结果、倒排索引、文档频率、文档长度和学院列表缓存到 `data/search_index/index.json`。启动后端或调用 `SearchEngine.load_data()` 时，如果缓存与 `data/teachers.jsonl` 的大小和修改时间匹配，会直接加载缓存；否则会自动重建并写回 `data/`。

  高级模式下可通过 `synonym_query=true` 启用查询期同义词扩展。词表位于 `data/synonyms.json`，格式为 `{ "标准词": ["同义词", "缩写"] }`。检索时同一查询词的原词与同义词按 OR 连接，不同查询词仍按 AND 连接；例如查询 `KG` 可以命中资料中的 `知识图谱`。修改同义词表后重启后端即可生效，无需重建搜索索引。

- `POST /experimental-query`：实验性模拟查询接口，基于预构建倒排索引，兼容别名 `POST /query`。请求体示例：

  ```json
  {
    "name": "xxx",
    "collegeId": 1,
    "keywords": ["xxx", "yyy"]
  }
  ```

  `name` 和 `collegeId` 可为 `null`；`keywords` 中所有关键词按 OR 连接。返回体为 `{ "results": [...] }`，结果条目与 `data/teachers_by_college/` 中教师记录保持一致，但移除了 `text`、`detail_fields`、`detail_sections`、`search_text` 等正文内容字段。

  倒排索引预构建在 `data/experimental_query_index/index.json`。如果 `data/teachers_by_college/` 更新，可重新生成：

  ```bash
  uv run python -m backend.experimental_query
  # 或安装脚本后：uv run ir-build-experimental-index
  ```

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

## Benchmark 测试报告

测试日期：2026-06-23

本轮运行命令：

```bash
uv run python -m bench.benchmark --include-llm
uv run python -m bench.related_benchmark
uv run python -m unittest discover -s tests
```

### 搜索词 -> 教师

评测集：`bench/cases.json`，共 19 条。指标为 Hit@1 / Hit@5，默认排序为 BM25。

| 配置 | Hit@1 | Hit@5 | 说明 |
|---|---:|---:|---|
| baseline | 7/19 (37%) | 7/19 (37%) | 精确匹配基线 |
| fuzzy | 7/19 (37%) | 13/19 (68%) | 自动放宽主要提升召回，Top-1 无提升 |
| pinyin | 13/19 (68%) | 13/19 (68%) | 拼音全拼/首字母查询收益明显 |
| synonym | 7/19 (37%) | 10/19 (53%) | 可命中 KG、计科院等同义/简称样例，但排序仍弱 |
| advanced | 13/19 (68%) | 17/19 (89%) | fuzzy + pinyin + synonym 组合 |
| llm-weight | 13/19 (68%) | 17/19 (89%) | LLM 查询加权，本轮与 advanced 持平 |
| llm-rerank | 16/19 (84%) | 17/19 (89%) | LLM 重排显著提升 Top-1 |
| llm-all | 16/19 (84%) | 17/19 (89%) | LLM 加权 + 重排，与单独重排持平 |

关键观察：

- `pinyin` 将 `zgd`、`cuishuang`、`lishoushan`、`lss`、`lpf`、`zhaolei` 等拼音查询提升为 Top-1 命中。
- `fuzzy` 能把 `周国`、`李寿`、部分拼音误触发样例召回到 Top5，但噪声较多，Top-1 没有改善。
- `synonym` 对 `KG`、`KG 陈副教授`、`计科院 计算机网络` 有帮助，但 `知识图谱、教授` 等样例仍存在排序干扰。
- `llm-rerank` 将 `周国`、`知识图谱、教授`、`KG` 等样例从非 Top-1 提升为 Top-1，是本轮最有效的 Top-1 优化。
- `ACM、算法、NLP` 与 `李寿` 仍未进入 Hit@5；`计科院 计算机网络` 命中 Top5 但 Top-1 是唐灯平，杨哲第 2。
- 本轮 `llm-rerank` 在 `李寿` 用例出现一次 DeepSeek 空响应，脚本按设计回退到原排序；汇总指标包含该回退结果。

### 教师 -> 相近教师

评测集：`bench/related_cases.json`，共 15 条，其中单答案 9 条、双答案 6 条。指标为 Hit@1 / Hit@5。

| 指标 | 结果 |
|---|---:|
| Hit@1 | 7/15 (47%) |
| Hit@5 | 12/15 (80%) |

Top-1 未命中的代表样例：

- `李寿山 -> 周国栋/王红玲`：Top-1 为张栋，周国栋第 4。
- `赵雷 -> 陈伟/许佳捷`：Top-1 为章晓芳，许佳捷第 2。
- `陈伟 -> 赵雷/崔爽`：Top-1 为晁平复，崔爽第 5。
- `王邦军 -> 崔爽/杨壮`：Top-1 为朱哲辰，崔爽第 2。
- `李正华 -> 贡正仙`、`朱晓旭 -> 刘安`、`陈伟 -> 赵雷` 未进入 Top5。

结论：相近教师功能当前召回可用，但 Top-1 排序空间较大。主要问题是通用文本相似、同学院、同职称加分会压过更细粒度的研究方向判断。

### 单元测试

`uv run python -m unittest discover -s tests` 运行 38 个测试，全部通过。
