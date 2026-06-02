"""Common utilities shared by the IR systems."""

from common.privacy_sanitizer import (
    DEFAULT_PHONE_MASK,
    desensitize_text,
    sanitize_file_to_file,
    sanitize_privacy,
    write_sanitized_copy,
)

__all__ = [
    "DEFAULT_PHONE_MASK",
    "desensitize_text",
    "sanitize_file_to_file",
    "sanitize_privacy",
    "write_sanitized_copy",
]
