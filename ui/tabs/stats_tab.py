"""统计面板页"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QGroupBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class StatsTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        group = QGroupBox("运行统计")
        grid = QGridLayout(group)
        grid.setSpacing(16)

        self._labels = {}
        items = [
            ("uptime", "运行时长"),
            ("total_received", "收到消息"),
            ("total_replied", "已回复"),
            ("total_skipped", "已跳过"),
            ("total_alerts", "触发预警"),
            ("total_errors", "错误次数"),
            ("avg_response_time", "平均响应"),
        ]

        for i, (key, title) in enumerate(items):
            row, col = divmod(i, 3)
            title_label = QLabel(title)
            title_label.setStyleSheet("color: #6c757d; font-size: 12px;")
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(title_label, row * 2, col)

            value_label = QLabel("0")
            value_label.setFont(QFont("Consolas", 18, QFont.Weight.Bold))
            value_label.setStyleSheet("color: #2c3e50;")
            value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(value_label, row * 2 + 1, col)
            self._labels[key] = value_label

        layout.addWidget(group)
        layout.addStretch()

    def update_stats(self, data: dict):
        """更新统计数据"""
        for key, label in self._labels.items():
            if key in data:
                label.setText(str(data[key]))
