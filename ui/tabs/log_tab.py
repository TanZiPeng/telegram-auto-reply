"""日志页"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QPushButton
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor


LOG_COLORS = {
    "info": "#2c3e50",
    "success": "#27ae60",
    "error": "#e74c3c",
    "reply": "#2980b9",
    "skip": "#95a5a6",
}


class LogTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #fafbfc;
                border: 1px solid #e0e4e8;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        layout.addWidget(self.log_text)

        clear_btn = QPushButton("清空日志")
        clear_btn.setFixedWidth(120)
        clear_btn.setStyleSheet("QPushButton { background-color: #6c757d; } QPushButton:hover { background-color: #5a6268; }")
        clear_btn.clicked.connect(self.log_text.clear)
        layout.addWidget(clear_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def append(self, msg: str, level: str = "info"):
        color = LOG_COLORS.get(level, "#2c3e50")
        self.log_text.append(f'<span style="color:{color}; font-size:10pt;">{msg}</span>')
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)
