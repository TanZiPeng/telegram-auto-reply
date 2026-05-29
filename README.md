# Telegram 自动回复系统

监听 Telegram 指定文件夹中的对话，使用 AI 自动回复客户的 AWS 技术支持问题。

## 功能

- 监听指定 Telegram 文件夹中的所有对话（群聊 + 私聊）
- AI 智能判断是否需要回复（只回复 AWS 技术相关问题）
- 支持图片理解（客户发截图也能看懂）
- 每个对话独立上下文记忆（SQLite 存储）
- 随机延迟回复（模拟真人）
- 使用你自己的 Telegram 账户发送（客户看不出是机器人）

## 安装

```powershell
cd telegram-auto-reply
pip install -r requirements.txt
```

## 配置

### 1. 获取 Telegram API 凭证

1. 访问 https://my.telegram.org
2. 登录你的 Telegram 账号
3. 点击 "API development tools"
4. 创建应用，获取 `api_id` 和 `api_hash`

### 2. 创建 Telegram 文件夹

1. 在 Telegram 客户端中，长按底部的"聊天"标签
2. 点击"创建文件夹"
3. 命名为"客户"（或你想要的名字）
4. 把需要自动回复的群聊和私聊添加进去

### 3. 编辑 config.yaml

```yaml
telegram:
  api_id: 你的api_id        # 从 my.telegram.org 获取
  api_hash: "你的api_hash"   # 从 my.telegram.org 获取
  folder_name: "客户"        # 你创建的文件夹名称

ai:
  base_url: "https://unifiedapi.cloud/v1"
  api_key: "你的API Key"
  model: "claude-sonnet-4-5-20250514"   # 按实际模型名填写
```

## 运行

```powershell
python main.py
```

首次运行会要求输入手机号和验证码登录 Telegram（只需一次，之后会保存会话）。

## 运行效果

```
==================================================
  博思云 Telegram 自动回复系统
==================================================
[INFO] 已登录: 你的名字 (+86xxxxxxx)
[INFO] 已加载文件夹 '客户'，监听 5 个对话
[INFO] 开始监听... (延迟 5-10s)
[INFO] 按 Ctrl+C 停止
--------------------------------------------------
[MSG] 张三 in 123456: 我的 EC2 实例连不上了怎么办
[WAIT] 等待 7.3s 后回复...
[REPLY] -> 您好，EC2 连不上常见几个原因：1. 安全组没放行...
[MSG] 李四 in 789012: 谢谢
[SKIP] 判断为不需要回复
```

## 后台运行（Windows）

如果想让程序在后台持续运行，可以：

### 方法一：使用 pythonw（无窗口）
```powershell
pythonw main.py
```

### 方法二：注册为 Windows 服务（推荐生产环境）
```powershell
# 安装 nssm
# 下载 https://nssm.cc/download
nssm install TelegramAutoReply "C:\Python312\python.exe" "D:\path\to\main.py"
nssm start TelegramAutoReply
```

### 方法三：使用任务计划程序
设置开机自动启动，触发器选"登录时"。

## 管理命令

在程序运行时，如果你在监听的对话中发送以下命令（以你自己的账户发送），程序会执行对应操作：

- 程序只响应别人发的消息，你自己发的消息会被忽略（`event.out` 过滤）

## 注意事项

1. **封号风险**：使用个人账户做自动化有一定风险，建议：
   - 不要监听太多对话
   - 保持合理的回复频率
   - 如果被 Telegram 警告，立即停止

2. **首次登录**：第一次运行需要输入手机号 + 验证码，之后会话会保存在 `.session` 文件中

3. **模型选择**：确保你的 API 服务支持所配置的模型，且该模型支持图片输入（vision）

4. **上下文**：每个对话独立记忆最近 20 条消息，72 小时后自动过期
