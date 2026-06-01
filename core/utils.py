"""
工具模块
- 聊天记录持久化
- 运行日志持久化
- 静默白名单管理
- 回复去重
- 统计数据
"""

import json
import hashlib
from datetime import datetime, date
from collections import deque
from pathlib import Path
from typing import Optional

from core.config import CHAT_LOGS_DIR, RUN_LOG_DIR, SILENCE_PATH


# ============ 聊天记录持久化 ============

def save_chat_log(chat_id: int, sender_name: str, role: str, content: str):
    """持久化聊天记录到 chat_logs/YYYY-MM-DD/chat_xxx.txt"""
    today = date.today().strftime("%Y-%m-%d")
    day_dir = CHAT_LOGS_DIR / today
    day_dir.mkdir(parents=True, exist_ok=True)
    log_file = day_dir / f"chat_{abs(chat_id)}.txt"
    timestamp = datetime.now().strftime("%H:%M:%S")
    if role == "user":
        line = f"[{timestamp}] {sender_name}: {content}\n"
    else:
        line = f"[{timestamp}] [AI回复]: {content}\n"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


# ============ 运行日志持久化 ============

def save_run_log(msg: str):
    """运行日志写入 run_logs/YYYY-MM-DD.log"""
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y-%m-%d")
    log_file = RUN_LOG_DIR / f"{today}.log"
    timestamp = datetime.now().strftime("%H:%M:%S")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except Exception:
        pass


# ============ 静默白名单 ============

def load_silence_list() -> dict:
    """加载静默白名单 {chat_id_str: {"added_at": ..., "reason": ...}}"""
    if SILENCE_PATH.exists():
        try:
            with open(SILENCE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_silence_list(data: dict):
    """保存静默白名单"""
    try:
        with open(SILENCE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ============ 回复去重 ============

class ReplyDeduplicator:
    """检测短时间内对同一群发送相似回复，避免重复"""

    def __init__(self, window_seconds: int = 120, max_history: int = 20):
        self._history: deque = deque(maxlen=max_history)
        self._window = window_seconds

    def is_duplicate(self, chat_id: int, reply_text: str) -> bool:
        """检查是否与近期回复重复（相似度 > 90%）"""
        now = datetime.now().timestamp()
        reply_hash = self._hash(reply_text)

        for ts, cid, h in self._history:
            if now - ts > self._window:
                continue
            if cid == chat_id and h == reply_hash:
                return True
        return False

    def record(self, chat_id: int, reply_text: str):
        """记录一条已发送的回复"""
        self._history.append((
            datetime.now().timestamp(),
            chat_id,
            self._hash(reply_text)
        ))

    @staticmethod
    def _hash(text: str) -> str:
        """取文本前100字的 hash 作为指纹"""
        return hashlib.md5(text[:100].encode()).hexdigest()


# ============ 统计数据 ============

class Stats:
    """运行时统计（内存中，重启清零）"""

    def __init__(self):
        self.total_received = 0
        self.total_replied = 0
        self.total_skipped = 0
        self.total_alerts = 0
        self.total_errors = 0
        self.start_time: Optional[datetime] = None
        self._response_times: deque = deque(maxlen=100)

    def start(self):
        self.start_time = datetime.now()

    def record_response_time(self, seconds: float):
        self._response_times.append(seconds)

    @property
    def avg_response_time(self) -> float:
        if not self._response_times:
            return 0.0
        return sum(self._response_times) / len(self._response_times)

    @property
    def uptime(self) -> str:
        if not self.start_time:
            return "未启动"
        delta = datetime.now() - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"

    def to_dict(self) -> dict:
        return {
            "uptime": self.uptime,
            "total_received": self.total_received,
            "total_replied": self.total_replied,
            "total_skipped": self.total_skipped,
            "total_alerts": self.total_alerts,
            "total_errors": self.total_errors,
            "avg_response_time": f"{self.avg_response_time:.1f}s",
        }
