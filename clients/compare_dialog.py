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

from clients.search_engine import SearchResult


class CompareDialog(QDialog):
    """Side-by-side comparison of baseline and optimized search results."""

    def __init__(
        self,
        query: str,
        baseline_results: list[SearchResult],
        optimized_results: list[SearchResult],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"检索对比 - {query}")
        self.setMinimumSize(1100, 600)
        self._build_ui(query, baseline_results, optimized_results)

    def _build_ui(
        self,
        query: str,
        baseline: list[SearchResult],
        optimized: list[SearchResult],
    ) -> None:
        layout = QVBoxLayout(self)

        # Summary
        summary = QLabel(
            f"查询：\"{query}\"  |  "
            f"基础系统：{len(baseline)} 条结果  |  "
            f"优化系统：{len(optimized)} 条结果"
        )
        summary.setStyleSheet("font-size: 14px; font-weight: bold; padding: 8px;")
        layout.addWidget(summary)

        # Side by side tables
        tables_layout = QHBoxLayout()

        baseline_group = QGroupBox("基础 IR 系统（精确匹配 + BM25）")
        baseline_layout = QVBoxLayout(baseline_group)
        baseline_table = self._create_table(baseline)
        baseline_layout.addWidget(baseline_table)
        tables_layout.addWidget(baseline_group)

        optimized_group = QGroupBox("优化系统（模糊匹配 + 查询放宽 + BM25）")
        optimized_layout = QVBoxLayout(optimized_group)
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
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(0, 50)
        table.setColumnWidth(1, 80)
        table.setColumnWidth(2, 70)
        table.setColumnWidth(3, 160)
        table.setColumnWidth(5, 70)
        table.setColumnWidth(6, 80)

        for row, result in enumerate(results):
            r = result.record
            table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            table.setItem(row, 1, QTableWidgetItem(r.name))
            table.setItem(row, 2, QTableWidgetItem(r.career))
            table.setItem(row, 3, QTableWidgetItem(r.college))

            research = r.research[:40] + "..." if len(r.research) > 40 else r.research
            table.setItem(row, 4, QTableWidgetItem(research))

            score_item = QTableWidgetItem(f"{result.score:.4f}")
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 5, score_item)

            mode = result.match_mode
            if result.relaxed:
                mode += " (放宽)"
            table.setItem(row, 6, QTableWidgetItem(mode))

        return table
