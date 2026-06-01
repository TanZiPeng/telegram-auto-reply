"""静默管理页"""

from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QInputDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from core.utils import load_silence_list, save_silence_list


class SilenceTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        hint = QLabel("静默白名单中的群聊暂停 AI 回复，由人工接管。\n触发预警时自动加入，处理完毕后移除即可恢复。")
        hint.setStyleSheet("color: #6c757d; padding: 6px 0;")
        layout.addWidget(hint)

        self.list_widget = QListWidget()
        self.list_widget.setFont(QFont("Microsoft YaHei", 10))
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("+ 手动添加")
        add_btn.setStyleSheet("QPushButton{background-color:#28a745}QPushButton:hover{background-color:#218838}")
        add_btn.clicked.connect(self._add)
        btn_layout.addWidget(add_btn)

        remove_btn = QPushButton("移除选中（恢复 AI）")
        remove_btn.setStyleSheet("QPushButton{background-color:#e74c3c}QPushButton:hover{background-color:#c0392b}")
        remove_btn.clicked.connect(self._remove)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        layout.addStretch()

        self.refresh()

    def refresh(self):
        self.list_widget.clear()
        data = load_silence_list()
        if not data:
            self.list_widget.addItem("（当前无静默群聊）")
            return
        for cid, info in data.items():
            text = f"群ID: {cid}  |  {info.get('added_at','')}  |  {info.get('reason','')}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, cid)
            self.list_widget.addItem(item)

    def _add(self):
        cid, ok = QInputDialog.getText(self, "添加静默", "请输入群/对话 ID:")
        if ok and cid.strip():
            data = load_silence_list()
            data[cid.strip()] = {"added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "reason": "手动添加"}
            save_silence_list(data)
            self.refresh()

    def _remove(self):
        current = self.list_widget.currentItem()
        if not current:
            QMessageBox.information(self, "提示", "请先选中要移除的群聊")
            return
        cid = current.data(Qt.ItemDataRole.UserRole)
        if cid:
            data = load_silence_list()
            data.pop(str(cid), None)
            save_silence_list(data)
            self.refresh()

    def sync_worker(self, worker):
        """同步静默列表到 worker"""
        if worker:
            worker.silence_list = load_silence_list()
