"""Additional QSS styles on top of qdarktheme base theme."""

# Custom styles that extend qdarktheme's base theme.
# qdarktheme handles all standard widget theming (colors, backgrounds, etc.),
# so we only need to define layout/spacing/sizing overrides here.

ADDITIONAL_QSS = """
/* ---- Font ---- */
QWidget {
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}

/* ---- Search input ---- */
QLineEdit#searchInput {
    padding: 10px 14px;
    font-size: 15px;
}

/* ---- Search button ---- */
QPushButton#searchBtn {
    border-radius: 8px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: bold;
}

/* ---- Field toggle buttons ---- */
QPushButton#fieldBtn {
    border-radius: 6px;
    padding: 5px 14px;
    font-size: 12px;
}
QPushButton#fieldBtn:checked {
    font-weight: bold;
}

/* ---- Group boxes ---- */
QGroupBox {
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 18px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
}

/* ---- Combo box ---- */
QComboBox {
    padding: 5px 10px;
    border-radius: 5px;
    min-width: 140px;
}

/* ---- Check / Radio ---- */
QCheckBox, QRadioButton {
    spacing: 6px;
}

/* ---- Table ---- */
QTableWidget {
    border-radius: 6px;
}
QTableWidget::item {
    padding: 6px 8px;
}
QHeaderView::section {
    padding: 8px 6px;
    font-weight: bold;
}
QTableWidget QPushButton {
    border-radius: 4px;
    padding: 4px 12px;
    font-size: 12px;
}

/* ---- Status bar ---- */
QStatusBar {
    font-size: 12px;
}

/* ---- Pagination ---- */
QPushButton#pageBtn {
    border-radius: 4px;
    padding: 5px 12px;
    min-width: 32px;
}

/* ---- Compare button ---- */
QPushButton#compareBtn {
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: bold;
}

/* ---- Theme toggle ---- */
QPushButton#themeBtn {
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
}

/* ---- Scrollbar ---- */
QScrollBar:vertical {
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* ---- Detail dialog section labels ---- */
QLabel#sectionLabel {
    font-weight: bold;
    font-size: 14px;
    margin-top: 10px;
}

/* ---- Compare dialog summary ---- */
QLabel#compareSummary {
    font-size: 14px;
    font-weight: bold;
    padding: 8px;
}
"""
