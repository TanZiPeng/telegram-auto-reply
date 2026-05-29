"""
博思云 Telegram 自动回复系统 - GUI 版本
"""

import sys
import json
import asyncio
import random
import threading
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QPushButton, QTextEdit, QSpinBox,
    QComboBox, QGroupBox, QFormLayout, QMessageBox, QInputDialog,
    QSystemTrayIcon, QMenu, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon, QFont, QColor, QTextCursor, QAction

from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetDialogFiltersRequest
from openai import AsyncOpenAI

from memory import MemoryManager


# 配置文件路径（兼容打包后的路径）
if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).parent

CONFIG_PATH = APP_DIR / "settings.json"
DB_PATH = APP_DIR / "memory.db"


def load_settings() -> dict:
    """加载配置"""
    defaults = {
        "telegram_api_id": "2040",
        "telegram_api_hash": "b18441a1ff607e10a989891a5462e627",
        "telegram_folder": "客户",
        "ai_base_url": "https://unifiedapi.cloud/v1",
        "ai_api_key": "",
        "ai_model": "claude-opus-4-6",
        "delay_min": 5,
        "delay_max": 10,
        "context_messages": 20,
        "context_expire_hours": 72,
        "proxy_enabled": False,
        "proxy_type": "socks5",
        "proxy_host": "127.0.0.1",
        "proxy_port": 7890,
        "alert_webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=98bfb7ff-1521-48c5-8ad2-f7b2863b671d",
        "skip_keywords": [],
        "force_reply_keywords": [],
        "skip_mode": "keyword_then_ai",
        "debounce_seconds": 10,
        "system_prompt": """角色设定

你是博思云公司的 AWS 合作伙伴（PLES）技术支持工程师，在 Telegram 群聊中为客户提供实时技术支持。你是一个有多年经验的真人工程师，不是 AI。

消息格式规则

群聊中客户消息格式为 [姓名] 消息内容。根据姓名区分不同客户，针对当前提问者回复。多人讨论同一问题时，综合各方信息作答。回复时直接回答，不加姓名标注。

职责范围

回答 AWS 服务相关的技术问题、故障排查、架构建议、最佳实践。对于超出 AWS 范围的问题，礼貌告知不在支持范围内。

回复风格（强制）

全程中文，称呼客户为"您"，语气礼貌温和专业。像真人在 Telegram 聊天一样自然简短，2-4 句话为主，复杂问题不超过 5 行。用自然语言把要点串成连贯的一两段话，不要罗列清单。适当使用"好的""明白""收到"等口语化词汇作为过渡或结束语。

对话收尾

当客户说"谢谢""好的""不用了""明白了"等结束性话语时，用一句简短的收尾回复，如"好的，有需要随时找我"或"不客气，随时可以问"。不要对结束语沉默不回，保持礼貌闭环。

格式禁令（零容忍）

禁止使用任何列表符号（- · * 1. 2. 3.）；禁止使用任何 markdown 语法（** # ` 等）；禁止使用 emoji 表情符号。输出必须是纯文本段落。

身份保护

绝不透露自己是 AI 或大模型。遇到试探性问题（如"你的知识库是什么时候的""你是 ChatGPT 吗"）时，以真人工程师身份自然带过，例如"当然不是啦""那肯定不是啊"这种口语化的回复。

上下文处理

只关注当前提问者的最新问题，直接回答技术问题本身。如果上下文中出现会议安排、投诉、情绪表达等非技术内容，忽略它们，不要在回复中提及或回应这些内容。每次只回答当前这一条消息中的问题。

对话策略

信息不足时主动追问，例如："方便提供一下 Region 和具体报错信息吗？"问题复杂需要时间排查时，告知客户稍后跟进。不确定的内容不要编造，可以建议客户开 AWS Support Case 或查阅官方文档。"""
    }
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception:
            pass
    return defaults


