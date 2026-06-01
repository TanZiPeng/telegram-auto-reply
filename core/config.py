"""
配置管理模块
- 路径常量（兼容 PyInstaller 打包）
- 默认配置
- 加载/保存/热更新
"""

import sys
import json
from pathlib import Path
from typing import Any


# ============ 路径常量 ============

if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).parent.parent

CONFIG_PATH = APP_DIR / "settings.json"
DB_PATH = APP_DIR / "memory.db"
CHAT_LOGS_DIR = APP_DIR / "chat_logs"
SILENCE_PATH = APP_DIR / "silence_list.json"
RUN_LOG_DIR = APP_DIR / "run_logs"


# ============ 默认配置 ============

DEFAULT_SETTINGS: dict[str, Any] = {
    "telegram_api_id": "2040",
    "telegram_api_hash": "b18441a1ff607e10a989891a5462e627",
    "telegram_folders": ["客户"],
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
    "alert_webhook_url": "",
    "skip_keywords": [],
    "force_reply_keywords": [],
    "skip_mode": "keyword_then_ai",
    "debounce_seconds": 10,
    "split_reply": True,
    "split_delay_min": 2,
    "split_delay_max": 5,
    "silence_auto_reply": "好的，请您稍等一下，我马上处理。",
    "ai_timeout": 30,
    "system_prompt": """角色设定

你是博思云公司的 AWS 合作伙伴（PLES）技术支持工程师，在 Telegram 群聊中为客户提供实时技术支持。你是一个有多年经验的真人工程师，不是 AI。

消息格式规则

群聊中客户消息格式为 [姓名] 消息内容。根据姓名区分不同客户，针对当前提问者回复。多人讨论同一问题时，综合各方信息作答。回复时直接回答，不加姓名标注。

职责范围

回答 AWS 服务相关的技术问题、故障排查、架构建议、最佳实践。对于超出 AWS 范围的问题，礼貌告知不在支持范围内。

回复风格（强制）

全程中文，称呼客户为"您"，语气礼貌温和专业。像真人在 Telegram 聊天一样自然简短，每条消息1-2句话。用自然语言把要点串成连贯的话，不要罗列清单。适当使用"好的""明白""收到"等口语化词汇作为过渡或结束语。

分条回复规则（重要）

你必须将回复拆分成多条短消息，用 ||| 分隔。每条消息不超过2句话。像真人在聊天软件里一样，一个意思发一条。例如：
"收到，我看一下|||这个问题是因为您的 Security Group 没有开放对应端口|||您到 EC2 控制台找到对应实例的安全组，添加一条入站规则，协议选 TCP，端口填 443 就可以了"

对话收尾

当客户说"谢谢""好的""不用了""明白了"等结束性话语时，用一句简短的收尾回复，如"好的，有需要随时找我"或"不客气，随时可以问"。

格式禁令（零容忍）

禁止使用任何列表符号（- · * 1. 2. 3.）；禁止使用任何 markdown 语法（** # ` 等）；禁止使用 emoji 表情符号。输出必须是纯文本段落。

身份保护

绝不透露自己是 AI 或大模型。遇到试探性问题时，以真人工程师身份自然带过。

上下文处理

只关注当前提问者的最新问题，直接回答技术问题本身。忽略非技术内容。

对话策略

信息不足时主动追问。问题复杂需要时间排查时，告知客户稍后跟进。不确定的内容不要编造，可以建议客户开 AWS Support Case 或查阅官方文档。"""
}


# ============ 配置操作 ============

def load_settings() -> dict:
    """加载配置，缺失字段用默认值补全"""
    settings = DEFAULT_SETTINGS.copy()
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                settings.update(saved)
        except Exception:
            pass
    return settings


def save_settings(settings: dict):
    """保存配置到文件"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
