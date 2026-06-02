from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from common.privacy_sanitizer import sanitize_file_to_file, sanitize_privacy


class PrivacySanitizerTest(unittest.TestCase):
    def test_obfuscates_suda_email(self) -> None:
        text = "邮箱：sombody@suda.edu.cn"

        sanitized = sanitize_privacy(text)

        self.assertEqual(sanitized, "邮箱：sombody at suda dot edu dot cn")

    def test_obfuscates_email_with_dots_in_local_part(self) -> None:
        text = "Contact first.last@cs.suda.edu.cn for help."

        sanitized = sanitize_privacy(text)

        self.assertEqual(
            sanitized,
            "Contact first dot last at cs dot suda dot edu dot cn for help.",
        )

    def test_masks_common_mobile_number_variants(self) -> None:
        cases = [
            "电话：13800138000",
            "电话：+86 13800138000",
            "电话：(+86) 138 0013 8000",
            "电话：138-0013-8000",
            "电话：138.0013.8000",
            "电话：13800138000 转 123",
        ]

        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(sanitize_privacy(text), "电话：XXX")

    def test_masks_landline_number_variants(self) -> None:
        cases = [
            "办公电话：0512-12345678",
            "办公电话：(0512) 12345678",
            "办公电话：+86-512-12345678",
            "办公电话：0512 12345678 转 1234",
            "办公电话：0512.12345678 ext. 88",
        ]

        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(sanitize_privacy(text), "办公电话：XXX")

    def test_masks_service_numbers(self) -> None:
        cases = [
            "服务热线：400-123-4567",
            "服务热线：4001234567",
            "服务热线：800 123 4567",
        ]

        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(sanitize_privacy(text), "服务热线：XXX")

    def test_masks_labeled_local_phone_but_keeps_label(self) -> None:
        self.assertEqual(sanitize_privacy("联系电话：12345678"), "联系电话：XXX")
        self.assertEqual(sanitize_privacy("Tel: 7654321"), "Tel: XXX")

    def test_does_not_mask_unlabeled_dates_or_short_ids(self) -> None:
        text = "日期 2026-06-02，编号 12345678，邮编 215000。"

        sanitized = sanitize_privacy(text)

        self.assertEqual(sanitized, text)

    def test_can_write_sanitized_copy_without_touching_original(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "raw.html"
            sanitized_path = root / "sanitized" / "page.html"
            original_text = "电话：13800138000 邮箱：sombody@suda.edu.cn"
            _ = original.write_text(original_text, encoding="utf-8")

            result_path = sanitize_file_to_file(original, sanitized_path)

            self.assertEqual(result_path, sanitized_path)
            self.assertEqual(original.read_text(encoding="utf-8"), original_text)
            self.assertEqual(
                sanitized_path.read_text(encoding="utf-8"),
                "电话：XXX 邮箱：sombody at suda dot edu dot cn",
            )


if __name__ == "__main__":
    _ = unittest.main()
