"""
自动更新模块
- 检查 GitHub Release 最新版本
- 下载并替换文件
"""

import os
import sys
import json
import shutil
import zipfile
import tempfile
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError
from typing import Optional, Tuple

from PyQt6.QtCore import QThread, pyqtSignal

# 当前版本号（每次发版时更新这里）
CURRENT_VERSION = "2.0.0"

# GitHub 仓库信息
GITHUB_OWNER = "TanZiPeng"
GITHUB_REPO = "telegram-auto-reply"
API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"


def parse_version(tag: str) -> tuple:
    """将 v2.0.1 解析为 (2, 0, 1) 用于比较"""
    tag = tag.lstrip("vV")
    parts = []
    for p in tag.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def check_update(proxy_settings: dict = None) -> Optional[dict]:
    """
    检查是否有新版本
    proxy_settings: {"enabled": bool, "type": "socks5/http", "host": str, "port": int}
    返回 {"version": "2.0.1", "download_url": "...", "body": "更新说明"} 或 None
    失败返回 {"error": "错误信息"}
    """
    try:
        import urllib.request
        import ssl

        # 忽略 SSL 验证（某些代理环境下需要）
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        # 配置代理
        if proxy_settings and proxy_settings.get("enabled"):
            host = proxy_settings.get("host", "127.0.0.1")
            port = proxy_settings.get("port", 7890)
            proxy_url = f"http://{host}:{port}"
            proxy_handler = urllib.request.ProxyHandler({
                "http": proxy_url,
                "https": proxy_url,
            })
            https_handler = urllib.request.HTTPSHandler(context=ctx)
            opener = urllib.request.build_opener(proxy_handler, https_handler)
        else:
            https_handler = urllib.request.HTTPSHandler(context=ctx)
            opener = urllib.request.build_opener(https_handler)

        req = Request(API_URL, headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "BosiCloud-AutoReply/2.0"
        })
        with opener.open(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        latest_tag = data.get("tag_name", "")
        latest_ver = parse_version(latest_tag)
        current_ver = parse_version(CURRENT_VERSION)

        if latest_ver <= current_ver:
            return None  # 已是最新

        # 找 zip 下载链接
        download_url = None
        for asset in data.get("assets", []):
            if asset["name"].endswith(".zip"):
                download_url = asset["browser_download_url"]
                break

        if not download_url:
            download_url = data.get("zipball_url")

        return {
            "version": latest_tag,
            "download_url": download_url,
            "body": data.get("body", ""),
        }
    except Exception as e:
        return {"error": str(e)}


class UpdateWorker(QThread):
    """后台下载更新线程"""
    progress = pyqtSignal(int)       # 下载进度 0-100
    finished = pyqtSignal(bool, str) # (成功, 消息)

    def __init__(self, download_url: str):
        super().__init__()
        self.download_url = download_url

    def run(self):
        try:
            # 下载到临时文件
            self.progress.emit(5)
            req = Request(self.download_url)
            with urlopen(req, timeout=120) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                data = bytearray()
                downloaded = 0
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    data.extend(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        self.progress.emit(int(downloaded / total * 80))

            self.progress.emit(80)

            # 保存 zip
            tmp_dir = tempfile.mkdtemp()
            zip_path = Path(tmp_dir) / "update.zip"
            with open(zip_path, "wb") as f:
                f.write(data)

            self.progress.emit(85)

            # 解压
            extract_dir = Path(tmp_dir) / "extracted"
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            self.progress.emit(90)

            # 找到解压后的实际目录（可能有一层嵌套）
            contents = list(extract_dir.iterdir())
            if len(contents) == 1 and contents[0].is_dir():
                source_dir = contents[0]
            else:
                source_dir = extract_dir

            # 替换文件到当前 exe 目录
            if getattr(sys, 'frozen', False):
                app_dir = Path(sys.executable).parent
            else:
                app_dir = Path(__file__).parent.parent

            self.progress.emit(92)

            # 复制新文件（跳过用户数据文件）
            skip_files = {"settings.json", "memory.db", "silence_list.json",
                         "tg_session.session", "tg_session.session-shm",
                         "tg_session.session-wal"}
            skip_dirs = {"chat_logs", "run_logs"}

            # 生成更新脚本（处理 exe 被锁的情况）
            update_bat = app_dir / "_update.bat"
            bat_commands = ['@echo off', 'echo 正在更新，请稍候...', 'timeout /t 2 /nobreak >nul']
            needs_bat = False

            for item in source_dir.rglob("*"):
                rel = item.relative_to(source_dir)
                if rel.parts[0] in skip_dirs:
                    continue
                if rel.name in skip_files:
                    continue

                target = app_dir / rel
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(item, target)
                    except PermissionError:
                        # 文件被锁（exe 运行中），写入 bat 脚本延迟替换
                        needs_bat = True
                        bat_commands.append(f'copy /y "{item}" "{target}"')

            self.progress.emit(98)

            if needs_bat:
                # 写入 bat：等待进程退出后替换文件并重启
                exe_name = Path(sys.executable).name if getattr(sys, 'frozen', False) else ""
                if exe_name:
                    bat_commands.append(f'start "" "{app_dir / exe_name}"')
                bat_commands.append(f'del "%~f0"')  # 自删除
                update_bat.write_text("\n".join(bat_commands), encoding="gbk")

            self.progress.emit(100)
            shutil.rmtree(tmp_dir, ignore_errors=True)

            if needs_bat:
                self.finished.emit(True, "更新已准备好，重启后自动完成替换。")
            else:
                self.finished.emit(True, "更新完成，请重启程序以应用新版本。")

        except Exception as e:
            self.finished.emit(False, f"更新失败: {e}")
