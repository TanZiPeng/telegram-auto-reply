"""
消息处理模块
- 消息聚合（debounce）
- 回复决策（关键词 + AI 判断）
- 预警检测
- 分条发送
- 回复去重
"""

import asyncio
import random
import base64
from datetime import datetime
from typing import Optional

from core.ai_service import AIService
from core.utils import save_chat_log, ReplyDeduplicator, Stats
from memory import MemoryManager


class MessageHandler:
    """消息处理器：聚合、决策、回复"""

    def __init__(self, settings: dict, ai: AIService, memory: MemoryManager,
                 stats: Stats, log_func, silence_checker, silence_adder,
                 send_func, reply_func, webhook_func):
        self.settings = settings
        self.ai = ai
        self.memory = memory
        self.stats = stats
        self.log = log_func
        self.is_silenced = silence_checker
        self.add_silence = silence_adder
        self.send_message = send_func
        self.reply_message = reply_func
        self.send_webhook = webhook_func
        self.dedup = ReplyDeduplicator()

        # 聚合状态
        self.pending: dict = {}
        self.processing: set = set()

    def update_settings(self, settings: dict):
        """热更新配置"""
        self.settings = settings

    async def on_message(self, chat_id: int, sender_name: str, msg_text: str,
                         has_photo: bool, event):
        """收到新消息时调用"""
        self.stats.total_received += 1
        debounce = self.settings.get("debounce_seconds", 10)

        # 按 chat_id 聚合
        if chat_id in self.pending:
            if "timer" in self.pending[chat_id]:
                self.pending[chat_id]["timer"].cancel()
            self.pending[chat_id]["messages"].append((msg_text, has_photo, event, sender_name))
        else:
            self.pending[chat_id] = {
                "messages": [(msg_text, has_photo, event, sender_name)],
            }

        # 正在处理中则不启动新定时器
        if chat_id in self.processing:
            return

        async def fire():
            await asyncio.sleep(debounce)
            await self._process(chat_id)

        self.pending[chat_id]["timer"] = asyncio.create_task(fire())

    async def _process(self, chat_id: int):
        """处理聚合后的消息"""
        if chat_id not in self.pending:
            return

        self.processing.add(chat_id)
        buffer = self.pending.pop(chat_id)
        msgs = buffer["messages"]

        # 合并文本
        combined_texts = []
        last_event = msgs[-1][2]
        last_sender = msgs[-1][3]

        for msg_text, has_photo, evt, sname in msgs:
            if msg_text:
                combined_texts.append(msg_text)
            if has_photo:
                last_event = evt

        combined_text = "\n".join(combined_texts)
        has_any_photo = any(m[1] for m in msgs)

        self.log(f"聚合 {last_sender} 的 {len(msgs)} 条消息: {combined_text[:80]}")
        save_chat_log(chat_id, last_sender, "user", combined_text or "[图片]")

        try:
            await self._handle(chat_id, combined_text, has_any_photo, msgs, last_event, last_sender)
        except Exception as e:
            self.log(f"处理消息异常: {e}", "error")
            self.stats.total_errors += 1
        finally:
            self.processing.discard(chat_id)
            await self._check_pending(chat_id)

    async def _handle(self, chat_id, combined_text, has_any_photo, msgs, last_event, last_sender):
        """核心处理逻辑"""
        s = self.settings

        # 静默检查
        if self.is_silenced(chat_id):
            self.log(f"群 {chat_id} 在静默名单中，跳过", "skip")
            self.stats.total_skipped += 1
            if combined_text:
                self.memory.add_message(chat_id, "user", f"[{last_sender}] {combined_text}")
            return

        # 判断是否回复
        judge_text = combined_text if combined_text else "[客户发送了一张图片]"
        should = await self._should_reply(judge_text, last_sender)
        if not should:
            self.log(f"跳过（判断为不需要回复）", "skip")
            self.stats.total_skipped += 1
            if combined_text:
                self.memory.add_message(chat_id, "user", f"[{last_sender}] {combined_text}")
            return

        # 预警检测
        if combined_text:
            need_alert = await self._check_alert(combined_text, last_sender)
            if need_alert:
                await self._handle_alert(chat_id, combined_text, last_event, last_sender)
                return

        # 构建消息内容
        if has_any_photo:
            content = await self._build_photo_content(msgs, combined_text, last_sender)
        else:
            content = f"[{last_sender}] {combined_text}"

        self.memory.add_message(chat_id, "user", content)
        context = self.memory.get_context(chat_id)

        # 调用 AI
        start_time = datetime.now()
        reply = await self.ai.chat(s["system_prompt"], context)

        if not reply:
            # AI 超时降级
            reply = AIService.FALLBACK_REPLY
            self.log(f"AI 超时，使用降级回复", "error")
            self.stats.total_errors += 1

        elapsed = (datetime.now() - start_time).total_seconds()
        self.stats.record_response_time(elapsed)

        # 去重检查
        if self.dedup.is_duplicate(chat_id, reply):
            self.log(f"检测到重复回复，跳过", "skip")
            self.stats.total_skipped += 1
            return

        # 分条发送
        await self._send_reply(chat_id, reply, last_event)
        self.dedup.record(chat_id, reply)
        self.stats.total_replied += 1

    async def _should_reply(self, text: str, sender: str) -> bool:
        """判断是否需要回复"""
        s = self.settings
        text_lower = text.strip().lower()

        # 强制回复关键词
        for kw in s.get("force_reply_keywords", []):
            if kw and kw.lower() in text_lower:
                self.log(f"命中强制回复关键词: {kw}")
                return True

        # 跳过关键词
        for kw in s.get("skip_keywords", []):
            if kw and kw.lower() == text_lower:
                self.log(f"命中跳过关键词: {kw}", "skip")
                return False

        # 仅关键词模式
        if s.get("skip_mode") == "keyword_only":
            return True

        # AI 判断
        prompt = '判断这条消息是否需要回复。回答"是"：任何问题、打招呼、求助、截图、结束语。回答"否"：纯表情、群内无关闲聊。不确定就答"是"。只回复：是 或 否'
        return await self.ai.judge(prompt, f"发送者:{sender}\n内容:{text}")

    async def _check_alert(self, text: str, sender: str) -> bool:
        """检测是否需要预警"""
        prompt = """判断这条消息是否包含以下情况之一：
1. 客户表达不满、投诉、抱怨
2. 客户要求电话/会议/视频沟通
3. 客户威胁退款、取消服务
4. 客户表示问题紧急、影响业务
5. 客户对之前回复不满意
只回复：是 或 否"""
        return await self.ai.judge(prompt, f"发送者:{sender}\n内容:{text}")

    async def _handle_alert(self, chat_id, text, last_event, sender):
        """处理预警：回复稍等 + 加入静默 + 推送 webhook"""
        s = self.settings
        silence_reply = s.get("silence_auto_reply", "好的，请您稍等一下，我马上处理。")

        try:
            await self.reply_message(last_event, silence_reply)
            self.log(f"触发人工接入，已回复: {silence_reply}", "error")
            save_chat_log(chat_id, "系统", "assistant", silence_reply)
        except Exception as e:
            self.log(f"发送稍等回复失败: {e}", "error")

        self.add_silence(abs(chat_id), reason=f"预警: {text[:50]}")
        self.log(f"⚠️ 群 {chat_id} 已加入静默名单", "error")

        await self.send_webhook(sender, chat_id, text)
        self.memory.add_message(chat_id, "user", f"[{sender}] {text}")
        self.memory.add_message(chat_id, "assistant", silence_reply)
        self.stats.total_alerts += 1

    async def _build_photo_content(self, msgs, combined_text, sender):
        """构建含图片的多模态消息"""
        for msg_text, has_photo, evt, sname in reversed(msgs):
            if has_photo:
                try:
                    photo_bytes = await evt.message.download_media(bytes)
                    if photo_bytes:
                        b64 = base64.b64encode(photo_bytes).decode()
                        return [
                            {"type": "text", "text": f"[{sender}] {combined_text or '发送了一张图片，请帮我看看'}"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                        ]
                except Exception:
                    pass
                break
        return f"[{sender}] {combined_text or '[图片无法下载]'}"

    async def _send_reply(self, chat_id: int, reply: str, last_event):
        """分条发送回复"""
        s = self.settings

        # 拆分逻辑
        if s.get("split_reply", True) and "|||" in reply:
            parts = [p.strip() for p in reply.split("|||") if p.strip()]
        elif s.get("split_reply", True) and len(reply) > 80:
            parts = [p.strip() for p in reply.split("\n") if p.strip()]
            if len(parts) <= 1:
                parts = [reply]
        else:
            parts = [reply]

        full_reply = ""
        for i, part in enumerate(parts):
            if i == 0:
                delay = random.uniform(s["delay_min"], s["delay_max"])
            else:
                delay = random.uniform(s.get("split_delay_min", 2), s.get("split_delay_max", 5))

            await asyncio.sleep(delay)

            try:
                if i == 0:
                    await self.reply_message(last_event, part)
                else:
                    await self.send_message(chat_id, part)
                self.log(f"回复({i+1}/{len(parts)}): {part[:60]}{'...' if len(part) > 60 else ''}", "reply")
                full_reply += part + "\n"
            except Exception as e:
                self.log(f"发送第 {i+1} 条失败: {e}", "error")
                break

        if full_reply:
            self.memory.add_message(chat_id, "assistant", full_reply.strip())
            save_chat_log(chat_id, "AI", "assistant", full_reply.strip())

    async def _check_pending(self, chat_id: int):
        """处理完成后检查是否有新消息积压"""
        if chat_id in self.pending:
            if "timer" in self.pending[chat_id]:
                self.pending[chat_id]["timer"].cancel()
            await asyncio.sleep(3)
            if chat_id in self.pending:
                await self._process(chat_id)
