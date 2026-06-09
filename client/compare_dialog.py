"""Comparison dialog showing baseline vs optimized search results side by side."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from client.api_client import SearchResult


class CompareDialog(QDialog):
    """Side-by-side comparison of baseline and optimized search results."""

    def __init__(
        self,
        query: str,
        baseline_results: list[SearchResult],
        optimized_results: list[SearchResult],
        baseline_label: str,
        optimized_label: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"检索对比 - {query}")
        self.setMinimumSize(1250, 650)
        self._build_ui(
            query, baseline_results, optimized_results, baseline_label, optimized_label
        )

    def _build_ui(
        self,
        query: str,
        baseline: list[SearchResult],
        optimized: list[SearchResult],
        baseline_label: str,
        optimized_label: str,
    ) -> None:
        layout = QVBoxLayout(self)

        # Summary
        summary = QLabel(
            f'查询："{query}"  |  '
            f"基础系统：{len(baseline)} 条结果  |  "
            f"优化系统：{len(optimized)} 条结果"
        )
        summary.setObjectName("compareSummary")
        layout.addWidget(summary)

        # Side by side tables
        tables_layout = QHBoxLayout()

        baseline_group = QGroupBox("基础 IR 系统")
        baseline_layout = QVBoxLayout(baseline_group)
        baseline_config = QLabel(baseline_label)
        baseline_config.setObjectName("compareConfig")
        baseline_config.setWordWrap(True)
        baseline_layout.addWidget(baseline_config)
        baseline_table = self._create_table(baseline)
        baseline_layout.addWidget(baseline_table)
        tables_layout.addWidget(baseline_group)

        optimized_group = QGroupBox("优化系统")
        optimized_layout = QVBoxLayout(optimized_group)
        optimized_config = QLabel(optimized_label)
        optimized_config.setObjectName("compareConfig")
        optimized_config.setWordWrap(True)
        optimized_layout.addWidget(optimized_config)
        optimized_table = self._create_table(optimized)
        optimized_layout.addWidget(optimized_table)
        tables_layout.addWidget(optimized_group)

        layout.addLayout(tables_layout)

    def _create_table(self, results: list[SearchResult]) -> QTableWidget:
        columns = ["排名", "姓名", "职称", "学院", "研究方向", "得分", "匹配模式"]
        table = QTableWidget(len(results), len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        header = table.horizontalHeader()
        assert header is not None
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        vertical_header = table.verticalHeader()
        assert vertical_header is not None
        vertical_header.setVisible(False)
        table.setColumnWidth(0, 50)
        table.setColumnWidth(1, 80)
        table.setColumnWidth(2, 70)
        table.setColumnWidth(3, 170)
        table.setColumnWidth(5, 70)
        table.setColumnWidth(6, 110)

        for row, result in enumerate(results):
            r = result.record
            table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            table.setItem(row, 1, QTableWidgetItem(r.name))
            table.setItem(row, 2, QTableWidgetItem(r.career))
            college_item = QTableWidgetItem(r.college)
            college_item.setToolTip(r.college)
            table.setItem(row, 3, college_item)

            research = r.research[:40] + "..." if len(r.research) > 40 else r.research
            research_item = QTableWidgetItem(research or "—")
            if r.research:
                research_item.setToolTip(r.research)
            table.setItem(row, 4, research_item)

            score_item = QTableWidgetItem(f"{result.score:.4f}")
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 5, score_item)

            mode = result.match_mode
            if result.relaxed:
                mode += " (放宽)"
            table.setItem(row, 6, QTableWidgetItem(mode))

        return table
