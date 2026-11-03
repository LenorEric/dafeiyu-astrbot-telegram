# Telegram 验证状态

本版本使用全新数据。离线回归和模拟 API 结果见本次任务报告；真实 Telegram、模型 API、手机和外部账号均未联调。历史资料中的界面图片仅作为示例，不是当前版本上线证据。

部署后需由主人完成文字、群触发、媒体、语音输出及截图打开确认。API 确认发送与用户确认分别记录，不能将其标记为已读。

源码中 `At.qq` 是 AstrBot 通用消息组件的既定字段名，仅用于其 Telegram 适配器的提及处理，不提供其他平台的接入能力。

本次完整 Python 回归：675 项，674 通过、1 项 Windows named-mutex 测试跳过。钉版镜像中，三个插件可导入，真实 Telegram Update 经访问保护、聊天处理和模拟模型结果后，通过真实 python-telegram-bot 客户端向内存 Bot API 发送成功。另一个完整管线 smoke 已验证真实 AstrBot 启动、长轮询、未授权用户拦截、OpenAI 兼容模型管线和 Telegram 回复；两端均为本地模拟 API，无真实账号和付费调用。

复现：`python -B -m unittest discover -s tests -v`。镜像集成命令：`docker run --rm --network none --entrypoint python -v "$PWD:/repo:ro" -w /AstrBot dafeiyu-telegram:local -B /repo/tests/telegram_runtime_smoke.py`。

完整管线复现：在新的、可丢弃的容器中，将上述镜像集成命令的脚本换成 `/repo/tests/telegram_pipeline_smoke.py`。此测试会写容器内的合成配置和数据库，不能在生产容器执行。

构建期间曾因当前 Docker VFS 层占满磁盘导致一轮测试及构建失败；清理本次测试容器和缓存、合并镜像复制层后，完整 Python 回归重新通过。

最终合并层 Docker 镜像构建通过；基于镜像内代码的完整模拟管线及 Telegram 消息／话题／Opus 上传检查通过。另补充原始 token 与 API URL 日志脱敏测试，通过。Compose 配置、Markdown 本地链接及代码围栏检查通过。
