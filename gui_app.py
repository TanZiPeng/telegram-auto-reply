"""
博思云 Telegram 自动回复系统 - 入口文件
"""

import sys
from pathlib import Path

# Windows 任务栏图标修复：设置 AppUserModelID 让 Windows 显示自定义图标而非 Python 默认图标
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("bosicloud.autoreply")
except Exception:
    pass

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QPalette, QColor, QIcon

from ui.main_window import MainWindow
from core.config import APP_DIR


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 设置应用级图标
    icon_path = APP_DIR / "logo.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # 浅色调色板
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f8f9fa"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#2c3e50"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f1f3f5"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#2c3e50"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#e9ecef"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#2c3e50"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#4a90d9"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    # 单实例检测
    import tempfile
    lock_file = Path(tempfile.gettempdir()) / "bosicloud_autoreply.lock"
    try:
        lock_fd = open(lock_file, 'w')
        import msvcrt
        msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
    except (IOError, OSError):
        QMessageBox.warning(None, "提示", "程序已在运行中，请勿重复打开。")
        sys.exit(1)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
