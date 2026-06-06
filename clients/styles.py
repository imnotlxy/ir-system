"""QSS stylesheets for light and dark themes."""

LIGHT_THEME = """
QWidget {
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #f5f7fa;
}

/* ---- Search bar ---- */
QLineEdit#searchInput {
    padding: 10px 14px;
    border: 2px solid #d0d5dd;
    border-radius: 8px;
    font-size: 15px;
    background: #ffffff;
    selection-background-color: #3b82f6;
}
QLineEdit#searchInput:focus {
    border-color: #3b82f6;
}

QPushButton#searchBtn {
    background-color: #3b82f6;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton#searchBtn:hover {
    background-color: #2563eb;
}
QPushButton#searchBtn:pressed {
    background-color: #1d4ed8;
}

QPushButton#fieldBtn {
    background-color: #f1f5f9;
    color: #475569;
    border: 2px solid #cbd5e1;
    border-radius: 6px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: normal;
}
QPushButton#fieldBtn:hover {
    background-color: #e2e8f0;
    border-color: #94a3b8;
}
QPushButton#fieldBtn:checked {
    background-color: #3b82f6;
    color: #ffffff;
    border: 2px solid #2563eb;
    font-weight: bold;
}
QPushButton#fieldBtn:checked:hover {
    background-color: #2563eb;
}

/* ---- Group boxes ---- */
QGroupBox {
    font-weight: bold;
    border: 1px solid #d0d5dd;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 18px;
    background-color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #1e293b;
}

/* ---- Combo / Check / Radio ---- */
QComboBox {
    padding: 5px 10px;
    border: 1px solid #d0d5dd;
    border-radius: 5px;
    background: #ffffff;
    min-width: 140px;
}
QComboBox:focus {
    border-color: #3b82f6;
}
QComboBox QAbstractItemView {
    selection-background-color: #3b82f6;
}

QCheckBox, QRadioButton {
    spacing: 6px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
}

/* ---- Table ---- */
QTableWidget {
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    gridline-color: #e2e8f0;
    background-color: #ffffff;
    alternate-background-color: #f8fafc;
    selection-background-color: #dbeafe;
    selection-color: #1e293b;
}
QTableWidget::item {
    padding: 6px 8px;
}
QHeaderView::section {
    background-color: #f1f5f9;
    color: #334155;
    font-weight: bold;
    padding: 8px 6px;
    border: none;
    border-bottom: 2px solid #cbd5e1;
}
QTableWidget QPushButton {
    background-color: #3b82f6;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 4px 12px;
    font-size: 12px;
}
QTableWidget QPushButton:hover {
    background-color: #2563eb;
}

/* ---- Status bar ---- */
QStatusBar {
    background-color: #f1f5f9;
    color: #475569;
    font-size: 12px;
    border-top: 1px solid #e2e8f0;
}

/* ---- Pagination ---- */
QPushButton#pageBtn {
    background-color: #ffffff;
    border: 1px solid #d0d5dd;
    border-radius: 4px;
    padding: 5px 12px;
    min-width: 32px;
}
QPushButton#pageBtn:hover {
    background-color: #e0e7ff;
    border-color: #3b82f6;
}
QPushButton#pageBtn:checked, QPushButton#pageBtn:disabled {
    background-color: #3b82f6;
    color: white;
    border-color: #3b82f6;
}

/* ---- Compare button ---- */
QPushButton#compareBtn {
    background-color: #7c3aed;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: bold;
}
QPushButton#compareBtn:hover {
    background-color: #6d28d9;
}

/* ---- Theme toggle ---- */
QPushButton#themeBtn {
    background-color: transparent;
    border: 1px solid #94a3b8;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
    color: #475569;
}
QPushButton#themeBtn:hover {
    background-color: #e2e8f0;
}

/* ---- Scrollbar ---- */
QScrollBar:vertical {
    background: #f1f5f9;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

DARK_THEME = """
QWidget {
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
    color: #e2e8f0;
}

QMainWindow {
    background-color: #0f172a;
}

