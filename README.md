# 🐋 大肥鱼 · Telegram 机器人

基于 AstrBot 4.29.0 的 Telegram 专用机器人。保持鲸鱼娘人格，支持私聊、指定群、话题隔离、图片、语音、视频、日程、长期记忆及有界自主活动。

链路：Telegram → Bot API 长轮询 → AstrBot → 聊天插件／模型／工具 → Telegram。无需公网回调端口。默认仅主人私聊和指定群可用，群中通过 @ 或回复机器人触发。普通 @ 文本需要按部署指南配置 Telegram 隐私模式；保留隐私模式时使用显式命令或回复消息。

## 开始使用

在 BotFather 创建机器人，取得 token；按 [部署指南](deploy/README.md) 填写本地安全配置并启动。支持 Python 3.12 原生运行及 systemd 常驻，无需 Docker；也保留 Docker Compose 方式。真实 token 不提交到仓库。

- [原生部署与排障经验](docs/native-deployment.md)：虚拟环境、systemd、FFmpeg、群隐私模式和配置迁移。
- 授权群可选开启最近 20 条／30 分钟文字上下文，仅在被点名时调用模型，按群和话题隔离。
- Breeze Blue 语音支持完整音色指令；自动情绪语音共享十分钟冷却，用户点播独立处理，文字与语音互斥。
- [JSON 气泡协议](docs/json-replies.md)：显式气泡边界、情绪、收尾句号及语音意图，配合 v2.3 人格；提供字段校验和异常兜底。

- [人格和模型导入](docs/导入指南.md)
- [指令手册](docs/指令手册.md)
- [B站自主活动](deploy/bili_activity/README.md)：审批、预算、来源笔记、创作和跨日项目。
- [手机控制](deploy/phone_mcp/README.md)及[只读浏览器](deploy/browser_use/README.md)：可选外部工具。
- [记忆观测台](deploy/memory_observatory/README.md)：本地演示或显式 SSH 只读来源。
- [验证状态](docs/VALIDATION.md)

核心插件：`astrbot_plugin_telegram_chat`、`astrbot_plugin_schedule_awareness`、`astrbot_plugin_bili_activity`。第三方 livingmemory、proactive_chat 和情绪插件按扩展文档安装；未安装或未配置的能力不能视为已启用。

这是独立数据的新 fork，不导入其他平台身份、记忆或活动账本。Telegram API 接受消息不代表用户已读；截图验收需要主人明确确认。文字对话、群背景和图片链路已在部署环境检查，Breeze 合成及音频格式转换已验证；动态贴纸仍只读取缩略图，离线回归不代表所有媒体场景均已完成真人验收。

角色为 DeepSeek 蓝鲸社区二创，非官方形象。项目许可证见 [LICENSE](LICENSE)；第三方补丁保留各自的许可与出处。
