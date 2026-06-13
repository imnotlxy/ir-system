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

from clients.search_engine import TeacherRecord


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
        tabs.addTab(self._build_research_tab(), "研究方向与项目")
        tabs.addTab(self._build_papers_tab(), "论文")
        layout.addWidget(tabs)

    def _build_info_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        fields = self.record.raw.get("detail_fields", {})
        display_order = [
            ("性别", "性别"),
            ("学位", "学位"),
            ("学历", "学历"),
            ("毕业院校", "毕业院校"),
            ("电子邮箱", "电子邮箱"),
            ("联系电话", "联系电话"),
            ("办公地址", "办公地址"),
            ("通讯地址", "通讯地址"),
            ("邮编", "邮编"),
        ]

        for label_text, key in display_order:
            value = fields.get(key, "")
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

        # Education experience
        edu = fields.get("教育经历", "")
        if edu:
            layout.addWidget(self._section_label("教育经历"))
            layout.addWidget(self._content_label(edu))

        # Work experience
        work = fields.get("工作经历", "")
        if work:
            layout.addWidget(self._section_label("工作经历"))
            layout.addWidget(self._content_label(work))

        # Intro
        intro = fields.get("个人简介", "")
        if intro:
            layout.addWidget(self._section_label("个人简介"))
            layout.addWidget(self._content_label(intro))

        layout.addStretch()
        return widget

    def _build_research_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        fields = self.record.raw.get("detail_fields", {})

        research = fields.get("研究领域", fields.get("研究方向", ""))
        if research:
            layout.addWidget(self._section_label("研究领域"))
            layout.addWidget(self._content_label(research))

        courses = fields.get("开授课程", "")
        if courses:
            layout.addWidget(self._section_label("开授课程"))
            layout.addWidget(self._content_label(courses))

        projects = fields.get("科研项目", "")
        if projects:
            layout.addWidget(self._section_label("科研项目"))
            layout.addWidget(self._content_label(projects))

        honors = fields.get("荣誉及奖励", "")
        if honors:
            layout.addWidget(self._section_label("荣誉及奖励"))
            layout.addWidget(self._content_label(honors))

        enrollment = fields.get("招生信息", "")
        if enrollment:
            layout.addWidget(self._section_label("招生信息"))
            layout.addWidget(self._content_label(enrollment))

        layout.addStretch()
        return widget

    def _build_papers_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        fields = self.record.raw.get("detail_fields", {})

        papers = fields.get("论文", "")
        if papers:
            browser = QTextBrowser()
            browser.setOpenExternalLinks(True)
            browser.setPlainText(papers)
            layout.addWidget(browser)
        else:
            layout.addWidget(QLabel("暂无论文信息"))

        patents = fields.get("专利", "")
        if patents:
            layout.addWidget(self._section_label("专利"))
            layout.addWidget(self._content_label(patents))

        software = fields.get("软件著作", "")
        if software:
            layout.addWidget(self._section_label("软件著作"))
            layout.addWidget(self._content_label(software))

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
