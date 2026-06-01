"""配置页"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QLineEdit, QSpinBox, QCheckBox, QComboBox, QPushButton, QLabel, QScrollArea
)
from PyQt6.QtCore import Qt, QEvent


class NoScrollSpinBox(QSpinBox):
    """只有鼠标左键点击后才响应滚轮的 SpinBox"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        # 只有主动点击获得焦点后才响应滚轮
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()

    def mousePressEvent(self, event):
        # 点击时才获取焦点
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)


class ConfigTab(QScrollArea):
    def __init__(self, settings: dict):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        # Telegram
        tg_group = QGroupBox("Telegram 配置")
        tg_form = QFormLayout(tg_group)
        tg_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self.api_id = QLineEdit(str(settings["telegram_api_id"]))
        tg_form.addRow("API ID:", self.api_id)
        self.api_hash = QLineEdit(settings["telegram_api_hash"])
        tg_form.addRow("API Hash:", self.api_hash)
        self.folder = QLineEdit(settings["telegram_folder"])
        tg_form.addRow("监听文件夹:", self.folder)
        layout.addWidget(tg_group)

        # AI
        ai_group = QGroupBox("AI 配置")
        ai_form = QFormLayout(ai_group)
        ai_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self.base_url = QLineEdit(settings["ai_base_url"])
        ai_form.addRow("Base URL:", self.base_url)
        self.api_key = QLineEdit(settings["ai_api_key"])
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        ai_form.addRow("API Key:", self.api_key)
        self.model = QLineEdit(settings["ai_model"])
        ai_form.addRow("模型:", self.model)
        self.ai_timeout = NoScrollSpinBox()
        self.ai_timeout.setRange(10, 120)
        self.ai_timeout.setValue(settings.get("ai_timeout", 30))
        self.ai_timeout.setSuffix(" 秒")
        ai_form.addRow("AI 超时:", self.ai_timeout)
        layout.addWidget(ai_group)

        # 回复
        reply_group = QGroupBox("回复配置")
        reply_form = QFormLayout(reply_group)
        reply_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        delay_layout = QHBoxLayout()
        self.delay_min = NoScrollSpinBox()
        self.delay_min.setRange(1, 60)
        self.delay_min.setValue(settings["delay_min"])
        self.delay_min.setMinimumWidth(70)
        delay_layout.addWidget(self.delay_min)
        delay_layout.addWidget(QLabel("~"))
        self.delay_max = NoScrollSpinBox()
        self.delay_max.setRange(1, 120)
        self.delay_max.setValue(settings["delay_max"])
        self.delay_max.setMinimumWidth(70)
        delay_layout.addWidget(self.delay_max)
        delay_layout.addWidget(QLabel("秒"))
        delay_layout.addStretch()
        reply_form.addRow("首条回复延迟:", delay_layout)

        self.context_msgs = NoScrollSpinBox()
        self.context_msgs.setRange(5, 50)
        self.context_msgs.setValue(settings["context_messages"])
        reply_form.addRow("上下文消息数:", self.context_msgs)

        self.debounce = NoScrollSpinBox()
        self.debounce.setRange(3, 60)
        self.debounce.setValue(settings.get("debounce_seconds", 10))
        self.debounce.setSuffix(" 秒")
        reply_form.addRow("消息聚合等待:", self.debounce)

        self.split_check = QCheckBox("启用分条回复")
        self.split_check.setChecked(settings.get("split_reply", True))
        reply_form.addRow(self.split_check)

        split_layout = QHBoxLayout()
        self.split_min = NoScrollSpinBox()
        self.split_min.setRange(1, 30)
        self.split_min.setValue(settings.get("split_delay_min", 2))
        self.split_min.setMinimumWidth(70)
        split_layout.addWidget(self.split_min)
        split_layout.addWidget(QLabel("~"))
        self.split_max = NoScrollSpinBox()
        self.split_max.setRange(1, 60)
        self.split_max.setValue(settings.get("split_delay_max", 5))
        self.split_max.setMinimumWidth(70)
        split_layout.addWidget(self.split_max)
        split_layout.addWidget(QLabel("秒"))
        split_layout.addStretch()
        reply_form.addRow("分条间隔:", split_layout)

        self.webhook = QLineEdit(settings.get("alert_webhook_url", ""))
        self.webhook.setPlaceholderText("企业微信 webhook 地址")
        reply_form.addRow("预警 Webhook:", self.webhook)

        self.silence_reply = QLineEdit(settings.get("silence_auto_reply", ""))
        reply_form.addRow("人工接入回复:", self.silence_reply)
        layout.addWidget(reply_group)

        # 代理
        proxy_group = QGroupBox("代理配置")
        proxy_form = QFormLayout(proxy_group)
        self.proxy_check = QCheckBox("启用代理")
        self.proxy_check.setChecked(settings.get("proxy_enabled", False))
        proxy_form.addRow(self.proxy_check)

        proxy_layout = QHBoxLayout()
        self.proxy_type = QComboBox()
        self.proxy_type.addItems(["socks5", "http"])
        self.proxy_type.setCurrentText(settings.get("proxy_type", "socks5"))
        proxy_layout.addWidget(self.proxy_type)
        self.proxy_host = QLineEdit(settings.get("proxy_host", "127.0.0.1"))
        self.proxy_host.setMinimumWidth(100)
        proxy_layout.addWidget(self.proxy_host)
        self.proxy_port = NoScrollSpinBox()
        self.proxy_port.setRange(1, 65535)
        self.proxy_port.setValue(settings.get("proxy_port", 7890))
        proxy_layout.addWidget(self.proxy_port)
        proxy_layout.addStretch()
        proxy_form.addRow("代理地址:", proxy_layout)
        layout.addWidget(proxy_group)

        layout.addStretch()
        self.setWidget(widget)

    def collect(self) -> dict:
        """收集当前配置值"""
        return {
            "telegram_api_id": self.api_id.text(),
            "telegram_api_hash": self.api_hash.text(),
            "telegram_folder": self.folder.text(),
            "ai_base_url": self.base_url.text(),
            "ai_api_key": self.api_key.text(),
            "ai_model": self.model.text(),
            "ai_timeout": self.ai_timeout.value(),
            "delay_min": self.delay_min.value(),
            "delay_max": self.delay_max.value(),
            "context_messages": self.context_msgs.value(),
            "context_expire_hours": 72,
            "debounce_seconds": self.debounce.value(),
            "split_reply": self.split_check.isChecked(),
            "split_delay_min": self.split_min.value(),
            "split_delay_max": self.split_max.value(),
            "alert_webhook_url": self.webhook.text(),
            "silence_auto_reply": self.silence_reply.text(),
            "proxy_enabled": self.proxy_check.isChecked(),
            "proxy_type": self.proxy_type.currentText(),
            "proxy_host": self.proxy_host.text(),
            "proxy_port": self.proxy_port.value(),
        }
