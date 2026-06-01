"""回复规则页"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QComboBox, QTextEdit, QLabel, QScrollArea
)
from PyQt6.QtCore import Qt


class RulesTab(QScrollArea):
    def __init__(self, settings: dict):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)

        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 模式
        mode_group = QGroupBox("判断模式")
        mode_layout = QVBoxLayout(mode_group)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["关键词 + AI 判断（推荐）", "仅关键词（不调用 AI 判断）"])
        current = settings.get("skip_mode", "keyword_then_ai")
        self.mode_combo.setCurrentIndex(0 if current == "keyword_then_ai" else 1)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addWidget(QLabel("先匹配关键词，未命中再由 AI 判断是否回复"))
        layout.addWidget(mode_group)

        # 跳过关键词
        skip_group = QGroupBox("跳过关键词（精确匹配）")
        skip_layout = QVBoxLayout(skip_group)
        self.skip_edit = QTextEdit()
        self.skip_edit.setFixedHeight(100)
        self.skip_edit.setPlaceholderText("每行一个，如：👍")
        self.skip_edit.setPlainText("\n".join(settings.get("skip_keywords", [])))
        skip_layout.addWidget(self.skip_edit)
        layout.addWidget(skip_group)

        # 强制回复关键词
        force_group = QGroupBox("强制回复关键词（包含匹配）")
        force_layout = QVBoxLayout(force_group)
        self.force_edit = QTextEdit()
        self.force_edit.setFixedHeight(100)
        self.force_edit.setPlaceholderText("每行一个，如：帮我")
        self.force_edit.setPlainText("\n".join(settings.get("force_reply_keywords", [])))
        force_layout.addWidget(self.force_edit)
        layout.addWidget(force_group)

        layout.addStretch()
        self.setWidget(widget)

    def collect(self) -> dict:
        skip = [l.strip() for l in self.skip_edit.toPlainText().split("\n") if l.strip()]
        force = [l.strip() for l in self.force_edit.toPlainText().split("\n") if l.strip()]
        mode = "keyword_then_ai" if self.mode_combo.currentIndex() == 0 else "keyword_only"
        return {"skip_keywords": skip, "force_reply_keywords": force, "skip_mode": mode}
