"""
主窗口 - 系统托盘 + 标签页管理 + 控制栏 + 手动发送
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QMessageBox, QInputDialog, QLineEdit,
    QSystemTrayIcon, QMenu, QComboBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QPixmap, QPainter, QColor, QIcon, QPalette

from core.config import load_settings, save_settings
from core.bot_worker import BotWorker
from ui.tabs import ConfigTab, LogTab, PromptTab, RulesTab, SilenceTab, StatsTab
from ui.style import LIGHT_THEME


def _create_icon(color: str) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, 56, 56)
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.worker = None
        self.chat_names: dict = {}
        self._init_ui()
        self._init_tray()

    def _init_ui(self):
        self.setWindowTitle("博思云 Telegram 自动回复系统")
        self.setMinimumSize(750, 600)
        self.setStyleSheet(LIGHT_THEME)

        # 窗口图标
        from core.config import APP_DIR
        icon_path = APP_DIR / "logo.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 标签页
        self.tabs = QTabWidget()
        self.config_tab = ConfigTab(self.settings)
        self.log_tab = LogTab()
        self.prompt_tab = PromptTab(self.settings)
        self.rules_tab = RulesTab(self.settings)
        self.silence_tab = SilenceTab()
        self.stats_tab = StatsTab()

        self.tabs.addTab(self.config_tab, "配置")
        self.tabs.addTab(self.log_tab, "运行日志")
        self.tabs.addTab(self.prompt_tab, "系统提示词")
        self.tabs.addTab(self.rules_tab, "回复规则")
        self.tabs.addTab(self.silence_tab, "静默管理")
        self.tabs.addTab(self.stats_tab, "统计")
        layout.addWidget(self.tabs)

        # 手动发送栏
        send_layout = QHBoxLayout()
        self.chat_combo = QComboBox()
        self.chat_combo.setMinimumWidth(200)
        self.chat_combo.setPlaceholderText("选择群聊...")
        send_layout.addWidget(self.chat_combo)
        self.send_input = QLineEdit()
        self.send_input.setPlaceholderText("输入消息手动发送...")
        self.send_input.returnPressed.connect(self._manual_send)
        send_layout.addWidget(self.send_input)
        send_btn = QPushButton("发送")
        send_btn.setFixedWidth(80)
        send_btn.clicked.connect(self._manual_send)
        send_layout.addWidget(send_btn)
        layout.addLayout(send_layout)

        # 控制栏
        control = QWidget()
        control.setObjectName("controlBar")
        control.setStyleSheet("""
            QWidget#controlBar { background-color: #ffffff; border: 1px solid #e0e4e8; border-radius: 8px; }
            QWidget#controlBar QPushButton#startBtn { background-color: #4a90d9; color: white; border: none; border-radius: 6px; padding: 8px 20px; font-weight: bold; }
            QWidget#controlBar QPushButton#startBtn:hover { background-color: #3a7bc8; }
            QWidget#controlBar QPushButton#startBtn:disabled { background-color: #adb5bd; color: #e9ecef; }
            QWidget#controlBar QPushButton#stopBtn { background-color: #e74c3c; color: white; border: none; border-radius: 6px; padding: 8px 20px; font-weight: bold; }
            QWidget#controlBar QPushButton#stopBtn:hover { background-color: #c0392b; }
            QWidget#controlBar QPushButton#stopBtn:disabled { background-color: #adb5bd; color: #e9ecef; }
        """)
        ctrl_layout = QHBoxLayout(control)
        ctrl_layout.setContentsMargins(12, 8, 12, 8)

        self.start_btn = QPushButton("▶  启动")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setFixedSize(120, 38)
        self.start_btn.clicked.connect(self.start_bot)
        ctrl_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("■  停止")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setFixedSize(120, 38)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_bot)
        ctrl_layout.addWidget(self.stop_btn)

        # 保存按钮
        save_btn = QPushButton("保存配置")
        save_btn.setFixedSize(120, 38)
        save_btn.clicked.connect(self._save_config)
        ctrl_layout.addWidget(save_btn)

        ctrl_layout.addStretch()
        self.status_label = QLabel("状态: 未启动")
        self.status_label.setStyleSheet("font-weight: bold;")
        ctrl_layout.addWidget(self.status_label)
        layout.addWidget(control)

    def _init_tray(self):
        """系统托盘"""
        self.tray = QSystemTrayIcon(self)
        from core.config import APP_DIR
        icon_path = APP_DIR / "logo.ico"
        if icon_path.exists():
            self.tray.setIcon(QIcon(str(icon_path)))
        else:
            self.tray.setIcon(_create_icon("#4a90d9"))
        self.tray.setToolTip("博思云自动回复")

        menu = QMenu()
        show_action = QAction("显示窗口", self)
        show_action.triggered.connect(self._show_window)
        menu.addAction(show_action)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    # ---- 操作方法 ----

    def _save_config(self):
        """收集所有 tab 的配置并保存（支持热更新）"""
        self.settings.update(self.config_tab.collect())
        self.settings.update(self.rules_tab.collect())
        self.settings["system_prompt"] = self.prompt_tab.get_prompt()
        save_settings(self.settings)
        # 热更新到 worker
        if self.worker:
            self.worker.update_settings(self.settings)
        self.log_tab.append("[配置已保存]", "success")

    def start_bot(self):
        self._save_config()
        if not self.settings["ai_api_key"]:
            QMessageBox.warning(self, "提示", "请先填写 AI API Key")
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("状态: 连接中...")
        self.tray.setIcon(_create_icon("#f39c12"))

        self.worker = BotWorker(self.settings)
        self.worker.log_signal.connect(self.log_tab.append)
        self.worker.status_signal.connect(self._on_status)
        self.worker.login_required.connect(self._on_login)
        self.worker.code_required.connect(self._on_code)
        self.worker.password_required.connect(self._on_password)
        self.worker.silence_updated.connect(self.silence_tab.refresh)
        self.worker.stats_updated.connect(self.stats_tab.update_stats)
        self.worker.chat_names_updated.connect(self._on_chat_names)
        self.worker.start()

    def stop_bot(self):
        if self.worker:
            self.worker.stop()
            self.worker.wait(5000)
            self.worker = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("状态: 已停止")
        self.tray.setIcon(_create_icon("#adb5bd"))
        self.log_tab.append("[已停止]", "info")

    def _on_status(self, status: str):
        status_map = {
            "connecting": ("状态: 连接中...", "#f39c12"),
            "running": ("状态: ● 运行中", "#27ae60"),
            "reconnecting": ("状态: 重连中...", "#e74c3c"),
            "stopped": ("状态: 已停止", "#adb5bd"),
        }
        text, color = status_map.get(status, (f"状态: {status}", "#adb5bd"))
        self.status_label.setText(text)
        self.tray.setIcon(_create_icon(color))
        if status == "stopped":
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def _on_login(self):
        phone, ok = QInputDialog.getText(self, "Telegram 登录", "请输入手机号（如 +8613800138000）:")
        if ok and phone:
            self.worker.provide_phone(phone)
        else:
            self.worker.stop()

    def _on_code(self):
        code, ok = QInputDialog.getText(self, "验证码", "请输入 Telegram 发送的验证码:")
        if ok and code:
            self.worker.provide_code(code)
        else:
            self.worker.stop()

    def _on_password(self):
        pwd, ok = QInputDialog.getText(self, "两步验证", "请输入两步验证密码:", QLineEdit.EchoMode.Password)
        if ok and pwd:
            self.worker.provide_password(pwd)
        else:
            self.worker.stop()

    def _on_chat_names(self, names: dict):
        """更新群名映射到下拉框"""
        self.chat_names = names
        self.chat_combo.clear()
        for cid, name in names.items():
            self.chat_combo.addItem(f"{name} ({cid})", cid)

    def _manual_send(self):
        """手动发送消息"""
        text = self.send_input.text().strip()
        if not text:
            return
        idx = self.chat_combo.currentIndex()
        if idx < 0:
            QMessageBox.information(self, "提示", "请先选择群聊")
            return
        chat_id = self.chat_combo.currentData()
        if self.worker:
            self.worker.send_manual_message(chat_id, text)
            self.log_tab.append(f"[手动发送] -> {chat_id}: {text[:60]}", "reply")
            self.send_input.clear()

    # ---- 窗口/托盘行为 ----

    def _show_window(self):
        self.showNormal()
        self.activateWindow()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    def _quit(self):
        self.stop_bot()
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    def closeEvent(self, event):
        """关闭窗口时最小化到托盘"""
        if self.worker and self.worker.isRunning():
            event.ignore()
            self.hide()
            self.tray.showMessage("博思云自动回复", "程序已最小化到托盘继续运行", QSystemTrayIcon.MessageIcon.Information, 2000)
        else:
            if self.worker:
                self.worker.stop()
                self.worker.wait(3000)
            event.accept()
