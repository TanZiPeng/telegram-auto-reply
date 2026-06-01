@echo off
echo 正在打包 博思云 Telegram 自动回复系统 v2.0...
.\venv\Scripts\pyinstaller --noconfirm --onedir --windowed ^
    --name "BosiCloud-AutoReply" ^
    --icon "logo.ico" ^
    --add-data "core;core" ^
    --add-data "ui;ui" ^
    --add-data "memory.py;." ^
    --add-data "logo.ico;." ^
    --hidden-import "socks" ^
    --hidden-import "sockshandler" ^
    --hidden-import "PySocks" ^
    --hidden-import "aiohttp" ^
    gui_app.py
echo.
echo 打包完成！输出目录: dist\BosiCloud-AutoReply\
pause
