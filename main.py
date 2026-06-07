import sys

import qdarktheme
from PyQt6.QtWidgets import QApplication

from clients.main_window import MainWindow
from clients.styles import ADDITIONAL_QSS


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("苏州大学导师信息垂直检索系统")

    # Apply theme that auto-syncs with the OS theme (light/dark)
    qdarktheme.setup_theme(theme="auto", additional_qss=ADDITIONAL_QSS, default_theme="dark")

    window = MainWindow()
    window.load_data()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
