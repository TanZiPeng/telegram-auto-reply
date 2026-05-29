"""
Telegram 自动回复主程序
监听指定文件夹中的对话，使用 AI 自动回复客户的 AWS 技术问题
"""

import asyncio
import random
import yaml
from pathlib import Path

from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetDialogFiltersRequest

from ai_client import AIClient
from memory import MemoryManager


# 加载配置
config_path = Path(__file__).parent / "config.yaml"
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# 初始化组件
proxy_config = None
if config["telegram"].get("proxy_type"):
    proxy_type = config["telegram"]["proxy_type"].lower()
    proxy_host = config["telegram"]["proxy_host"]
    proxy_port = config["telegram"]["proxy_port"]

    if proxy_type == "socks5":
        import socks
        proxy_config = (socks.SOCKS5, proxy_host, proxy_port)
    elif proxy_type == "socks4":
        import socks
        proxy_config = (socks.SOCKS4, proxy_host, proxy_port)
    elif proxy_type == "http":
        import socks
        proxy_config = (socks.HTTP, proxy_host, proxy_port)

    print(f"[INFO] 使用代理: {proxy_type}://{proxy_host}:{proxy_port}", flush=True)

client = TelegramClient(
    config["telegram"]["session_name"],
    config["telegram"]["api_id"],
    config["telegram"]["api_hash"],
    proxy=proxy_config
)

ai = AIClient(
    base_url=config["ai"]["base_url"],
    api_key=config["ai"]["api_key"],
    model=config["ai"]["model"],
    max_tokens=config["ai"]["max_tokens"],
)

memory = MemoryManager(
    db_path=str(Path(__file__).parent / "memory.db"),
    max_messages=config["reply"]["context_messages"],
    expire_hours=config["reply"]["context_expire_hours"],
)

SYSTEM_PROMPT = config["system_prompt"]
FOLDER_NAME = config["telegram"]["folder_name"]
DELAY_MIN = config["reply"]["delay_min"]
DELAY_MAX = config["reply"]["delay_max"]

# 存储监听的 chat_id 集合
monitored_chats: set = set()


async def load_folder_chats():
    """加载指定文件夹中的所有对话 ID"""
    global monitored_chats

    try:
        dialog_filters = await client(GetDialogFiltersRequest())

        target_filter = None
        for f in dialog_filters.filters:
            if hasattr(f, "title") and f.title == FOLDER_NAME:
                target_filter = f
                break

        if target_filter is None:
            print(f"[ERROR] 未找到名为 '{FOLDER_NAME}' 的文件夹！")
            print("可用的文件夹：")
            for f in dialog_filters.filters:
                if hasattr(f, "title"):
                    print(f"  - {f.title}")
            return

        # 提取文件夹中的 peer ID
        chat_ids = set()
        if hasattr(target_filter, "include_peers"):
            for peer in target_filter.include_peers:
                if hasattr(peer, "channel_id"):
                    chat_ids.add(peer.channel_id)
                elif hasattr(peer, "chat_id"):
                    chat_ids.add(peer.chat_id)
                elif hasattr(peer, "user_id"):
                    chat_ids.add(peer.user_id)

        monitored_chats = chat_ids
        print(f"[INFO] 已加载文件夹 '{FOLDER_NAME}'，监听 {len(chat_ids)} 个对话")

    except Exception as e:
        print(f"[ERROR] 加载文件夹失败: {e}")


async def handle_message(event):
    """处理收到的消息"""
    # 忽略自己发的消息
    if event.out:
        return

    # 获取 chat_id
    chat_id = event.chat_id

    # 检查是否在监听列表中（兼容正负 ID）
    abs_chat_id = abs(chat_id)
    if abs_chat_id not in monitored_chats and chat_id not in monitored_chats:
        return

    # 获取发送者信息
    sender = await event.get_sender()
    sender_name = ""
    if sender:
        sender_name = getattr(sender, "first_name", "") or ""
        last_name = getattr(sender, "last_name", "") or ""
        if last_name:
            sender_name += f" {last_name}"

    # 处理消息内容
    message_text = event.message.message or ""
    has_photo = event.message.photo is not None

    # 如果既没有文字也没有图片，跳过（贴纸、动图等）
    if not message_text and not has_photo:
        return

    print(f"[MSG] {sender_name} in {chat_id}: {message_text[:50]}{'...' if len(message_text) > 50 else ''} {'[图片]' if has_photo else ''}")

    # 构建用于判断的文本
    judge_text = message_text if message_text else "[客户发送了一张图片]"

    # AI 判断是否需要回复
    should_reply = await ai.should_reply(SYSTEM_PROMPT, judge_text, sender_name)
    if not should_reply:
        print(f"[SKIP] 判断为不需要回复")
        # 仍然记录到上下文（保持连贯性）
        if message_text:
            memory.add_message(chat_id, "user", message_text)
        return

    # 构建消息内容（支持图片）
    if has_photo:
        # 下载图片
        photo_bytes = await event.message.download_media(bytes)
        if photo_bytes:
            image_b64 = AIClient.image_to_base64(photo_bytes)
            content = AIClient.build_image_message(
                message_text or "请帮我看看这张图片中的问题",
                image_b64,
                "image/jpeg"
            )
        else:
            content = message_text or "[图片无法下载]"
    else:
        content = message_text

    # 记录用户消息到上下文
    memory.add_message(chat_id, "user", content)

    # 获取完整上下文
    context = memory.get_context(chat_id)

    # 调用 AI 生成回复
    reply_text = await ai.chat(SYSTEM_PROMPT, context)

    if not reply_text:
        print(f"[ERROR] AI 未返回回复")
        return

    # 随机延迟（模拟人类打字）
    delay = random.uniform(DELAY_MIN, DELAY_MAX)
    print(f"[WAIT] 等待 {delay:.1f}s 后回复...")
    await asyncio.sleep(delay)

    # 发送回复
    try:
        await event.reply(reply_text)
        print(f"[REPLY] -> {reply_text[:80]}{'...' if len(reply_text) > 80 else ''}")

        # 记录 AI 回复到上下文
        memory.add_message(chat_id, "assistant", reply_text)

    except Exception as e:
        print(f"[ERROR] 发送回复失败: {e}")


async def post_start():
    """登录成功后的初始化和运行"""
    me = await client.get_me()
    print(f"[INFO] 已登录: {me.first_name} ({me.phone})")

    # 加载监听的文件夹
    await load_folder_chats()

    if not monitored_chats:
        print("[WARN] 没有找到要监听的对话，请检查文件夹配置")
        print("[INFO] 程序将继续运行，等待文件夹更新...")

    # 注册消息处理器
    client.add_event_handler(handle_message, events.NewMessage())

    print(f"[INFO] 开始监听... (延迟 {DELAY_MIN}-{DELAY_MAX}s)")
    print("[INFO] 按 Ctrl+C 停止")
    print("-" * 50)

    # 保持运行
    await client.run_until_disconnected()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(line_buffering=True)

    print("=" * 50, flush=True)
    print("  博思云 Telegram 自动回复系统", flush=True)
    print("=" * 50, flush=True)
    print("[INFO] 正在连接 Telegram...", flush=True)

    try:
        with client:
            client.loop.run_until_complete(post_start())
    except KeyboardInterrupt:
        print("\n[INFO] 已停止")
    except Exception as e:
        print(f"[ERROR] {e}", flush=True)
        import traceback
        traceback.print_exc()
