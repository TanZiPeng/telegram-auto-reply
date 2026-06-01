"""
AI 服务封装
- 统一的 AI 调用接口
- 超时控制
- 重试机制
- 降级回复
"""

import asyncio
from openai import AsyncOpenAI
from typing import Optional


class AIService:
    """AI 调用服务，封装超时、重试、降级逻辑"""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 30):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.timeout = timeout

    def update_config(self, base_url: str, api_key: str, model: str, timeout: int = 30):
        """热更新配置"""
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.timeout = timeout

    async def chat(self, system_prompt: str, messages: list, max_tokens: int = 2048) -> Optional[str]:
        """
        发送对话请求，带超时和重试
        返回 AI 回复文本，失败返回 None
        """
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        for attempt in range(2):  # 最多重试1次
            try:
                resp = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.model,
                        messages=full_messages,
                        max_tokens=max_tokens,
                        temperature=0.7,
                    ),
                    timeout=self.timeout
                )
                return resp.choices[0].message.content.strip()
            except asyncio.TimeoutError:
                if attempt == 0:
                    continue  # 重试一次
                return None
            except Exception:
                if attempt == 0:
                    await asyncio.sleep(2)
                    continue
                return None

    async def judge(self, prompt: str, user_content: str) -> bool:
        """
        判断类调用（是/否），用于 should_reply 和 check_alert
        超时或异常默认返回 True（宁可多回复）
        """
        try:
            resp = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_content}
                    ],
                    max_tokens=10,
                    temperature=0,
                ),
                timeout=15
            )
            return "是" in resp.choices[0].message.content.strip()
        except Exception:
            return True

    FALLBACK_REPLY = "稍等我查一下，马上回复您。"