QLineEdit {
    padding: 5px 10px;
    border: 1px solid #334155;
    border-radius: 5px;
    background: #1e293b;
    color: #e2e8f0;
}
QLineEdit:focus {
    border-color: #60a5fa;
}

QLineEdit#searchInput {
    padding: 10px 14px;
    border: 2px solid #334155;
    border-radius: 8px;
    font-size: 15px;
    background: #1e293b;
    color: #e2e8f0;
    selection-background-color: #3b82f6;
}
QLineEdit#searchInput:focus {
    border-color: #60a5fa;
}

QPushButton#searchBtn {
    background-color: #3b82f6;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton#searchBtn:hover {
    background-color: #2563eb;
}
QPushButton#searchBtn:pressed {
    background-color: #1d4ed8;
}

QPushButton#fieldBtn {
    background-color: #1e293b;
    color: #94a3b8;
    border: 2px solid #334155;
    border-radius: 6px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: normal;
}
QPushButton#fieldBtn:hover {
    background-color: #334155;
    border-color: #475569;
}
QPushButton#fieldBtn:checked {
    background-color: #3b82f6;
    color: #ffffff;
    border: 2px solid #60a5fa;
    font-weight: bold;
}
QPushButton#fieldBtn:checked:hover {
    background-color: #2563eb;
}

QGroupBox {
    font-weight: bold;
    border: 1px solid #334155;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 18px;
    background-color: #1e293b;
    color: #e2e8f0;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #e2e8f0;
}

QComboBox {
    padding: 5px 10px;
    border: 1px solid #334155;
    border-radius: 5px;
    background: #1e293b;
    color: #e2e8f0;
    min-width: 140px;
}
QComboBox:focus {
    border-color: #60a5fa;
}
QComboBox QAbstractItemView {
    background: #1e293b;
    color: #e2e8f0;
    selection-background-color: #3b82f6;
}

QCheckBox, QRadioButton {
    spacing: 6px;
    color: #cbd5e1;
}

QTableWidget {
    border: 1px solid #334155;
    border-radius: 6px;
    gridline-color: #334155;
    background-color: #1e293b;
    alternate-background-color: #0f172a;
    selection-background-color: #1e3a5f;
    selection-color: #e2e8f0;
    color: #e2e8f0;
}
QTableWidget::item {
    padding: 6px 8px;
}
QHeaderView::section {
    background-color: #0f172a;
    color: #94a3b8;
    font-weight: bold;
    padding: 8px 6px;
    border: none;
    border-bottom: 2px solid #334155;
}
QTableWidget QTableCornerButton::section {
    background-color: #0f172a;
    border: none;
}
QHeaderView {
    background-color: #0f172a;
}
QTableWidget QPushButton {
    background-color: #3b82f6;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 4px 12px;
    font-size: 12px;
}
QTableWidget QPushButton:hover {
    background-color: #2563eb;
}

QStatusBar {
    background-color: #0f172a;
    color: #94a3b8;
    font-size: 12px;
    border-top: 1px solid #334155;
}

QPushButton#pageBtn {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 5px 12px;
    min-width: 32px;
    color: #e2e8f0;
}
QPushButton#pageBtn:hover {
    background-color: #334155;
    border-color: #60a5fa;
}
QPushButton#pageBtn:checked, QPushButton#pageBtn:disabled {
    background-color: #3b82f6;
    color: white;
    border-color: #3b82f6;
}

QPushButton#compareBtn {
    background-color: #7c3aed;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: bold;
}
QPushButton#compareBtn:hover {
    background-color: #6d28d9;
}

QPushButton#themeBtn {
    background-color: transparent;
    border: 1px solid #475569;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
    color: #94a3b8;
}
QPushButton#themeBtn:hover {
    background-color: #334155;
}

QScrollBar:vertical {
    background: #0f172a;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #334155;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #475569;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QLabel {
    color: #e2e8f0;
}

QTextEdit {
    background-color: #1e293b;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 5px;
}

QDialog {
    background-color: #0f172a;
}
"""
