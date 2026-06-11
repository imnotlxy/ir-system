import argparse
import sys

import qdarktheme
from PyQt6.QtWidgets import QApplication

from client.main_window import MainWindow
from client.styles import ADDITIONAL_QSS


def main():
    parser = argparse.ArgumentParser(description="Run the IR Qt frontend.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    args, qt_args = parser.parse_known_args()

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("苏州大学导师信息垂直检索系统")

    # Apply theme that auto-syncs with the OS theme (light/dark)
    qdarktheme.setup_theme(
        theme="auto", additional_qss=ADDITIONAL_QSS, default_theme="dark"
    )

    window = MainWindow(api_url=args.api_url)
    window.load_data()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
