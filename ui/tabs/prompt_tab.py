"""系统提示词页"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLabel
from PyQt6.QtGui import QFont


class PromptTab(QWidget):
    def __init__(self, settings: dict):
        super().__init__()
        layout = QVBoxLayout(self)

        header = QLabel("系统提示词（定义 AI 的回复风格和角色）:")
        header.setStyleSheet("font-weight: bold; color: #34495e; padding: 4px 0;")
        layout.addWidget(header)

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlainText(settings["system_prompt"])
        self.prompt_edit.setFont(QFont("Microsoft YaHei", 10))
        layout.addWidget(self.prompt_edit)

    def get_prompt(self) -> str:
        return self.prompt_edit.toPlainText()
