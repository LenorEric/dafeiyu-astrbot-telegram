# Telegram 运维 MCP

`server.py` 提供 stdio MCP，通过受信任 SSH 连接管理远端 AstrBot。使用 `DAFEIYU_SSH_HOST` 或 `~/.dafeiyu-admin/host` 配置目标；密钥位于 `~/.ssh/ecs_dafeiyu`，必须事先建立 known_hosts 信任。不会禁用主机校验。

只读工具：`health`、`logs`、`plugins`、`cron_jobs`。仅允许 `astrbot` 容器；健康信息显示轮询相关日志，不将容器运行状态视为收发成功。日志隐藏 Bot API token。

`restart` 和 `compose_up` 分别需要字面确认 `RESTART` 和 `UP`。部署目录默认 `/opt/dafeiyu/deploy`，完整仓库应位于 `/opt/dafeiyu`。不提供任意 shell 执行工具。

本地运行 `python -B deploy/ops_mcp/server.py --help` 查看入口；`--selftest` 会访问配置的远端主机，只有配置 SSH 并计划执行只读检查时才运行。MCP 客户端的 stdio 配置使用本机 Python 和此脚本的绝对路径，禁止提交个人机器路径和凭证。
