"""Main window of the IR system GUI."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from client.api_client import SearchApiClient, SearchResult
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
        ranking: str,
        college_filter: list[str] | None,
        research_filter: str,
        auto_relax: bool,
        search_field: str = "",
        llm_rerank: bool = False,
        llm_query_weight: bool = False,
        pinyin_query: bool = False,
    ):
        super().__init__()
        self.api_client = api_client
        self.query = query
        self.ranking = ranking
        self.college_filter = college_filter
        self.research_filter = research_filter
        self.auto_relax = auto_relax
        self.search_field = search_field
        self.llm_rerank = llm_rerank
        self.llm_query_weight = llm_query_weight
        self.pinyin_query = pinyin_query

    def run(self) -> None:
        try:
            results, elapsed, mode_info = self.api_client.search(
                self.query,
                ranking=self.ranking,
                college_filter=self.college_filter,
                research_filter=self.research_filter,
                auto_relax=self.auto_relax,
                search_field=self.search_field,
                llm_rerank=self.llm_rerank,
                llm_query_weight=self.llm_query_weight,
                pinyin_query=self.pinyin_query,
            )
            self.results_ready.emit(results, elapsed, mode_info)
        except Exception as e:
            self.error_occurred.emit(str(e))


class MainWindow(QMainWindow):
    """Main application window for the IR system."""

    def __init__(self, api_url: str = "http://127.0.0.1:8000"):
        super().__init__()
        self.api_client = SearchApiClient(api_url)
        self.advanced = False  # Will be set from backend metadata
        self.record_count = 0
        self.college_names: list[str] = []
        self.current_results: list[SearchResult] = []
        self.current_page = 0
        self._current_theme = "auto"  # "auto", "dark", "light"
        self.search_field = (
            ""  # "" means all fields, "name" / "papers" for field-specific
        )
        self._search_worker: SearchWorker | None = None
        self._search_request_id = 0
        self._search_pending = False
        self._last_query = ""
        self._updating_college_checks = False

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
        self.search_input.setPlaceholderText(
            '输入查询词，如"自然语言处理"、"周国栋"、"zhouguodong"…'
        )
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
        self._update_theme_button()
        self.theme_btn.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_btn)

        return layout

    def _build_options_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(280)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)

        self.match_widget = QWidget()
        match_layout = QVBoxLayout(self.match_widget)
        match_layout.setContentsMargins(0, 0, 0, 0)
        match_layout.addWidget(self._panel_label("查询优化"))
        self.chk_auto_relax = QCheckBox("模糊查询")
        self.chk_auto_relax.setChecked(True)
        match_layout.addWidget(self.chk_auto_relax)
        self.chk_pinyin_query = QCheckBox("拼音姓名查询")
        self.chk_pinyin_query.setToolTip(
            "输入教师姓名全拼或首字母进行匹配，例如 zhouguodong / zgd。"
        )
        match_layout.addWidget(self.chk_pinyin_query)
        self.chk_llm_rerank = QCheckBox("LLM 重排")
        self.chk_llm_rerank.setToolTip(
            "使用 DeepSeek 大模型对前 20 条结果进行相关性重排（仅高级模式可用）"
        )
        match_layout.addWidget(self.chk_llm_rerank)
        self.chk_llm_query_weight = QCheckBox("LLM 查询加权")
        self.chk_llm_query_weight.setToolTip(
            "使用 DeepSeek 大模型为查询词的各部分分配不同权重，"
            "核心关键词权重更高，辅助词权重更低（仅高级模式可用）"
        )
        match_layout.addWidget(self.chk_llm_query_weight)
        layout.addWidget(self.match_widget)

        rank_layout = QVBoxLayout()
        rank_layout.addWidget(self._panel_label("排序方式"))
        self.ranking_combo = QComboBox()
        self.ranking_combo.addItem("BM25", "bm25")
        self.ranking_combo.addItem("TF-IDF", "tfidf")
        rank_layout.addWidget(self.ranking_combo)
        layout.addLayout(rank_layout)

        # College filter
        college_layout = QVBoxLayout()
        college_layout.addWidget(self._panel_label("学院过滤"))
        self.chk_all_colleges = QCheckBox("全部学院")
        self.chk_all_colleges.setTristate(True)
        self.chk_all_colleges.setChecked(True)
        self.chk_all_colleges.clicked.connect(self._on_college_select_all_clicked)
        college_layout.addWidget(self.chk_all_colleges)

        self.college_checks: list[QCheckBox] = []
        # Will be populated after data load
        self.college_layout = college_layout
        layout.addLayout(college_layout)

        # Research filter
        research_layout = QVBoxLayout()
        research_layout.addWidget(self._panel_label("研究领域过滤"))
        self.research_input = QLineEdit()
        self.research_input.setPlaceholderText("关键词，逗号分隔")
        self.research_input.setToolTip(
            "仅过滤导师资料中的研究方向字段，多个关键词用英文逗号分隔。"
        )
        research_layout.addWidget(self.research_input)
        layout.addLayout(research_layout)

        layout.addStretch()

        scroll = QScrollArea()
        scroll.setObjectName("optionsScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(panel)
        scroll.setFixedWidth(300)
        return scroll

    def _build_results_area(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 0, 0, 0)

        # Results table
        self.results_table = QTableWidget()
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.results_table.doubleClicked.connect(self._on_table_double_click)
        vertical_header = self.results_table.verticalHeader()
        assert vertical_header is not None
        vertical_header.setVisible(False)

        columns = [
            "姓名",
            "职称",
            "学院",
            "研究方向",
            "论文代表作（节选）",
            "联系方式",
            "操作",
        ]
        self.results_table.setColumnCount(len(columns))
        self.results_table.setHorizontalHeaderLabels(columns)

        header = self.results_table.horizontalHeader()
        assert header is not None
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

        self.results_state_label = QLabel("请输入查询词开始检索")
        self.results_state_label.setObjectName("resultsStateLabel")
        self.results_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.results_state_label)
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

        # Read advanced flag from backend
        self.advanced = bool(metadata.get("advanced", False))
        self.match_widget.setVisible(self.advanced)

        # Populate college checkboxes
        self.record_count = int(metadata.get("record_count") or 0)
        self.college_names = list(metadata.get("college_names") or [])
        for college_name in self.college_names:
            chk = QCheckBox(college_name)
            chk.setChecked(True)
            chk.stateChanged.connect(self._on_college_child_changed)
            self.college_checks.append(chk)
            self.college_layout.addWidget(chk)
        self._sync_all_colleges_state()

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
            self._show_results_state("请输入查询词开始检索")
            return

        ranking = str(self.ranking_combo.currentData() or "bm25")
        college_filter = self._get_college_filter()
        research_filter = self.research_input.text().strip()
        auto_relax = self.chk_auto_relax.isChecked() if self.advanced else False
        llm_rerank = self.chk_llm_rerank.isChecked() if self.advanced else False
        llm_query_weight = (
            self.chk_llm_query_weight.isChecked() if self.advanced else False
        )
        pinyin_query = self.chk_pinyin_query.isChecked() if self.advanced else False
        if college_filter == []:
            self.current_results = []
            self.current_page = 0
            self._last_query = query
            self._render_page("未选择学院，请至少选择一个学院或勾选全部学院")
            self.status_bar.showMessage("未选择学院 — 不执行检索")
            return

        self._search_request_id += 1
        request_id = self._search_request_id
        self._search_pending = True
        self._last_query = query
        self.current_results = []
        self.search_btn.setEnabled(False)
        self.search_input.setEnabled(False)
        self.status_bar.showMessage("正在检索…")
        self._show_results_state("正在检索…")

        self._search_worker = SearchWorker(
            self.api_client,
            query,
            ranking,
            college_filter,
            research_filter,
            auto_relax,
            search_field=self.search_field,
            llm_rerank=llm_rerank,
            llm_query_weight=llm_query_weight,
            pinyin_query=pinyin_query,
        )
        self._search_worker.results_ready.connect(
            lambda results, elapsed, mode_info, rid=request_id: self._on_search_done(
                rid, results, elapsed, mode_info
            )
        )
        self._search_worker.error_occurred.connect(
            lambda msg, rid=request_id: self._on_search_error(rid, msg)
        )
        self._search_worker.start()

    def _on_search_done(
        self,
        request_id: int,
        results: list[SearchResult],
        elapsed: float,
        mode_info: str,
    ) -> None:
        if request_id != self._search_request_id:
            return
        self._search_pending = False
        self.current_results = results
        self.current_page = 0
        self._render_page()

        if results:
            self.status_bar.showMessage(
                f"检索完成 — {len(results)} 条结果，耗时 {elapsed:.3f}s，{mode_info}"
            )
        else:
            self.status_bar.showMessage(
                f"检索完成 — 无结果，耗时 {elapsed:.3f}s。"
                + ("尝试勾选自动放宽条件。" if self.advanced else "")
            )
        self._update_search_controls()

    def _on_search_error(self, request_id: int, msg: str) -> None:
        if request_id != self._search_request_id:
            return
        self._search_pending = False
        self.current_results = []
        self._render_page(f"检索出错：{msg}")
        self.status_bar.showMessage(f"检索出错：{msg}")
        QMessageBox.warning(self, "检索出错", msg)
        self._update_search_controls()

    # ------------------------------------------------------------------
    # Results rendering
    # ------------------------------------------------------------------

    def _render_page(self, empty_message: str | None = None) -> None:
        results = self.current_results
        total = len(results)
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        start = self.current_page * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        page_results = results[start:end]

        self.results_table.setRowCount(len(page_results))
        self._show_results_state(
            empty_message or ("未找到匹配结果" if total == 0 else "")
        )

        for row, result in enumerate(page_results):
            r = result.record

            # Name
            self._set_table_text(row, 0, r.name)

            # Career
            self._set_table_text(row, 1, r.career)

            # College
            self._set_table_text(row, 2, r.college)

            # Research
            research = r.research[:60] + "…" if len(r.research) > 60 else r.research
            self._set_table_text(row, 3, research, r.research)

            # Papers excerpt
            papers = r.papers[:80] + "…" if len(r.papers) > 80 else r.papers
            self._set_table_text(row, 4, papers, r.papers)

            # Contact (partially hidden)
            email = r.email
            if email and "@" in email:
                local, domain = email.split("@", 1)
                masked = local[:2] + "***@" + domain
            else:
                masked = email or "—"
            self._set_table_text(row, 5, masked, r.email or r.phone)

            # Detail button
            detail_btn = QPushButton("详情")
            detail_btn.clicked.connect(lambda checked, rec=r: self._show_detail(rec))
            self.results_table.setCellWidget(row, 6, detail_btn)
            self.results_table.setRowHeight(row, 36)

        # Update pagination
        self._render_pagination(total_pages)
        self.page_info_label.setText(
            f"第 {self.current_page + 1}/{total_pages} 页，共 {total} 条"
        )

    def _render_pagination(self, total_pages: int) -> None:
        # Clear old buttons
        while self.page_layout_inner.count():
            item = self.page_layout_inner.takeAt(0)
            assert item is not None
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

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
    # Helpers
    # ------------------------------------------------------------------

    def _set_search_field(self, field: str) -> None:
        """Set the search field (QButtonGroup handles exclusive toggle)."""
        self.search_field = field

    def _panel_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("panelLabel")
        return label

    def _get_college_filter(self) -> list[str] | None:
        if self.chk_all_colleges.checkState() == Qt.CheckState.Checked:
            return None
        return [chk.text() for chk in self.college_checks if chk.isChecked()]

    def _on_college_select_all_clicked(self, checked: bool) -> None:
        self._updating_college_checks = True
        for chk in self.college_checks:
            chk.setChecked(checked)
        self._updating_college_checks = False
        self._sync_all_colleges_state()

    def _on_college_child_changed(self) -> None:
        if not self._updating_college_checks:
            self._sync_all_colleges_state()

    def _sync_all_colleges_state(self) -> None:
        self._updating_college_checks = True
        checked_count = sum(1 for chk in self.college_checks if chk.isChecked())
        if checked_count == len(self.college_checks):
            state = Qt.CheckState.Checked
        elif checked_count == 0:
            state = Qt.CheckState.Unchecked
        else:
            state = Qt.CheckState.PartiallyChecked
        self.chk_all_colleges.setCheckState(state)
        self._updating_college_checks = False

    def _set_table_text(
        self, row: int, column: int, text: str, tooltip: str | None = None
    ) -> None:
        item = QTableWidgetItem(text or "—")
        if tooltip:
            item.setToolTip(tooltip)
        self.results_table.setItem(row, column, item)

    def _show_results_state(self, message: str) -> None:
        self.results_state_label.setText(message)
        self.results_state_label.setVisible(bool(message))

    def _update_search_controls(self) -> None:
        self.search_btn.setEnabled(not self._search_pending)
        self.search_input.setEnabled(not self._search_pending)

    def _field_label(self, field: str) -> str:
        return {"": "全部字段", "name": "姓名", "papers": "论文"}.get(field, field)

    def _college_label(self, college_filter: list[str] | None) -> str:
        if college_filter is None:
            return "全部学院"
        return "学院：" + "、".join(college_filter)

    def _ranking_label(self, ranking: str) -> str:
        return {"bm25": "BM25", "tfidf": "TF-IDF"}.get(ranking, ranking.upper())

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _toggle_theme(self) -> None:
        # Cycle: auto -> dark -> light -> auto
        cycle = {"auto": "dark", "dark": "light", "light": "auto"}
        self._current_theme = cycle.get(self._current_theme, "auto")
        self._update_theme_button()
        self._apply_theme()

    def _update_theme_button(self) -> None:
        theme_labels = {"auto": "跟随系统", "dark": "暗色", "light": "亮色"}
        self.theme_btn.setText(f"主题：{theme_labels[self._current_theme]}")

    def _apply_theme(self) -> None:
        import qdarktheme

        qdarktheme.setup_theme(
            theme=self._current_theme,
            additional_qss=ADDITIONAL_QSS,
            default_theme="dark",
        )
