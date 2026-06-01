"""
QSS 样式定义 - 浅色主题
"""

LIGHT_THEME = """
QMainWindow {
    background-color: #f8f9fa;
}
QWidget {
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
    color: #2c3e50;
}
QTabWidget::pane {
    border: 1px solid #dee2e6;
    border-radius: 6px;
    background-color: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background-color: #e9ecef;
    border: 1px solid #dee2e6;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 18px;
    margin-right: 3px;
    color: #495057;
}
QTabBar::tab:selected {
    background-color: #ffffff;
    border-bottom: 2px solid #4a90d9;
    color: #2c3e50;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background-color: #f1f3f5;
}
QGroupBox {
    font-weight: bold;
    font-size: 13px;
    color: #34495e;
    border: 1px solid #e0e4e8;
    border-radius: 8px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
    background-color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
}
QLineEdit, QComboBox {
    border: 1px solid #ced4da;
    border-radius: 5px;
    padding: 6px 10px;
    background-color: #ffffff;
    color: #2c3e50;
    selection-background-color: #4a90d9;
}
QLineEdit:focus, QComboBox:focus {
    border: 1.5px solid #4a90d9;
    background-color: #f8fbff;
}
QSpinBox {
    padding: 4px 6px;
    color: #2c3e50;
    background-color: #ffffff;
    selection-background-color: #4a90d9;
}
QTextEdit {
    border: 1px solid #ced4da;
    border-radius: 5px;
    padding: 6px;
    background-color: #ffffff;
    color: #2c3e50;
    selection-background-color: #4a90d9;
}
QTextEdit:focus {
    border: 1.5px solid #4a90d9;
}
QPushButton {
    background-color: #4a90d9;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: bold;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #3a7bc8;
}
QPushButton:pressed {
    background-color: #2e6bb0;
}
QPushButton:disabled {
    background-color: #adb5bd;
    color: #e9ecef;
}
QCheckBox {
    spacing: 8px;
    color: #2c3e50;
}
QListWidget {
    border: 1px solid #dee2e6;
    border-radius: 6px;
    background-color: #ffffff;
    padding: 4px;
    outline: none;
}
QListWidget::item {
    padding: 8px 10px;
    border-radius: 4px;
    margin: 2px 0;
}
QListWidget::item:selected {
    background-color: #e3f0fc;
    color: #2c3e50;
}
QListWidget::item:hover:!selected {
    background-color: #f1f3f5;
}
QLabel {
    color: #495057;
}
QScrollArea {
    background-color: transparent;
    border: none;
}
QScrollBar:vertical {
    background-color: #f1f3f5;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background-color: #ced4da;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #adb5bd;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""
