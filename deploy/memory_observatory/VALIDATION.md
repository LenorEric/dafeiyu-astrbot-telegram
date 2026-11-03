# 扩展验证

当前 Telegram 版本仅有离线验证。真实设备、账号、SSH 和模型均需部署后另行验收。

从仓库根目录运行 `python -B -m unittest discover -s tests -v`；观测台可用 `python -B -m deploy.memory_observatory.server --port 8766` 启动虚构数据演示。真实模式须显式配置可信 SSH，不会失败后静默回退演示。

截图必须核对 Telegram API 返回的目标 chat_id、消息 ID 与 photo_file_id，再由主人确认打开；不能要求 Bot API 不提供的消息回读。B站操作的回读验证仍独立保留。
