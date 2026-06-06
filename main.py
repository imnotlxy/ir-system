import sys

from PyQt6.QtWidgets import QApplication

from clients.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("苏州大学导师信息垂直检索系统")

    window = MainWindow()
    window.load_data()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
