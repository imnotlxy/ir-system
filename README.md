# IR System

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
