"""
AI API 客户端 - 调用 OpenAI 兼容接口（支持图片理解）
"""

import base64
from openai import AsyncOpenAI


class AIClient:
    def __init__(self, base_url: str, api_key: str, model: str, max_tokens: int = 2048):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    async def chat(self, system_prompt: str, messages: list) -> str:
        """
        发送对话请求
        messages: OpenAI 格式的消息列表
        返回 AI 的回复文本
        """
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=full_messages,
                max_tokens=self.max_tokens,
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[AI ERROR] {e}")
            return None

    async def should_reply(self, system_prompt: str, message_text: str, sender_name: str) -> bool:
        """
        判断消息是否需要回复
        """
        judge_prompt = """你是一个消息分类器。判断以下消息是否需要回复。

需要回复（回答"是"）：
- 任何问题（无论是否与 AWS 相关）
- 打招呼（"你好"、"在吗"、"hi"）
- 寻求帮助或指导
- 描述问题或故障
- 询问某个技术概念是什么
- 对之前对话的追问
- 发送了截图（可能在求助）

不需要回复（回答"否"）：
- 纯表情包或贴纸（没有文字）
- 群内其他人之间的闲聊，明显不是在找技术支持

如果不确定，回答"是"。宁可多回复也不要漏掉客户的问题。

只回复一个字：是 或 否"""

        messages = [
            {"role": "user", "content": f"发送者: {sender_name}\n消息内容: {message_text}"}
        ]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": judge_prompt}] + messages,
                max_tokens=10,
                temperature=0,
            )
            result = response.choices[0].message.content.strip()
            return "是" in result
        except Exception as e:
            print(f"[JUDGE ERROR] {e}")
            # 出错时默认回复，避免漏掉客户问题
            return True

    @staticmethod
    def image_to_base64(image_bytes: bytes) -> str:
        """将图片字节转为 base64 字符串"""
        return base64.b64encode(image_bytes).decode("utf-8")

    @staticmethod
    def build_image_message(text: str, image_base64: str, mime_type: str = "image/png") -> list:
        """构建包含图片的多模态消息内容"""
        content = []
        if text:
            content.append({"type": "text", "text": text})
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{image_base64}"
            }
        })
        return content