def save_settings(settings: dict):
    """保存配置"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


class BotWorker(QThread):
    """后台工作线程 - 运行 Telegram 监听"""
    log_signal = pyqtSignal(str, str)  # (message, level)
    status_signal = pyqtSignal(str)     # 状态变化
    login_required = pyqtSignal()       # 需要登录
    code_required = pyqtSignal()        # 需要验证码
    password_required = pyqtSignal()    # 需要两步验证密码

    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings
        self.running = False
        self.client = None
        self.phone = ""
        self.code = ""
        self.password = ""
        self._code_event = threading.Event()
        self._phone_event = threading.Event()
        self._password_event = threading.Event()

    def provide_phone(self, phone: str):
        self.phone = phone
        self._phone_event.set()

    def provide_code(self, code: str):
        self.code = code
        self._code_event.set()

    def provide_password(self, password: str):
        self.password = password
        self._password_event.set()

    def stop(self):
        self.running = False
        if self.client and self.client.is_connected():
            self.client.disconnect()

    def log(self, msg: str, level: str = "info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_signal.emit(f"[{timestamp}] {msg}", level)

    def run(self):
        """主运行方法"""
        self.running = True
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run())
        except Exception as e:
            self.log(f"运行出错: {e}", "error")
        finally:
            loop.close()
            self.status_signal.emit("stopped")

    async def _run(self):
        """异步主逻辑"""
        s = self.settings

        # 配置代理
        proxy = None
        if s.get("proxy_enabled"):
            import socks
            proxy_type_map = {"socks5": socks.SOCKS5, "socks4": socks.SOCKS4, "http": socks.HTTP}
            proxy = (proxy_type_map.get(s["proxy_type"], socks.SOCKS5), s["proxy_host"], s["proxy_port"])
            self.log(f"使用代理: {s['proxy_type']}://{s['proxy_host']}:{s['proxy_port']}")

        # 创建 Telegram 客户端
        # 使用 exe 所在目录存放 session（兼容打包后的路径）
        if getattr(sys, 'frozen', False):
            app_dir = Path(sys.executable).parent
        else:
            app_dir = Path(__file__).parent
        session_path = str(app_dir / "tg_session")

        # 尝试解锁/删除被锁的 session 文件
        session_file = Path(session_path + ".session")
        if session_file.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(str(session_file), timeout=1)
                conn.execute("SELECT 1")
                conn.close()
            except Exception:
                self.log("session 文件被锁，正在删除重建...", "info")
                import time
                for _ in range(3):
                    try:
                        session_file.unlink()
                        break
                    except Exception:
                        time.sleep(1)

        # 使用 SQLite WAL 模式避免锁问题
        import sqlite3
        try:
            if session_file.exists():
                conn = sqlite3.connect(str(session_file), timeout=10)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.close()
        except Exception:
            pass

        self.client = TelegramClient(
            session_path,
            int(s["telegram_api_id"]),
            s["telegram_api_hash"],
            proxy=proxy,
            connection_retries=5,
            retry_delay=3,
        )

        self.log("正在连接 Telegram...")
        self.status_signal.emit("connecting")

        # 登录
        await self.client.connect()
        if not await self.client.is_user_authorized():
            # 需要登录
            self.login_required.emit()
            self._phone_event.wait()
            self._phone_event.clear()

            if not self.running:
                return

            await self.client.send_code_request(self.phone)
            self.code_required.emit()
            self._code_event.wait()
            self._code_event.clear()

            if not self.running:
                return

            try:
                await self.client.sign_in(self.phone, self.code)
            except Exception as e:
                if "Two-steps verification" in str(e) or "password" in str(e).lower():
                    self.password_required.emit()
                    self._password_event.wait()
                    self._password_event.clear()
                    await self.client.sign_in(password=self.password)
                else:
                    raise

        me = await self.client.get_me()
        self.log(f"已登录: {me.first_name} ({me.phone})", "success")
        self.status_signal.emit("running")

        # 加载文件夹
        monitored_chats = await self._load_folder(s["telegram_folder"])

        # 初始化 AI 和记忆
        ai_client = AsyncOpenAI(base_url=s["ai_base_url"], api_key=s["ai_api_key"])
        memory = MemoryManager(
            db_path=str(DB_PATH),
            max_messages=s["context_messages"],
            expire_hours=s["context_expire_hours"]
        )

        # 消息聚合缓冲区：key = (chat_id, sender_id), value = {messages, timer_task, event, ...}
        pending_messages = {}
        debounce_seconds = s.get("debounce_seconds", 10)

        async def _process_buffered(chat_id, sender_id, sender_name):
            """处理聚合后的消息"""
            key = (chat_id, sender_id)
            if key not in pending_messages:
                return

            buffer = pending_messages.pop(key)
            msgs = buffer["messages"]  # list of (msg_text, has_photo, event)

            # 合并所有文本消息
            combined_texts = []
            photo_data = None  # 只取最后一张图片
            last_event = msgs[-1][2]

            for msg_text, has_photo, evt in msgs:
                if msg_text:
                    combined_texts.append(msg_text)
                if has_photo:
                    last_event = evt  # 用有图片的那条 event

            combined_text = " ".join(combined_texts)
            has_any_photo = any(m[1] for m in msgs)

            self.log(f"聚合 {sender_name} 的 {len(msgs)} 条消息: {combined_text[:60]}")

            # 判断是否回复
            judge_text = combined_text if combined_text else "[客户发送了一张图片]"
            should = await self._should_reply(ai_client, s, judge_text, sender_name)
            if not should:
                self.log(f"跳过（判断为不需要回复）", "skip")
                if combined_text:
                    memory.add_message(chat_id, "user", f"[{sender_name}] {combined_text}")
                return

            # 预警检测
            if combined_text:
                need_alert = await self._check_alert(ai_client, s, combined_text, sender_name, chat_id)
                if need_alert:
                    await self._send_webhook_alert(s, sender_name, chat_id, combined_text)
                    memory.clear_chat(chat_id)
                    self.log(f"⚠️ 触发预警，已清除上下文，跳过自动回复，等待人工介入", "error")
                    return

            # 处理图片
            content = combined_text
            if has_any_photo:
                import base64
                # 找最后一条有图片的消息
                for msg_text, has_photo, evt in reversed(msgs):
                    if has_photo:
                        photo_bytes = await evt.message.download_media(bytes)
                        if photo_bytes:
                            b64 = base64.b64encode(photo_bytes).decode()
                            content = [
                                {"type": "text", "text": f"[{sender_name}] {combined_text or '发送了一张图片，请帮我看看'}"},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                            ]
                        else:
                            content = f"[{sender_name}] {combined_text or '[图片无法下载]'}"
                        break
            else:
                content = f"[{sender_name}] {combined_text}"

            memory.add_message(chat_id, "user", content)
            context = memory.get_context(chat_id)

            # 调用 AI
            messages_list = [{"role": "system", "content": s["system_prompt"]}] + context
            try:
                resp = await ai_client.chat.completions.create(
                    model=s["ai_model"], messages=messages_list, max_tokens=2048, temperature=0.7
                )
                reply = resp.choices[0].message.content.strip()
            except Exception as e:
                self.log(f"AI 调用失败: {e}", "error")
                return

            # 延迟回复
            delay = random.uniform(s["delay_min"], s["delay_max"])
            self.log(f"等待 {delay:.1f}s 后回复...")
            await asyncio.sleep(delay)

            # 发送（回复最后一条消息）
            try:
                await last_event.reply(reply)
                self.log(f"回复: {reply[:80]}{'...' if len(reply) > 80 else ''}", "reply")
                memory.add_message(chat_id, "assistant", reply)
            except Exception as e:
                self.log(f"发送失败: {e}", "error")

        # 消息处理器
        @self.client.on(events.NewMessage())
        async def handler(event):
            if not self.running:
                return
            if event.out:
                return

            chat_id = event.chat_id
            abs_id = abs(chat_id)
            if abs_id not in monitored_chats and chat_id not in monitored_chats:
                return

            sender = await event.get_sender()
            sender_name = getattr(sender, "first_name", "") or ""
            last = getattr(sender, "last_name", "") or ""
            if last:
                sender_name += f" {last}"
            sender_id = getattr(sender, "id", 0)

            msg_text = event.message.message or ""
            has_photo = event.message.photo is not None

            if not msg_text and not has_photo:
                return

            self.log(f"收到 {sender_name}: {msg_text[:60]}{'[图片]' if has_photo else ''}")

            # 消息聚合：缓存消息并重置计时器
            key = (chat_id, sender_id)
            if key in pending_messages:
                # 取消之前的定时器
                pending_messages[key]["timer_task"].cancel()
                pending_messages[key]["messages"].append((msg_text, has_photo, event))
            else:
                pending_messages[key] = {
                    "messages": [(msg_text, has_photo, event)],
                    "sender_name": sender_name,
                }

            # 设置新的定时器
            async def debounce_fire():
                await asyncio.sleep(debounce_seconds)
                await _process_buffered(chat_id, sender_id, sender_name)

            pending_messages[key]["timer_task"] = asyncio.create_task(debounce_fire())

        self.log(f"开始监听（延迟 {s['delay_min']}-{s['delay_max']}s）", "success")
        await self.client.run_until_disconnected()

    async def _load_folder(self, folder_name: str) -> set:
        """加载文件夹中的对话"""
        try:
            filters = await self.client(GetDialogFiltersRequest())
            for f in filters.filters:
                if hasattr(f, "title") and f.title == folder_name:
                    ids = set()
                    if hasattr(f, "include_peers"):
                        for p in f.include_peers:
                            for attr in ("channel_id", "chat_id", "user_id"):
                                if hasattr(p, attr):
                                    ids.add(getattr(p, attr))
                                    break
                    self.log(f"已加载文件夹 '{folder_name}'，监听 {len(ids)} 个对话", "success")
                    return ids
            self.log(f"未找到文件夹 '{folder_name}'", "error")
        except Exception as e:
            self.log(f"加载文件夹失败: {e}", "error")
        return set()

    async def _should_reply(self, client, settings, text, sender) -> bool:
        """判断是否需要回复（关键词优先，再走 AI 判断）"""
        text_lower = text.strip().lower()

        # 1. 强制回复关键词匹配
        force_keywords = settings.get("force_reply_keywords", [])
        for kw in force_keywords:
            if kw and kw.lower() in text_lower:
                self.log(f"命中强制回复关键词: {kw}", "info")
                return True

        # 2. 跳过关键词匹配
        skip_keywords = settings.get("skip_keywords", [])
        for kw in skip_keywords:
            if kw and kw.lower() == text_lower:
                self.log(f"命中跳过关键词: {kw}", "skip")
                return False

        # 3. 如果模式是仅关键词，不走 AI
        if settings.get("skip_mode") == "keyword_only":
            return True

        # 4. AI 判断
        prompt = """判断这条消息是否需要回复。回答"是"：任何问题、打招呼、求助、截图、结束语（谢谢/不用了/再见等也需要简短回复）。回答"否"：纯表情、群内无关闲聊。不确定就答"是"。只回复：是 或 否"""
        try:
            resp = await client.chat.completions.create(
                model=settings["ai_model"],
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"发送者:{sender}\n内容:{text}"}
                ],
                max_tokens=10, temperature=0
            )
            return "是" in resp.choices[0].message.content.strip()
        except:
            return True

    async def _check_alert(self, ai_client, settings, text, sender_name, chat_id) -> bool:
        """检测是否需要预警（客户不满、要求会议沟通等）"""
        prompt = """判断这条消息是否包含以下情况之一：
