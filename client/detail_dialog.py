"""Dialog to show detailed teacher information."""

from __future__ import annotations

from html import escape

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from client.api_client import RelatedTeacherResult, SearchApiClient, TeacherRecord


class DetailDialog(QDialog):
    """Modal dialog showing full details of a teacher record."""

    def __init__(
        self,
        record: TeacherRecord,
        parent: QWidget | None = None,
        api_client: SearchApiClient | None = None,
    ):
        super().__init__(parent)
        self.record = record
        self.api_client = api_client
        self.related_results: list[RelatedTeacherResult] = []
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

        self.related_btn = QPushButton("查找相近教师")
        self.related_btn.setEnabled(self.api_client is not None)
        self.related_btn.clicked.connect(self._load_related_teachers)
        header.addWidget(self.related_btn)
        layout.addLayout(header)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_info_tab(), "基本信息")
        self.tabs.addTab(self._build_sections_tab(), "结构化文本")
        self.tabs.addTab(self._build_works_tab(), "代表作")
        self.related_tab = self._build_related_tab()
        self.tabs.addTab(self.related_tab, "相近教师")
        layout.addWidget(self.tabs)

    def _build_info_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)

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
            if label_text == "原始页面":
                escaped = escape(value, quote=True)
                val = QLabel(f'<a href="{escaped}">{escaped}</a>')
                val.setOpenExternalLinks(True)
                val.setTextFormat(Qt.TextFormat.RichText)
            else:
                val = QLabel(value)
            val.setWordWrap(True)
            val.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.LinksAccessibleByMouse
            )
            row.addWidget(label)
            row.addWidget(val, 1)
            layout.addLayout(row)

        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)
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

    def _build_related_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.related_state_label = QLabel("点击“查找相近教师”后显示结果")
        self.related_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.related_state_label)

        self.related_table = QTableWidget()
        self.related_table.setAlternatingRowColors(True)
        self.related_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.related_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        columns = ["姓名", "学院", "职称", "相似度", "依据", "操作"]
        self.related_table.setColumnCount(len(columns))
        self.related_table.setHorizontalHeaderLabels(columns)

        header = self.related_table.horizontalHeader()
        assert header is not None
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.related_table.setColumnWidth(0, 90)
        self.related_table.setColumnWidth(1, 180)
        self.related_table.setColumnWidth(2, 80)
        self.related_table.setColumnWidth(3, 70)
        self.related_table.setColumnWidth(5, 70)

        vertical_header = self.related_table.verticalHeader()
        assert vertical_header is not None
        vertical_header.setVisible(False)

        layout.addWidget(self.related_table, 1)
        return widget

    def _load_related_teachers(self) -> None:
        if self.api_client is None:
            return

        self.related_btn.setEnabled(False)
        self.related_state_label.setText("正在查找相近教师…")
        self.tabs.setCurrentWidget(self.related_tab)
        try:
            self.related_results = self.api_client.related_teachers(
                self.record,
                top_k=10,
            )
        except RuntimeError as exc:
            self.related_state_label.setText("查找失败")
            QMessageBox.warning(self, "查找相近教师失败", str(exc))
            return
        finally:
            self.related_btn.setEnabled(True)

        self._render_related_results()

    def _render_related_results(self) -> None:
        self.related_table.setRowCount(len(self.related_results))
        self.related_state_label.setVisible(not self.related_results)
        if not self.related_results:
            self.related_state_label.setText("未找到相近教师")
            return

        for row, result in enumerate(self.related_results):
            record = result.record
            self._set_related_text(row, 0, record.name)
            self._set_related_text(row, 1, record.college)
            self._set_related_text(row, 2, record.career)
            self._set_related_text(row, 3, f"{result.score:.1f}")
            reason_text = "；".join(result.reasons)
            self._set_related_text(row, 4, reason_text, reason_text)

            detail_btn = QPushButton("详情")
            detail_btn.clicked.connect(
                lambda checked, item=record: self._show_related_detail(item)
            )
            self.related_table.setCellWidget(row, 5, detail_btn)
            self.related_table.setRowHeight(row, 36)

    def _show_related_detail(self, record: TeacherRecord) -> None:
        dialog = DetailDialog(record, self, self.api_client)
        dialog.exec()

    def _set_related_text(
        self,
        row: int,
        column: int,
        text: str,
        tooltip: str | None = None,
    ) -> None:
        item = QTableWidgetItem(text or "—")
        if tooltip:
            item.setToolTip(tooltip)
        self.related_table.setItem(row, column, item)

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
