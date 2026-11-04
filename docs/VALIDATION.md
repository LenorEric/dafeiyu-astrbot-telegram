# Telegram 验证状态

本版本使用独立数据，不导入其他平台身份、聊天或活动账本。历史资料中的界面图片仅作为示例，不是当前版本上线证据。

## 2026-11-04 当前普通文本部署

- 按要求移除 JSON Output 请求模式、气泡协议提示、专用 Provider 解码/修复、气泡编号适配及对应测试；清理 persona 中 JSON 表述并逐字同步到数据库，保留其他人格内容和会话历史。
- 真实 AstrBot/SDK 加本地模拟 HTTP 通过：请求无 `response_format` 和气泡协议，普通正文经表情、分句和末尾标点处理后按预期发送；自动及点播语音路由、thinking enabled / high 和完整 HTTP 日志保留。未向 Telegram 或付费模型发送测试内容。
- 气泡/句号、表情规则、6 项语音测试和 12 项 API 日志测试均通过。复现普通文本集成：`.venv/bin/python tests/plain_text_reply_smoke.py`。

## 2026-11-04 此前 JSON 实验验证（已撤销）

- 持久 API 日志的 12 项测试通过，覆盖 1 MiB FIFO、完整记录、超限压缩、并发、错误、流式及脱敏；真实 SDK 模拟集成确认 reject 原始响应和修复请求均留存。启用后服务重启正常，日志文件已创建为 600、目录 700；启用时尚无新的真人调用，不额外发送付费验证请求。
- 仓库 v2.3 人格分隔线后的正文已与运行数据库逐字比对并同步，保留人格工具、技能、默认选择及现有会话绑定。`dafeiyu.service` 重启后处于 active，日志确认人格、Telegram 插件、TTS 路由加载及 AstrBot 启动完成，无本次启动 traceback。
- 新增 9 项 JSON 协议单元测试通过，覆盖字段校验、末尾句号、情绪约束、代码/链接、用户 JSON 正文、静默及超额气泡保留全文；旧气泡、表情规则与 6 项语音回归通过。
- 真实 AstrBot Provider、OpenAI SDK、聊天插件、装饰和发送阶段配合本地 HTTP 模拟，通过显式四气泡（含无标点、表情和超过 150 字的气泡）原样发送；空白修复、错误结构兜底、辅助调用不受影响、原生工具 ID/参数、自动与点播语音路由通过。
- DeepSeek 真实接口仅使用通用协议和合成句子验证：`response_format=json_object` 与 thinking enabled / high 同时返回 HTTP 200、finish_reason stop；合法两泡经处理得到“我来啦”和“不理你了。”。未在该真实验证中发送完整 persona、聊天历史或工具定义，也未向 Telegram 发送测试消息。完整 persona 和工具的组合兼容性由本地模拟集成覆盖；最终真人聊天效果仍需运行中观察。

以上 JSON 实验适配已移除，现行处理方式见 [普通文本消息处理](text-replies.md)。

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