1. 客户表达不满、投诉、抱怨、生气
2. 客户要求电话沟通、会议、视频通话、线下见面
3. 客户威胁要退款、取消服务、换供应商
4. 客户表示问题很紧急、已经影响业务
5. 客户对之前的回复不满意、觉得没解决问题

只回复：是 或 否"""
        try:
            resp = await ai_client.chat.completions.create(
                model=settings["ai_model"],
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"发送者:{sender_name}\n内容:{text}"}
                ],
                max_tokens=10, temperature=0
            )
            return "是" in resp.choices[0].message.content.strip()
        except:
            return False

    async def _send_webhook_alert(self, settings, sender_name, chat_id, msg_text):
        """发送企业微信 webhook 预警"""
        webhook_url = settings.get("alert_webhook_url", "")
        if not webhook_url:
            return

        import aiohttp
        payload = {
            "msgtype": "text",
            "text": {
                "content": f"⚠️ 客户预警\n\n发送者: {sender_name}\n群/对话ID: {chat_id}\n消息内容: {msg_text[:200]}\n\n请尽快手动介入处理。"
            }
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as resp:
                    if resp.status == 200:
                        self.log(f"⚠️ 已推送预警到企业微信（{sender_name}）", "error")
                    else:
                        self.log(f"预警推送失败: HTTP {resp.status}", "error")
        except Exception as e:
            self.log(f"预警推送异常: {e}", "error")


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.worker = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("博思云 Telegram 自动回复系统")
        self.setMinimumSize(700, 550)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # 标签页
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # 配置页
        config_tab = self._create_config_tab()
        tabs.addTab(config_tab, "配置")

        # 日志页
        log_tab = self._create_log_tab()
        tabs.addTab(log_tab, "运行日志")

        # Prompt 页
        prompt_tab = self._create_prompt_tab()
        tabs.addTab(prompt_tab, "系统提示词")

        # 回复规则页
        rules_tab = self._create_rules_tab()
        tabs.addTab(rules_tab, "回复规则")

        # 底部控制栏
        control_layout = QHBoxLayout()
        self.start_btn = QPushButton("▶ 启动")
        self.start_btn.setFixedHeight(36)
        self.start_btn.clicked.connect(self.start_bot)
        control_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("■ 停止")
        self.stop_btn.setFixedHeight(36)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_bot)
        control_layout.addWidget(self.stop_btn)

        self.status_label = QLabel("状态: 未启动")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        control_layout.addWidget(self.status_label)

        layout.addLayout(control_layout)

    def _create_config_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Telegram 配置
        tg_group = QGroupBox("Telegram 配置")
        tg_form = QFormLayout(tg_group)

        self.api_id_input = QLineEdit(str(self.settings["telegram_api_id"]))
        tg_form.addRow("API ID:", self.api_id_input)

        self.api_hash_input = QLineEdit(self.settings["telegram_api_hash"])
        tg_form.addRow("API Hash:", self.api_hash_input)

        self.folder_input = QLineEdit(self.settings["telegram_folder"])
        tg_form.addRow("监听文件夹:", self.folder_input)

        layout.addWidget(tg_group)

        # AI 配置
        ai_group = QGroupBox("AI 配置")
        ai_form = QFormLayout(ai_group)

        self.base_url_input = QLineEdit(self.settings["ai_base_url"])
        ai_form.addRow("Base URL:", self.base_url_input)

        self.api_key_input = QLineEdit(self.settings["ai_api_key"])
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        ai_form.addRow("API Key:", self.api_key_input)

        self.model_input = QLineEdit(self.settings["ai_model"])
        ai_form.addRow("模型:", self.model_input)

        layout.addWidget(ai_group)

        # 回复配置
        reply_group = QGroupBox("回复配置")
        reply_form = QFormLayout(reply_group)

        delay_layout = QHBoxLayout()
        self.delay_min_input = QSpinBox()
        self.delay_min_input.setRange(1, 60)
        self.delay_min_input.setValue(self.settings["delay_min"])
        delay_layout.addWidget(self.delay_min_input)
        delay_layout.addWidget(QLabel("-"))
        self.delay_max_input = QSpinBox()
        self.delay_max_input.setRange(1, 120)
        self.delay_max_input.setValue(self.settings["delay_max"])
        delay_layout.addWidget(self.delay_max_input)
        delay_layout.addWidget(QLabel("秒"))
        reply_form.addRow("回复延迟:", delay_layout)

        self.context_input = QSpinBox()
        self.context_input.setRange(5, 50)
        self.context_input.setValue(self.settings["context_messages"])
        reply_form.addRow("上下文消息数:", self.context_input)

        self.debounce_input = QSpinBox()
        self.debounce_input.setRange(3, 60)
        self.debounce_input.setValue(self.settings.get("debounce_seconds", 10))
        self.debounce_input.setSuffix(" 秒")
        reply_form.addRow("消息聚合等待:", self.debounce_input)

        self.webhook_input = QLineEdit(self.settings.get("alert_webhook_url", ""))
        self.webhook_input.setPlaceholderText("企业微信 webhook 地址（留空则不推送预警）")
        reply_form.addRow("预警 Webhook:", self.webhook_input)

        layout.addWidget(reply_group)

        # 代理配置
        proxy_group = QGroupBox("代理配置")
        proxy_form = QFormLayout(proxy_group)

        self.proxy_check = QCheckBox("启用代理")
        self.proxy_check.setChecked(self.settings.get("proxy_enabled", False))
        proxy_form.addRow(self.proxy_check)

        proxy_detail = QHBoxLayout()
        self.proxy_type_combo = QComboBox()
        self.proxy_type_combo.addItems(["socks5", "http"])
        self.proxy_type_combo.setCurrentText(self.settings.get("proxy_type", "socks5"))
        proxy_detail.addWidget(self.proxy_type_combo)
        self.proxy_host_input = QLineEdit(self.settings.get("proxy_host", "127.0.0.1"))
        self.proxy_host_input.setFixedWidth(120)
        proxy_detail.addWidget(self.proxy_host_input)
        self.proxy_port_input = QSpinBox()
        self.proxy_port_input.setRange(1, 65535)
        self.proxy_port_input.setValue(self.settings.get("proxy_port", 7890))
        proxy_detail.addWidget(self.proxy_port_input)
        proxy_form.addRow("代理地址:", proxy_detail)

        layout.addWidget(proxy_group)

        # 保存按钮
        save_btn = QPushButton("保存配置")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)

        layout.addStretch()
        return widget

    def _create_log_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text)

        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(self.log_text.clear)
        layout.addWidget(clear_btn)

        return widget

    def _create_prompt_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel("系统提示词（定义 AI 的回复风格和角色）:"))
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlainText(self.settings["system_prompt"])
        self.prompt_edit.setFont(QFont("Microsoft YaHei", 10))
        layout.addWidget(self.prompt_edit)

        save_prompt_btn = QPushButton("保存提示词")
        save_prompt_btn.clicked.connect(self.save_config)
        layout.addWidget(save_prompt_btn)

        return widget

    def _create_rules_tab(self) -> QWidget:
        """创建回复规则配置页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 判断模式选择
        mode_group = QGroupBox("判断模式")
        mode_layout = QVBoxLayout(mode_group)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["关键词 + AI 判断（推荐）", "仅关键词（不调用 AI 判断）"])
        current_mode = self.settings.get("skip_mode", "keyword_then_ai")
        self.mode_combo.setCurrentIndex(0 if current_mode == "keyword_then_ai" else 1)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addWidget(QLabel("「关键词 + AI」模式下，先匹配关键词，未命中再由 AI 判断是否回复"))

        layout.addWidget(mode_group)

        # 跳过关键词
        skip_group = QGroupBox("跳过关键词（精确匹配，消息内容完全等于关键词时跳过）")
        skip_layout = QVBoxLayout(skip_group)

        self.skip_keywords_edit = QTextEdit()
        self.skip_keywords_edit.setFixedHeight(100)
        self.skip_keywords_edit.setPlaceholderText("每行一个关键词，例如：\n👍\n🙏\n+1")
        skip_keywords = self.settings.get("skip_keywords", [])
        self.skip_keywords_edit.setPlainText("\n".join(skip_keywords))
        skip_layout.addWidget(self.skip_keywords_edit)
        skip_layout.addWidget(QLabel("消息内容完全等于某个关键词时，不回复。适合过滤纯表情、纯符号等。"))

        layout.addWidget(skip_group)

        # 强制回复关键词
        force_group = QGroupBox("强制回复关键词（包含匹配，消息中包含关键词时必定回复）")
        force_layout = QVBoxLayout(force_group)

        self.force_keywords_edit = QTextEdit()
        self.force_keywords_edit.setFixedHeight(100)
        self.force_keywords_edit.setPlaceholderText("每行一个关键词，例如：\n帮我\n怎么\n为什么\n报错")
        force_keywords = self.settings.get("force_reply_keywords", [])
        self.force_keywords_edit.setPlainText("\n".join(force_keywords))
        force_layout.addWidget(self.force_keywords_edit)
        force_layout.addWidget(QLabel("消息中包含任一关键词时，跳过 AI 判断直接回复。优先级高于跳过规则。"))

        layout.addWidget(force_group)

        # 保存按钮
        save_rules_btn = QPushButton("保存规则")
        save_rules_btn.clicked.connect(self.save_config)
        layout.addWidget(save_rules_btn)

        layout.addStretch()
        return widget

    def save_config(self):
        """保存所有配置"""
        # 解析回复规则关键词
        skip_text = self.skip_keywords_edit.toPlainText() if hasattr(self, 'skip_keywords_edit') else ""
        skip_keywords = [line.strip() for line in skip_text.split("\n") if line.strip()]

        force_text = self.force_keywords_edit.toPlainText() if hasattr(self, 'force_keywords_edit') else ""
        force_keywords = [line.strip() for line in force_text.split("\n") if line.strip()]

        mode_index = self.mode_combo.currentIndex() if hasattr(self, 'mode_combo') else 0
        skip_mode = "keyword_then_ai" if mode_index == 0 else "keyword_only"

        self.settings.update({
            "telegram_api_id": self.api_id_input.text(),
            "telegram_api_hash": self.api_hash_input.text(),
            "telegram_folder": self.folder_input.text(),
            "ai_base_url": self.base_url_input.text(),
            "ai_api_key": self.api_key_input.text(),
            "ai_model": self.model_input.text(),
            "delay_min": self.delay_min_input.value(),
            "delay_max": self.delay_max_input.value(),
            "context_messages": self.context_input.value(),
            "context_expire_hours": 72,
            "debounce_seconds": self.debounce_input.value(),
            "alert_webhook_url": self.webhook_input.text(),
            "proxy_enabled": self.proxy_check.isChecked(),
            "proxy_type": self.proxy_type_combo.currentText(),
            "proxy_host": self.proxy_host_input.text(),
            "proxy_port": self.proxy_port_input.value(),
            "system_prompt": self.prompt_edit.toPlainText(),
            "skip_keywords": skip_keywords,
            "force_reply_keywords": force_keywords,
            "skip_mode": skip_mode,
        })
        save_settings(self.settings)
        self.append_log("[配置已保存]", "success")

    def start_bot(self):
        """启动机器人"""
        self.save_config()

        if not self.settings["ai_api_key"]:
            QMessageBox.warning(self, "提示", "请先填写 AI API Key")
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("状态: 连接中...")

        self.worker = BotWorker(self.settings)
        self.worker.log_signal.connect(self.append_log)
        self.worker.status_signal.connect(self.on_status_change)
        self.worker.login_required.connect(self.on_login_required)
        self.worker.code_required.connect(self.on_code_required)
        self.worker.password_required.connect(self.on_password_required)
        self.worker.start()

    def stop_bot(self):
        """停止机器人"""
        if self.worker:
            self.worker.stop()
            self.worker.wait(5000)
            self.worker = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("状态: 已停止")
        self.append_log("[已停止]", "info")

    def on_status_change(self, status: str):
        status_map = {
            "connecting": "状态: 连接中...",
            "running": "状态: ● 运行中",
            "stopped": "状态: 已停止",
        }
        self.status_label.setText(status_map.get(status, f"状态: {status}"))
        if status == "stopped":
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def on_login_required(self):
        phone, ok = QInputDialog.getText(self, "Telegram 登录", "请输入手机号（如 +8613800138000）:")
        if ok and phone:
            self.worker.provide_phone(phone)
        else:
            self.worker.stop()

    def on_code_required(self):
        code, ok = QInputDialog.getText(self, "验证码", "请输入 Telegram 发送的验证码:")
        if ok and code:
            self.worker.provide_code(code)
        else:
            self.worker.stop()

    def on_password_required(self):
        pwd, ok = QInputDialog.getText(self, "两步验证", "请输入两步验证密码:", QLineEdit.EchoMode.Password)
        if ok and pwd:
            self.worker.provide_password(pwd)
        else:
            self.worker.stop()

    def append_log(self, msg: str, level: str = "info"):
        """追加日志到日志窗口"""
        color_map = {
            "info": "#333333",
            "success": "#2e7d32",
            "error": "#c62828",
            "reply": "#1565c0",
            "skip": "#757575",
        }
        color = color_map.get(level, "#333333")
        self.log_text.append(f'<span style="color:{color}">{msg}</span>')
        # 自动滚动到底部
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)

    def closeEvent(self, event):
        """关闭窗口时停止后台线程"""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 单实例检测：防止重复打开导致 database locked
    import tempfile
    lock_file = Path(tempfile.gettempdir()) / "bosicloud_autoreply.lock"
    try:
        # 尝试独占打开锁文件
        lock_fd = open(lock_file, 'w')
        import msvcrt
        msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
    except (IOError, OSError):
        QMessageBox.warning(None, "提示", "程序已在运行中，请勿重复打开。\n\n如果确认没有在运行，请在任务管理器中结束 BosiCloud-AutoReply 进程后重试。")
        sys.exit(1)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
