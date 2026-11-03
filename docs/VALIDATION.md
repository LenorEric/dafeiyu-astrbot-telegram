# Telegram 验证状态

本版本使用独立数据，不导入其他平台身份、聊天或活动账本。历史资料中的界面图片仅作为示例，不是当前版本上线证据。

## 2026-11-03 原生部署检查

- 已以 Python 虚拟环境原生运行并接入 `dafeiyu.service`，启用开机启动；无需 Docker。
- 真实 Telegram 私聊、群聊文字、DeepSeek 对话、私聊表情包以及未点名群文字背景均有运行记录或部署者反馈。群背景的两步测试中，模型正确回答了此前未点名消息中的物品颜色。
- Breeze Blue API 已验证身份、可用模型和音色，完整声音指令下合成的 MP3 已成功解码。真实 AstrBot `Record` 转换及 Telegram 所需的 WAV → OGG/Opus 编码已在本地通过；本地合成和转换不等于用户已收到语音。
- 群贴纸回复的问题已通过真实 PTB/AstrBot 类型复现：数字引用 ID 与用户名 `self_id` 不匹配导致未唤醒。修复后的离线 smoke 验证唤醒及图片保留、私聊兼容、引用其他贴纸，以及未授权消息仍被拦截；真人群贴纸识别效果仍需部署者复测。
- 自动语音十分钟全局冷却、点播绕过且不改动冷却、否定语音请求、语音文字互斥、失败回退、持久化状态、气泡末尾句号与有意保留规则均有回归覆盖。
- 手机、浏览器、长期记忆、B站和其他外部账号能力未在本轮联调，不能因为保留了源码而视为已启用。

复现原生关键检查见 [原生部署与排障经验](native-deployment.md)。下面的镜像测试数量和命令是此前容器版本的历史记录，不代表本次重新完成了整套容器构建或全部测试。

## 此前容器回归记录

部署后需由主人完成文字、群触发、媒体、语音输出及截图打开确认。API 确认发送与用户确认分别记录，不能将其标记为已读。

源码中 `At.qq` 是 AstrBot 通用消息组件的既定字段名，仅用于其 Telegram 适配器的提及处理，不提供其他平台的接入能力。

本次完整 Python 回归：675 项，674 通过、1 项 Windows named-mutex 测试跳过。钉版镜像中，三个插件可导入，真实 Telegram Update 经访问保护、聊天处理和模拟模型结果后，通过真实 python-telegram-bot 客户端向内存 Bot API 发送成功。另一个完整管线 smoke 已验证真实 AstrBot 启动、长轮询、未授权用户拦截、OpenAI 兼容模型管线和 Telegram 回复；两端均为本地模拟 API，无真实账号和付费调用。

复现：`python -B -m unittest discover -s tests -v`。镜像集成命令：`docker run --rm --network none --entrypoint python -v "$PWD:/repo:ro" -w /AstrBot dafeiyu-telegram:local -B /repo/tests/telegram_runtime_smoke.py`。

完整管线复现：在新的、可丢弃的容器中，将上述镜像集成命令的脚本换成 `/repo/tests/telegram_pipeline_smoke.py`。此测试会写容器内的合成配置和数据库，不能在生产容器执行。

构建期间曾因当前 Docker VFS 层占满磁盘导致一轮测试及构建失败；清理本次测试容器和缓存、合并镜像复制层后，完整 Python 回归重新通过。

最终合并层 Docker 镜像构建通过；基于镜像内代码的完整模拟管线及 Telegram 消息／话题／Opus 上传检查通过。另补充原始 token 与 API URL 日志脱敏测试，通过。Compose 配置、Markdown 本地链接及代码围栏检查通过。
