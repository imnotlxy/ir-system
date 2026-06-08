"""Main window of the IR system GUI."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from client.api_client import SearchApiClient, SearchResult
from client.compare_dialog import CompareDialog
from client.detail_dialog import DetailDialog
from client.styles import ADDITIONAL_QSS

PAGE_SIZE = 20


class SearchWorker(QThread):
    """Background thread for search operations."""

    results_ready = pyqtSignal(list, float, str)  # results, elapsed, mode_info
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        api_client: SearchApiClient,
        query: str,
        match_mode: str,
        ranking: str,
        college_filter: list[str],
        research_filter: str,
        auto_relax: bool,
        search_field: str = "",
        is_baseline: bool = False,
    ):
        super().__init__()
        self.api_client = api_client
        self.query = query
        self.match_mode = match_mode
        self.ranking = ranking
        self.college_filter = college_filter
        self.research_filter = research_filter
        self.auto_relax = auto_relax
        self.search_field = search_field
        self.is_baseline = is_baseline

    def run(self) -> None:
        try:
            results, elapsed, mode_info = self.api_client.search(
                self.query,
                match_mode=self.match_mode,
                ranking=self.ranking,
                college_filter=self.college_filter if self.college_filter else None,
                research_filter=self.research_filter,
                auto_relax=self.auto_relax,
                search_field=self.search_field,
                baseline=self.is_baseline,
            )
            self.results_ready.emit(results, elapsed, mode_info)
        except Exception as e:
            self.error_occurred.emit(str(e))


class MainWindow(QMainWindow):
    """Main application window for the IR system."""

    def __init__(self, api_url: str = "http://127.0.0.1:8000"):
        super().__init__()
        self.api_client = SearchApiClient(api_url)
        self.record_count = 0
        self.college_names: list[str] = []
        self.current_results: list[SearchResult] = []
        self.baseline_results: list[SearchResult] = []
        self.current_page = 0
        self._current_theme = "auto"  # "auto", "dark", "light"
        self.search_field = ""  # "" means all fields, "name" / "papers" for field-specific
        self._search_worker: SearchWorker | None = None
        self._baseline_worker: SearchWorker | None = None

        self.setWindowTitle("苏州大学导师信息垂直检索系统")
        self.setMinimumSize(1200, 750)
        self.resize(1400, 850)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 12, 16, 12)

        # Top: search bar
        main_layout.addLayout(self._build_search_bar())

        # Middle: options + results
        middle_layout = QHBoxLayout()
        middle_layout.addWidget(self._build_options_panel(), 0)
        middle_layout.addWidget(self._build_results_area(), 1)
        main_layout.addLayout(middle_layout, 1)

        # Bottom: status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 — 请输入查询词开始检索")

    def _build_search_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText('输入查询词，如"自然语言处理"、"周国栋"、"知识图谱"…')
        self.search_input.returnPressed.connect(self._on_search)
        layout.addWidget(self.search_input, 1)

        self.search_btn = QPushButton("搜 索")
        self.search_btn.setObjectName("searchBtn")
        self.search_btn.clicked.connect(self._on_search)
        layout.addWidget(self.search_btn)

        # Field-specific search buttons (radio-like)
        self._field_btn_group = QButtonGroup(self)
        self._field_btn_group.setExclusive(True)

        self.field_btn_all = QPushButton("全部字段")
        self.field_btn_all.setObjectName("fieldBtn")
        self.field_btn_all.setCheckable(True)
        self.field_btn_all.setChecked(True)
        self._field_btn_group.addButton(self.field_btn_all)
        self.field_btn_all.clicked.connect(lambda: self._set_search_field(""))
        layout.addWidget(self.field_btn_all)

        self.field_btn_name = QPushButton("姓名")
        self.field_btn_name.setObjectName("fieldBtn")
        self.field_btn_name.setCheckable(True)
        self._field_btn_group.addButton(self.field_btn_name)
        self.field_btn_name.clicked.connect(lambda: self._set_search_field("name"))
        layout.addWidget(self.field_btn_name)

        self.field_btn_papers = QPushButton("论文")
        self.field_btn_papers.setObjectName("fieldBtn")
        self.field_btn_papers.setCheckable(True)
        self._field_btn_group.addButton(self.field_btn_papers)
        self.field_btn_papers.clicked.connect(lambda: self._set_search_field("papers"))
        layout.addWidget(self.field_btn_papers)

        # Theme toggle
        self.theme_btn = QPushButton("切换主题")
        self.theme_btn.setObjectName("themeBtn")
        self.theme_btn.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_btn)

        return layout

    def _build_options_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(280)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)

        # Match mode
        match_group = QGroupBox("匹配模式")
        match_layout = QVBoxLayout(match_group)
        self.radio_exact = QRadioButton("精确匹配")
        self.radio_exact.setChecked(True)
        self.radio_fuzzy = QRadioButton("模糊匹配")
        match_layout.addWidget(self.radio_exact)
        match_layout.addWidget(self.radio_fuzzy)
        layout.addWidget(match_group)

        # Ranking method
        rank_group = QGroupBox("排序方式")
        rank_layout = QVBoxLayout(rank_group)
        self.radio_bm25 = QRadioButton("BM25")
        self.radio_bm25.setChecked(True)
        self.radio_tfidf = QRadioButton("TF-IDF")
        rank_layout.addWidget(self.radio_bm25)
        rank_layout.addWidget(self.radio_tfidf)
        layout.addWidget(rank_group)

        # Query relaxation
        relax_group = QGroupBox("查询优化")
        relax_layout = QVBoxLayout(relax_group)
        self.chk_auto_relax = QCheckBox("结果为空时自动放宽条件")
        self.chk_auto_relax.setChecked(True)
        relax_layout.addWidget(self.chk_auto_relax)
        layout.addWidget(relax_group)

        # College filter
        college_group = QGroupBox("学院过滤")
        college_layout = QVBoxLayout(college_group)
        self.chk_all_colleges = QCheckBox("全部学院")
        self.chk_all_colleges.setChecked(True)
        self.chk_all_colleges.stateChanged.connect(self._on_college_select_all)
        college_layout.addWidget(self.chk_all_colleges)
        self.college_checks: list[QCheckBox] = []
        # Will be populated after data load
        self.college_layout = college_layout
        layout.addWidget(college_group)

        # Research filter
        research_group = QGroupBox("研究领域过滤")
        research_layout = QVBoxLayout(research_group)
        self.research_input = QLineEdit()
        self.research_input.setPlaceholderText("关键词，逗号分隔")
        research_layout.addWidget(self.research_input)
        layout.addWidget(research_group)

        # Compare button
        self.compare_btn = QPushButton("查看对比")
        self.compare_btn.setObjectName("compareBtn")
        self.compare_btn.clicked.connect(self._on_compare)
        layout.addWidget(self.compare_btn)

        layout.addStretch()
        return panel

    def _build_results_area(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 0, 0, 0)

        # Results table
        self.results_table = QTableWidget()
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.doubleClicked.connect(self._on_table_double_click)

        columns = ["姓名", "职称", "学院", "研究方向", "论文代表作（节选）", "联系方式", "操作"]
        self.results_table.setColumnCount(len(columns))
        self.results_table.setHorizontalHeaderLabels(columns)

        header = self.results_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.results_table.setColumnWidth(0, 80)
        self.results_table.setColumnWidth(1, 70)
        self.results_table.setColumnWidth(2, 170)
        self.results_table.setColumnWidth(5, 130)
        self.results_table.setColumnWidth(6, 80)

        layout.addWidget(self.results_table, 1)

        # Pagination
        page_layout = QHBoxLayout()
        page_layout.addStretch()

        self.page_buttons_widget = QWidget()
        self.page_layout_inner = QHBoxLayout(self.page_buttons_widget)
        self.page_layout_inner.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(self.page_buttons_widget)

        self.page_info_label = QLabel("")
        self.page_info_label.setStyleSheet("font-size: 12px; margin-left: 12px;")
        page_layout.addWidget(self.page_info_label)

        page_layout.addStretch()
        layout.addLayout(page_layout)

        return widget

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_data(self) -> None:
        """Load backend metadata and populate UI elements."""
        self.status_bar.showMessage("正在连接检索后端…")
        try:
            metadata = self.api_client.metadata()
        except RuntimeError as e:
            QMessageBox.critical(self, "后端连接失败", str(e))
            self.status_bar.showMessage("后端连接失败")
            return

        # Populate college checkboxes
        self.record_count = int(metadata.get("record_count") or 0)
        self.college_names = list(metadata.get("college_names") or [])
        for college_name in self.college_names:
            chk = QCheckBox(college_name)
            chk.setChecked(True)
            self.college_checks.append(chk)
            self.college_layout.addWidget(chk)

        self.status_bar.showMessage(
            f"后端连接成功 — 共 {self.record_count} 位导师，"
            f"{len(self.college_names)} 个学院"
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _on_search(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            self.status_bar.showMessage("请输入查询词")
            return

        match_mode = "fuzzy" if self.radio_fuzzy.isChecked() else "exact"
        ranking = "tfidf" if self.radio_tfidf.isChecked() else "bm25"
        college_filter = self._get_college_filter()
        research_filter = self.research_input.text().strip()
        auto_relax = self.chk_auto_relax.isChecked()

        self.search_btn.setEnabled(False)
        self.search_input.setEnabled(False)
        self.status_bar.showMessage("正在检索…")

        # Run optimized search
        self._search_worker = SearchWorker(
            self.api_client, query, match_mode, ranking,
            college_filter, research_filter, auto_relax,
            search_field=self.search_field,
        )
        self._search_worker.results_ready.connect(self._on_search_done)
        self._search_worker.error_occurred.connect(self._on_search_error)
        self._search_worker.start()

        # Run baseline search in parallel
        self._baseline_worker = SearchWorker(
            self.api_client, query, "exact", ranking,
            college_filter, "", False, is_baseline=True,
        )
        self._baseline_worker.results_ready.connect(self._on_baseline_done)
        self._baseline_worker.error_occurred.connect(self._on_search_error)
        self._baseline_worker.start()

    def _on_search_done(self, results: list[SearchResult], elapsed: float, mode_info: str) -> None:
        self.search_btn.setEnabled(True)
        self.search_input.setEnabled(True)
        self.current_results = results
        self.current_page = 0
        self._render_page()

        if results:
            self.status_bar.showMessage(
                f"检索完成 — {len(results)} 条结果，耗时 {elapsed:.3f}s，{mode_info}"
            )
        else:
            self.status_bar.showMessage(
                f"检索完成 — 无结果，耗时 {elapsed:.3f}s。尝试切换为模糊匹配或勾选自动放宽条件。"
            )

    def _on_baseline_done(self, results: list[SearchResult], elapsed: float, mode_info: str) -> None:
        self.baseline_results = results

    def _on_search_error(self, msg: str) -> None:
        self.search_btn.setEnabled(True)
        self.search_input.setEnabled(True)
        self.status_bar.showMessage(f"检索出错：{msg}")

    # ------------------------------------------------------------------
    # Results rendering
    # ------------------------------------------------------------------

    def _render_page(self) -> None:
        results = self.current_results
        total = len(results)
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        start = self.current_page * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        page_results = results[start:end]

        self.results_table.setRowCount(len(page_results))

        for row, result in enumerate(page_results):
            r = result.record

            # Name
            self.results_table.setItem(row, 0, QTableWidgetItem(r.name))

            # Career
            self.results_table.setItem(row, 1, QTableWidgetItem(r.career))

            # College
            self.results_table.setItem(row, 2, QTableWidgetItem(r.college))

            # Research
            research = r.research[:60] + "…" if len(r.research) > 60 else r.research
            self.results_table.setItem(row, 3, QTableWidgetItem(research))

            # Papers excerpt
            papers = r.papers[:80] + "…" if len(r.papers) > 80 else r.papers
            self.results_table.setItem(row, 4, QTableWidgetItem(papers))

            # Contact (partially hidden)
            email = r.email
            if email and "@" in email:
                local, domain = email.split("@", 1)
                masked = local[:2] + "***@" + domain
            else:
                masked = email or "—"
            self.results_table.setItem(row, 5, QTableWidgetItem(masked))

            # Detail button
            detail_btn = QPushButton("详情")
            detail_btn.clicked.connect(lambda checked, rec=r: self._show_detail(rec))
            self.results_table.setCellWidget(row, 6, detail_btn)
            self.results_table.setRowHeight(row, 36)

        # Update pagination
        self._render_pagination(total_pages)
        self.page_info_label.setText(f"第 {self.current_page + 1}/{total_pages} 页，共 {total} 条")

    def _render_pagination(self, total_pages: int) -> None:
        # Clear old buttons
        while self.page_layout_inner.count():
            item = self.page_layout_inner.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Prev button
        prev_btn = QPushButton("上一页")
        prev_btn.setObjectName("pageBtn")
        prev_btn.setEnabled(self.current_page > 0)
        prev_btn.clicked.connect(lambda: self._go_page(self.current_page - 1))
        self.page_layout_inner.addWidget(prev_btn)

        # Page number buttons (show at most 7)
        start_page = max(0, self.current_page - 3)
        end_page = min(total_pages, start_page + 7)
        start_page = max(0, end_page - 7)

        for p in range(start_page, end_page):
            btn = QPushButton(str(p + 1))
            btn.setObjectName("pageBtn")
            btn.setCheckable(True)
            btn.setChecked(p == self.current_page)
            btn.clicked.connect(lambda checked, page=p: self._go_page(page))
            self.page_layout_inner.addWidget(btn)

        # Next button
        next_btn = QPushButton("下一页")
        next_btn.setObjectName("pageBtn")
        next_btn.setEnabled(self.current_page < total_pages - 1)
        next_btn.clicked.connect(lambda: self._go_page(self.current_page + 1))
        self.page_layout_inner.addWidget(next_btn)

    def _go_page(self, page: int) -> None:
        self.current_page = page
        self._render_page()

    # ------------------------------------------------------------------
    # Detail dialog
    # ------------------------------------------------------------------

    def _show_detail(self, record) -> None:
        dialog = DetailDialog(record, self)
        dialog.exec()

    def _on_table_double_click(self, index) -> None:
        row = index.row()
        start = self.current_page * PAGE_SIZE
        actual_idx = start + row
        if 0 <= actual_idx < len(self.current_results):
            self._show_detail(self.current_results[actual_idx].record)

    # ------------------------------------------------------------------
    # Compare dialog
    # ------------------------------------------------------------------

    def _on_compare(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.information(self, "提示", "请先输入查询词并执行搜索")
            return

        if not self.current_results and not self.baseline_results:
            QMessageBox.information(self, "提示", "请先执行搜索")
            return

        dialog = CompareDialog(query, self.baseline_results, self.current_results, self)
        dialog.exec()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_search_field(self, field: str) -> None:
        """Set the search field (QButtonGroup handles exclusive toggle)."""
        self.search_field = field

    def _get_college_filter(self) -> list[str]:
        if self.chk_all_colleges.isChecked():
            return []
        return [chk.text() for chk in self.college_checks if chk.isChecked()]

    def _on_college_select_all(self, state) -> None:
        checked = state == Qt.CheckState.Checked.value
        for chk in self.college_checks:
            chk.setChecked(checked)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _toggle_theme(self) -> None:
        # Cycle: auto -> dark -> light -> auto
        cycle = {"auto": "dark", "dark": "light", "light": "auto"}
        self._current_theme = cycle.get(self._current_theme, "auto")
        theme_labels = {"auto": "跟随系统", "dark": "暗色", "light": "亮色"}
        self.theme_btn.setText(f"主题：{theme_labels[self._current_theme]}")
        self._apply_theme()

    def _apply_theme(self) -> None:
        import qdarktheme
        qdarktheme.setup_theme(
            theme=self._current_theme,
            additional_qss=ADDITIONAL_QSS,
            default_theme="dark",
        )
