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
CURRENT_VERSION = "2.0.3"

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

    def __init__(self, download_url: str, proxy_settings: dict = None):
        super().__init__()
        self.download_url = download_url
        self.proxy_settings = proxy_settings

    def _make_opener(self):
        """创建带代理的 opener"""
        import urllib.request
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        https_handler = urllib.request.HTTPSHandler(context=ctx)

        if self.proxy_settings and self.proxy_settings.get("enabled"):
            host = self.proxy_settings.get("host", "127.0.0.1")
            port = self.proxy_settings.get("port", 7890)
            proxy_url = f"http://{host}:{port}"
            proxy_handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
            return urllib.request.build_opener(proxy_handler, https_handler)
        else:
            return urllib.request.build_opener(https_handler)

    def run(self):
        try:
            opener = self._make_opener()

            # 下载 zip
            self.progress.emit(5)
            req = Request(self.download_url, headers={"User-Agent": "BosiCloud-AutoReply/2.0"})
            with opener.open(req, timeout=180) as resp:
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
                        self.progress.emit(int(downloaded / total * 70))

            self.progress.emit(75)

            # 保存到 exe 同级的 _update 目录（不用临时目录，防止被清理）
            if getattr(sys, 'frozen', False):
                app_dir = Path(sys.executable).parent
            else:
                app_dir = Path(__file__).parent.parent

            update_dir = app_dir / "_update_temp"
            if update_dir.exists():
                shutil.rmtree(update_dir, ignore_errors=True)
            update_dir.mkdir(parents=True, exist_ok=True)

            zip_path = update_dir / "update.zip"
            with open(zip_path, "wb") as f:
                f.write(data)

            self.progress.emit(80)

            # 解压
            extract_dir = update_dir / "extracted"
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            self.progress.emit(85)

            # 找到解压后的实际目录（zip 内可能有一层文件夹嵌套）
            contents = list(extract_dir.iterdir())
            if len(contents) == 1 and contents[0].is_dir():
                source_dir = contents[0]
            else:
                source_dir = extract_dir

            self.progress.emit(90)

            # 复制新文件（跳过用户数据）
            skip_files = {"settings.json", "memory.db", "silence_list.json",
                         "tg_session.session", "tg_session.session-shm",
                         "tg_session.session-wal", "_update.bat"}
            skip_dirs = {"chat_logs", "run_logs", "_update_temp"}

            # 收集被锁文件，写入 bat
            locked_files = []
            copied_count = 0

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
                        copied_count += 1
                    except PermissionError:
                        # 文件被锁，记录下来用 bat 替换
                        locked_files.append((str(item), str(target)))

            self.progress.emit(95)

            # 如果有被锁文件，生成更新脚本
            if locked_files:
                bat_lines = [
                    '@echo off',
                    'echo 正在完成更新，请勿关闭此窗口...',
                    # 等待旧进程完全退出
                    'timeout /t 5 /nobreak >nul',
                ]
                # 先复制所有被锁文件
                for src, dst in locked_files:
                    bat_lines.append(f'copy /y "{src}" "{dst}" >nul 2>&1')

                # 复制完成后再启动新 exe
                if getattr(sys, 'frozen', False):
                    exe_path = str(Path(sys.executable))
                    bat_lines.append(f'start "" "{exe_path}"')

                # 延迟后清理临时目录和 bat 自身
                bat_lines.append('timeout /t 3 /nobreak >nul')
                bat_lines.append(f'rmdir /s /q "{update_dir}"')
                bat_lines.append('del "%~f0"')

                bat_path = app_dir / "_update.bat"
                bat_path.write_text("\n".join(bat_lines), encoding="gbk")
                self.progress.emit(100)
                self.finished.emit(True, f"更新已下载（{copied_count} 个文件已替换，{len(locked_files)} 个文件需重启后替换）。\n点击重启完成更新。")
            else:
                # 全部替换成功，清理临时目录
                shutil.rmtree(update_dir, ignore_errors=True)
                self.progress.emit(100)
                self.finished.emit(True, f"更新完成（{copied_count} 个文件已替换）。\n请重启程序以应用新版本。")

        except Exception as e:
            self.finished.emit(False, f"更新失败: {e}")
