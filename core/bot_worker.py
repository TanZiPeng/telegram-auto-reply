"""
Bot 工作线程
- Telegram 连接 + 登录
- 自动重连（指数退避）
- 消息监听分发
- 群名映射
- 手动发送
"""

import sys
import asyncio
import threading
from pathlib import Path
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal

from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetDialogFiltersRequest

from core.config import DB_PATH
from core.ai_service import AIService
from core.message_handler import MessageHandler
from core.utils import (
    load_silence_list, save_silence_list, save_run_log, Stats
)
from memory import MemoryManager


class BotWorker(QThread):
    """后台工作线程"""

    log_signal = pyqtSignal(str, str)       # (message, level)
    status_signal = pyqtSignal(str)          # connecting/running/reconnecting/stopped
    login_required = pyqtSignal()
    code_required = pyqtSignal()
    password_required = pyqtSignal()
    silence_updated = pyqtSignal()
    stats_updated = pyqtSignal(dict)         # 统计数据更新
    chat_names_updated = pyqtSignal(dict)    # 群名映射更新

    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings
        self.running = False
        self.client = None
        self.loop = None

        # 登录交互
        self.phone = ""
        self.code = ""
        self.password = ""
        self._phone_event = threading.Event()
        self._code_event = threading.Event()
        self._password_event = threading.Event()

        # 状态
        self.silence_list = load_silence_list()
        self.stats = Stats()
        self.chat_names: dict[int, str] = {}  # chat_id -> 群名
        self._monitored_chats: set = set()

    # ---- 外部接口 ----

    def provide_phone(self, phone: str):
        self.phone = phone
        self._phone_event.set()

    def provide_code(self, code: str):
        self.code = code
        self._code_event.set()

    def provide_password(self, pwd: str):
        self.password = pwd
        self._password_event.set()

    def add_silence(self, chat_id: int, reason: str = "手动添加"):
        self.silence_list[str(chat_id)] = {
            "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "reason": reason
        }
        save_silence_list(self.silence_list)
        self.silence_updated.emit()

    def remove_silence(self, chat_id: int):
        self.silence_list.pop(str(chat_id), None)
        save_silence_list(self.silence_list)
        self.silence_updated.emit()

    def is_silenced(self, chat_id: int) -> bool:
        return str(abs(chat_id)) in self.silence_list or str(chat_id) in self.silence_list

    def update_settings(self, settings: dict):
        """配置热更新"""
        self.settings = settings
        if hasattr(self, '_handler'):
            self._handler.update_settings(settings)
        if hasattr(self, '_ai'):
            self._ai.update_config(
                settings["ai_base_url"], settings["ai_api_key"],
                settings["ai_model"], settings.get("ai_timeout", 30)
            )

    def send_manual_message(self, chat_id: int, text: str):
        """手动发送消息（从 GUI 调用）"""
        if self.loop and self.client and self.client.is_connected():
            asyncio.run_coroutine_threadsafe(
                self.client.send_message(chat_id, text), self.loop
            )

    def stop(self):
        self.running = False
        if self.client and self.client.is_connected():
            self.client.disconnect()

    # ---- 内部方法 ----

    def log(self, msg: str, level: str = "info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {msg}"
        self.log_signal.emit(full_msg, level)
        save_run_log(msg)

    def run(self):
        """主运行方法"""
        self.running = True
        self.stats.start()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._run_with_reconnect())
        except Exception as e:
            self.log(f"运行出错: {e}", "error")
        finally:
            self.loop.close()
            self.status_signal.emit("stopped")

    async def _run_with_reconnect(self):
        """带自动重连的主循环"""
        retry_delay = 5
        max_retry_delay = 120

        while self.running:
            try:
                await self._run()
            except Exception as e:
                if not self.running:
                    break
                self.log(f"连接断开: {e}，{retry_delay}s 后重连...", "error")
                self.status_signal.emit("reconnecting")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
            else:
                break  # 正常退出

    async def _run(self):
        """核心异步逻辑"""
        s = self.settings

        # 代理
        proxy = None
        if s.get("proxy_enabled"):
            import socks
            proxy_map = {"socks5": socks.SOCKS5, "socks4": socks.SOCKS4, "http": socks.HTTP}
            proxy = (proxy_map.get(s["proxy_type"], socks.SOCKS5), s["proxy_host"], s["proxy_port"])
            self.log(f"使用代理: {s['proxy_type']}://{s['proxy_host']}:{s['proxy_port']}")

        # Session 路径
        if getattr(sys, 'frozen', False):
            app_dir = Path(sys.executable).parent
        else:
            app_dir = Path(__file__).parent.parent
        session_path = str(app_dir / "tg_session")

        # Session 文件检查
        session_file = Path(session_path + ".session")
        if session_file.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(str(session_file), timeout=1)
                conn.execute("SELECT 1")
                conn.close()
            except Exception:
                self.log("session 文件被锁，删除重建...", "info")
                import time
                for _ in range(3):
                    try:
                        session_file.unlink()
                        break
                    except Exception:
                        time.sleep(1)

        self.client = TelegramClient(
            session_path, int(s["telegram_api_id"]), s["telegram_api_hash"],
            proxy=proxy, connection_retries=5, retry_delay=3,
        )

        self.log("正在连接 Telegram...")
        self.status_signal.emit("connecting")

        await self.client.connect()
        if not await self.client.is_user_authorized():
            await self._login()

        me = await self.client.get_me()
        self.log(f"已登录: {me.first_name} ({me.phone})", "success")
        self.status_signal.emit("running")

        # 加载文件夹 + 群名映射
        self._monitored_chats = await self._load_folder(s["telegram_folder"])
        await self._load_chat_names()

        # 初始化服务
        self._ai = AIService(
            s["ai_base_url"], s["ai_api_key"], s["ai_model"], s.get("ai_timeout", 30)
        )
        memory = MemoryManager(
            db_path=str(DB_PATH), max_messages=s["context_messages"],
            expire_hours=s["context_expire_hours"]
        )
        self._handler = MessageHandler(
            settings=s, ai=self._ai, memory=memory, stats=self.stats,
            log_func=self.log, silence_checker=self.is_silenced,
            silence_adder=self.add_silence,
            send_func=self._send_msg, reply_func=self._reply_msg,
            webhook_func=self._send_webhook,
        )

        # 统计定时器
        async def stats_ticker():
            while self.running:
                await asyncio.sleep(5)
                self.stats_updated.emit(self.stats.to_dict())

        asyncio.create_task(stats_ticker())

        # 消息处理器
        @self.client.on(events.NewMessage())
        async def handler(event):
            if not self.running or event.out:
                return
            chat_id = event.chat_id
            abs_id = abs(chat_id)
            if abs_id not in self._monitored_chats and chat_id not in self._monitored_chats:
                return

            sender = await event.get_sender()
            sender_name = getattr(sender, "first_name", "") or ""
            last = getattr(sender, "last_name", "") or ""
            if last:
                sender_name += f" {last}"

            msg_text = event.message.message or ""
            has_photo = event.message.photo is not None
            if not msg_text and not has_photo:
                return

            self.log(f"收到 {sender_name}: {msg_text[:60]}{'[图片]' if has_photo else ''}")
            await self._handler.on_message(chat_id, sender_name, msg_text, has_photo, event)

        self.log(f"开始监听（聚合 {s['debounce_seconds']}s，延迟 {s['delay_min']}-{s['delay_max']}s）", "success")
        await self.client.run_until_disconnected()

    async def _login(self):
        """登录流程"""
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

    async def _load_folder(self, folder_name: str) -> set:
        """加载文件夹中的对话 ID"""
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

    async def _load_chat_names(self):
        """加载群名映射"""
        try:
            async for dialog in self.client.iter_dialogs():
                cid = dialog.id
                if abs(cid) in self._monitored_chats or cid in self._monitored_chats:
                    self.chat_names[abs(cid)] = dialog.name or str(cid)
            self.chat_names_updated.emit(self.chat_names)
            self.log(f"已加载 {len(self.chat_names)} 个群名映射")
        except Exception as e:
            self.log(f"加载群名失败: {e}", "error")

    async def _send_msg(self, chat_id: int, text: str):
        """发送消息"""
        await self.client.send_message(chat_id, text)

    async def _reply_msg(self, event, text: str):
        """回复消息"""
        await event.reply(text)

    async def _send_webhook(self, sender_name: str, chat_id: int, msg_text: str):
        """发送企业微信 webhook 预警"""
        webhook_url = self.settings.get("alert_webhook_url", "")
        if not webhook_url:
            return
        import aiohttp
        payload = {
            "msgtype": "text",
            "text": {
                "content": f"⚠️ 客户预警\n\n发送者: {sender_name}\n群ID: {chat_id}\n内容: {msg_text[:200]}\n\n已自动回复并加入静默名单，请在 GUI 中处理后移除。"
            }
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as resp:
                    if resp.status == 200:
                        self.log(f"⚠️ 已推送预警到企业微信", "error")
                    else:
                        self.log(f"预警推送失败: HTTP {resp.status}", "error")
        except Exception as e:
            self.log(f"预警推送异常: {e}", "error")
