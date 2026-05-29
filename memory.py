"""
上下文记忆管理 - 使用 SQLite 存储每个对话的聊天历史
每个 chat_id 独立维护上下文，互不干扰
"""

import sqlite3
import json
import time
from pathlib import Path


class MemoryManager:
    def __init__(self, db_path: str = "memory.db", max_messages: int = 20, expire_hours: int = 72):
        self.db_path = db_path
        self.max_messages = max_messages
        self.expire_seconds = expire_hours * 3600
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_timestamp 
            ON messages(chat_id, timestamp)
        """)
        conn.commit()
        conn.close()

    def add_message(self, chat_id: int, role: str, content):
        """
        添加一条消息到记忆中
        content 可以是字符串或列表（多模态消息）
        """
        conn = sqlite3.connect(self.db_path)
        # content 如果是列表（含图片），序列化为 JSON
        if isinstance(content, list):
            content_str = json.dumps(content, ensure_ascii=False)
        else:
            content_str = content

        conn.execute(
            "INSERT INTO messages (chat_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (chat_id, role, content_str, time.time())
        )
        conn.commit()

        # 清理超出数量限制的旧消息
        self._cleanup(conn, chat_id)
        conn.close()

    def get_context(self, chat_id: int) -> list:
        """获取指定对话的上下文消息列表（OpenAI 格式）"""
        conn = sqlite3.connect(self.db_path)
        cutoff = time.time() - self.expire_seconds

        rows = conn.execute(
            """SELECT role, content FROM messages 
               WHERE chat_id = ? AND timestamp > ?
               ORDER BY timestamp ASC
               LIMIT ?""",
            (chat_id, cutoff, self.max_messages)
        ).fetchall()
        conn.close()

        messages = []
        for role, content_str in rows:
            # 尝试解析 JSON（多模态内容）
            try:
                content = json.loads(content_str)
                if not isinstance(content, list):
                    content = content_str
            except (json.JSONDecodeError, TypeError):
                content = content_str

            messages.append({"role": role, "content": content})

        return messages

    def _cleanup(self, conn: sqlite3.Connection, chat_id: int):
        """清理超出限制的旧消息"""
        # 删除过期消息
        cutoff = time.time() - self.expire_seconds
        conn.execute(
            "DELETE FROM messages WHERE chat_id = ? AND timestamp < ?",
            (chat_id, cutoff)
        )

        # 如果仍超出数量限制，删除最旧的
        count = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE chat_id = ?",
            (chat_id,)
        ).fetchone()[0]

        if count > self.max_messages:
            conn.execute(
                """DELETE FROM messages WHERE id IN (
                    SELECT id FROM messages WHERE chat_id = ?
                    ORDER BY timestamp ASC LIMIT ?
                )""",
                (chat_id, count - self.max_messages)
            )
        conn.commit()

    def clear_chat(self, chat_id: int):
        """清除指定对话的所有记忆"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        conn.commit()
        conn.close()
