"""Dialog to show detailed teacher information."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from client.api_client import TeacherRecord


class DetailDialog(QDialog):
    """Modal dialog showing full details of a teacher record."""

    def __init__(self, record: TeacherRecord, parent: QWidget | None = None):
        super().__init__(parent)
        self.record = record
        self.setWindowTitle(f"导师详情 - {record.name}")
        self.setMinimumSize(700, 550)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Header
        header = QHBoxLayout()
        name_label = QLabel(self.record.name)
        name_label.setStyleSheet("font-size: 22px; font-weight: bold;")
        header.addWidget(name_label)

        career_label = QLabel(self.record.career)
        career_label.setStyleSheet("font-size: 14px; margin-left: 12px;")
        header.addWidget(career_label)
        header.addStretch()

        college_label = QLabel(self.record.college)
        college_label.setStyleSheet("font-size: 13px;")
        header.addWidget(college_label)
        layout.addLayout(header)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._build_info_tab(), "基本信息")
        tabs.addTab(self._build_sections_tab(), "结构化文本")
        tabs.addTab(self._build_works_tab(), "代表作")
        layout.addWidget(tabs)

    def _build_info_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        display_order = [
            ("姓名", self.record.name),
            ("性别", self.record.gender),
            ("职称", self.record.career),
            ("学院", self.record.college),
            ("电子邮箱", self.record.email),
            ("联系电话", self.record.phone),
            ("研究方向", self.record.research),
            ("原始页面", self.record.detail_url),
        ]

        for label_text, value in display_order:
            if not value:
                continue
            row = QHBoxLayout()
            label = QLabel(f"{label_text}：")
            label.setStyleSheet("font-weight: bold; min-width: 80px;")
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            val = QLabel(value)
            val.setWordWrap(True)
            row.addWidget(label)
            row.addWidget(val, 1)
            layout.addLayout(row)

        layout.addStretch()
        return widget

    def _build_sections_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)

        sections = self.record.sections or self.record.raw.get("text", {}).get("sections", [])
        if sections:
            for section in sections:
                heading = section.get("heading") or "未命名段落"
                paragraphs = [p for p in section.get("paragraphs", []) if p]
                if not paragraphs:
                    continue
                layout.addWidget(self._section_label(heading))
                for paragraph in paragraphs:
                    layout.addWidget(self._content_label(paragraph))
        else:
            layout.addWidget(QLabel("暂无结构化文本"))

        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        return widget

    def _build_works_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        works = self.record.representative_works or []
        if works:
            browser = QTextBrowser()
            browser.setOpenExternalLinks(True)
            browser.setPlainText("\n\n".join(works))
            layout.addWidget(browser)
        else:
            layout.addWidget(QLabel("暂无代表作信息"))
        return widget

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    @staticmethod
    def _content_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label
