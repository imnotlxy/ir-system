"""Utilities for de-identifying page content before storing public copies.

The functions in this module are intentionally side-effect free unless a
``*_copy`` helper is used. IR systems should continue saving the original page
content through their normal path, then call this module to create the separate
privacy-sanitized version.
"""

from __future__ import annotations

import re
from pathlib import Path

DEFAULT_PHONE_MASK = "XXX"
PathInput = str | Path

_EMAIL_RE = re.compile(
    r"""
    (?<![\w.%+-])
    (?P<local>[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+)
    @
    (?P<domain>[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)
    (?![\w.-])
    """,
    re.VERBOSE,
)

_COUNTRY_CODE = r"(?:\(\s*\+?86\s*\)|\+?\s*86)[\s\-.]*"
_EXTENSION = r"(?:[\s\-.]*(?:转|分机|ext\.?|extension|x|\#)\s*\d{1,6})?"

_PHONE_PATTERNS = (
    # Chinese mainland mobile numbers, with optional country code and common
    # separators: 13800138000, +86 138 0013 8000, 138-0013-8000.
    re.compile(
        rf"(?<![\w@])(?:{_COUNTRY_CODE})?1[3-9]\d(?:[\s\-.]?\d){{8}}{_EXTENSION}(?![\w@])",
        re.IGNORECASE,
    ),
    # Landlines with an area code: 0512-12345678, (0512) 12345678,
    # +86-512-12345678. Area-code forms are masked even without a label.
    re.compile(
        rf"(?<![\w@])(?:{_COUNTRY_CODE})?(?:\(\s*0?\d{{2,4}}\s*\)|0?\d{{2,4}})[\s\-.]+\d{{7,8}}{_EXTENSION}(?![\w@])",
        re.IGNORECASE,
    ),
    # Service numbers: 400-123-4567, 8001234567.
    re.compile(
        rf"(?<![\w@])(?:400|800)[\s\-.]?\d{{3}}[\s\-.]?\d{{4}}{_EXTENSION}(?![\w@])",
        re.IGNORECASE,
    ),
)

_LABELED_LOCAL_PHONE_RE = re.compile(
    rf"""
    (?P<label>
        (?:
            电话|手机|传真|联系方式|联系电话|办公电话|咨询电话|服务热线|
            tel(?:ephone)?|phone|mobile|fax
        )
        \s*(?:号码|number)?\s*[:：]?\s*
    )
    (?P<number>
        (?:{_COUNTRY_CODE})?
        (?:
            (?:400|800)[\s\-.]?\d{{3}}[\s\-.]?\d{{4}}
            |
            1[3-9]\d(?:[\s\-.]?\d){{8}}
            |
            \d{{7,8}}
        )
        {_EXTENSION}
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def sanitize_privacy(text: str, *, phone_mask: str = DEFAULT_PHONE_MASK) -> str:
    """Return ``text`` with privacy-sensitive contact details de-identified.

    Rules:
    - Phone numbers are replaced with ``phone_mask`` (``"XXX"`` by default).
    - Email addresses are converted from ``name@example.edu.cn`` to
      ``name at example dot edu dot cn``.

    The original input string is never modified; callers should save the
    returned value as the separate sanitized page version.
    """
    sanitized = _EMAIL_RE.sub(_obfuscate_email, text)
    sanitized = _LABELED_LOCAL_PHONE_RE.sub(
        lambda match: f"{match.group('label')}{phone_mask}", sanitized
    )

    for pattern in _PHONE_PATTERNS:
        sanitized = pattern.sub(phone_mask, sanitized)

    return sanitized


def desensitize_text(text: str, *, phone_mask: str = DEFAULT_PHONE_MASK) -> str:
    """Alias for ``sanitize_privacy`` using project terminology."""
    return sanitize_privacy(text, phone_mask=phone_mask)


def sanitize_file_to_file(
    source_path: PathInput,
    destination_path: PathInput,
    *,
    encoding: str = "utf-8",
    phone_mask: str = DEFAULT_PHONE_MASK,
) -> Path:
    """Read an original page file and write a separate sanitized copy.

    The source file is left untouched. Parent directories for the destination
    are created automatically.
    """
    text = Path(source_path).read_text(encoding=encoding)
    return write_sanitized_copy(
        text,
        Path(destination_path),
        encoding=encoding,
        phone_mask=phone_mask,
    )


def write_sanitized_copy(
    text: str,
    destination_path: PathInput,
    *,
    encoding: str = "utf-8",
    phone_mask: str = DEFAULT_PHONE_MASK,
) -> Path:
    """Write ``text`` after privacy sanitization and return the destination path."""
    destination = Path(destination_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _ = destination.write_text(
        sanitize_privacy(text, phone_mask=phone_mask),
        encoding=encoding,
    )
    return destination


def _obfuscate_email(match: re.Match[str]) -> str:
    local = match.group("local").replace(".", " dot ")
    domain = match.group("domain").replace(".", " dot ")
    return f"{local} at {domain}"
