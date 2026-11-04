# JSON 气泡协议

原生部署对使用大肥鱼人格的 `deepseek-flash` 非流式聊天请求，在 HTTP 调用前显式设置 `response_format: {"type":"json_object"}`。协议说明包含 `json` 字样和完整示例，符合 [DeepSeek JSON Output 文档](https://api-docs.deepseek.com/zh-cn/guides/json_mode/) 的要求。JSON 模式保证语法格式，程序仍需验证字段，不能当作严格 JSON Schema 服务。辅助图片分析、摘要等未带协议标记的调用保持各自格式；`thinking` 与 `reasoning_effort` 继续按已有模型配置发送。

```json
{
  "v": 1,
  "bubbles": [
    {"text": "你总算来啦", "emotion": "happy", "ending": "omit"},
    {"text": "哼，刚才才没有在等你", "emotion": "tsundere", "ending": "period"}
  ],
  "voice": "none"
}
```

- `bubbles` 按顺序直接对应气泡，通常 1～3 个，最多 6 个。超过 6 个时把多余内容合进最后一泡，保留全文。长解释、列表、代码可放在同一泡；超过旧的 150 字阈值也不会改变已指定的边界。Telegram 超长消息的 4096 字符切分仍生效。
- `text` 是最终正文，可包含 Markdown、换行、代码、公式和用户要求的 JSON；对话历史保存为可读文本，原始 HTTP 响应仍保留原始 JSON（仅在显式抓取或调试保存时落盘）。推理继续来自 API 独立的 `reasoning_content`，不放进气泡协议。
- `emotion` 可为 `neutral`、`happy`、`excited`、`surprised`、`pouting`、`shy`、`touched`、`cold`、`displeased`、`tsundere`、`serious`、`sad`。情绪只是呈现元数据，不额外添加舞台动作或旁白。
- `ending` 默认 `omit`，仅处理气泡收尾句号，中间标点不动。`period` 只在 `cold/displeased/pouting/tsundere` 时有效，收尾一个句号；认真讲解的 `serious` 不享有例外。问号、叹号、省略号、代码和 URL 保留。新协议不用 `[[KEEP_PERIOD]]`。
- `voice` 可为 `none/auto/requested`。`auto` 还要求至少一泡为 `excited/surprised/pouting/shy/touched`，并经过原有全局十分钟冷却；当前用户点播语音绕过自动冷却，明确只要文字时优先文字。成功只发整轮一条语音，失败回退原有文字气泡。语音文本保留气泡之间的停顿；新协议不用 `[[VOICE:...]]`。
- `bubbles: []` 与 `voice: "none"` 表示静默，仍须遵守人格中无需回复的判断。原生 `tool_calls` 继续使用原有接口、参数和 ID，不伪装成聊天 JSON。

处理链路：请求注入协议 → Provider 设置 JSON Output → 验证并解码最终 JSON → 各气泡清理与标点处理 → 表情转换时保留气泡编号 → 按明确边界发送，或整轮 TTS。第一泡立即发送，后续仍按已有配置间隔发送。

对空白、无效 JSON 或字段不合法的回复最多追加一次修复请求；仍失败则返回可读的格式错误提示，不把协议壳发给用户。若 `finish_reason` 为 `length`，直接兜底，避免盲目重复同一个超长请求。未显式设置新的生成 token 上限，沿用当前模型配置与 API 默认值；合法结构也不能保证内容事实正确。

协议源文件是 `deploy/patches/structured_reply.py`，Provider 适配在 `deploy/telegram/structured_output.py`，聊天插件在 `plugin/astrbot_plugin_telegram_chat/main.py`。原生安装器负责复制 pipeline 补丁；更新现有部署时也需同步插件文件到 `deploy/data/plugins/astrbot_plugin_telegram_chat` 并重启服务。可在本地 `.env` 设置 `DAFEIYU_STRUCTURED_REPLY=0` 后重启，恢复旧标记与正则分段，不删除历史。

离线校验：`python -m unittest discover -s tests -p test_structured_reply.py -v`；安装 AstrBot 运行环境后可运行 `.venv/bin/python tests/structured_reply_smoke.py`，使用真实 SDK/Provider/插件和本地模拟 HTTP，不向 Telegram 或模型接口发送内容。
