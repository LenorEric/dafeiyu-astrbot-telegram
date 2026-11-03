# 🐋 大肥鱼 · Telegram 机器人

基于 AstrBot 4.29.0 的 Telegram 专用机器人。保持鲸鱼娘人格，支持私聊、指定群、话题隔离、图片、语音、视频、日程、长期记忆及有界自主活动。

链路：Telegram → Bot API 长轮询 → AstrBot → 聊天插件／模型／工具 → Telegram。无需公网回调端口。默认仅主人私聊和指定群可用，群中通过 @ 或回复机器人触发。

## 开始使用

在 BotFather 创建机器人，取得 token；按 [部署指南](deploy/README.md) 填写本地安全配置并启动。真实 token 不提交到仓库。

- [人格和模型导入](docs/导入指南.md)
- [指令手册](docs/指令手册.md)
- [B站自主活动](deploy/bili_activity/README.md)：审批、预算、来源笔记、创作和跨日项目。
- [手机控制](deploy/phone_mcp/README.md)及[只读浏览器](deploy/browser_use/README.md)：可选外部工具。
- [记忆观测台](deploy/memory_observatory/README.md)：本地演示或显式 SSH 只读来源。
- [验证状态](docs/VALIDATION.md)

核心插件：`astrbot_plugin_telegram_chat`、`astrbot_plugin_schedule_awareness`、`astrbot_plugin_bili_activity`。第三方 livingmemory、proactive_chat 和情绪插件按扩展文档安装；未安装或未配置的能力不能视为已启用。

这是独立数据的新 fork，不导入其他平台身份、记忆或活动账本。Telegram API 接受消息不代表用户已读；截图验收需要主人明确确认。真实机器人和付费 API 尚未联调。

角色为 DeepSeek 蓝鲸社区二创，非官方形象。项目许可证见 [LICENSE](LICENSE)；第三方补丁保留各自的许可与出处。
