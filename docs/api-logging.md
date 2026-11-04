# 有界模型 API 日志

服务启动后默认持续记录当前 DeepSeek 官方接口 `api.deepseek.com` 的每次 HTTP 调用，日志位于项目根目录 `logs/model-api.jsonl`。每次实际重试都是独立记录，包括 HTTP 错误、连接失败及辅助 DeepSeek 调用。采集发生在 SDK 的 HTTP 边界，早于正文清理，空白或异常正文也按原始数据保存。此功能覆盖服务进程中的 DeepSeek 调用，不是整台机器的网络抓包。

记录包含本地调用 ID、UTC 起止时间、耗时、请求方法/URL/头/完整 body、响应状态/头/完整 body、可解析的 API response ID，以及完成或失败状态。响应 body 包含模型返回的全部 JSON 字段，例如 `choices`、`reasoning_content`、`usage` 和 `finish_reason`，不是只提取回复正文。认证头、Cookie、API key/Token 头和敏感 URL 查询参数会脱敏；请求 body 的 persona、历史、图片编码等内容按实际发送数据保留。

文件为 UTF-8 JSONL，每行是一条调用。请求开始时先保存 pending 记录，响应完成后用同一 ID 更新；按最近写入顺序保留。流式响应随消费过程收集，不提前读完整流；完整结束才标记 complete，提前取消或关闭会标记 incomplete 并保留已收到字节。网络错误保留已发送请求和异常类型。压缩的 HTTP 响应或非 UTF-8 body 以原始字节的 Base64 保存，并保留头信息。

硬上限为 **1 MiB，即 1,048,576 字节**。写入时从队首淘汰最旧的整条调用，保证剩余记录可解析，不留半行。单条完整记录超过上限时先无损 gzip + Base64 封装；读取工具会校验摘要并自动解包。若单条压缩后仍超过上限，只保留 `oversize_not_stored` 元数据、长度和 SHA-256，并在 service 日志中告警；不会伪装成完整记录或静默裁切正文。有限容量意味着更旧的记录会永久淘汰。

日志目录权限为 700，日志和锁文件为 600。更新通过进程/线程锁和原子替换完成，日志写入失败不会改变模型调用结果。日志目录已加入 Git 和镜像构建忽略规则；它包含聊天、人格及推理等私有内容，只保存在本机。

查看最新一条完整记录：

```bash
.venv/bin/python deploy/read-api-log.py
```

查看最新一条的完整请求体或完整响应体（不是仅正文），压缩 HTTP body 会按编码解开：

```bash
.venv/bin/python deploy/read-api-log.py --part request
.venv/bin/python deploy/read-api-log.py --part response
```

查看多条，或按本地调用 ID / API response ID 查找：

```bash
.venv/bin/python deploy/read-api-log.py --last 5
.venv/bin/python deploy/read-api-log.py --id RESPONSE_ID --part response
```

当前使用普通文本输出，不再进行结构化气泡校验或产生 `Structured reply rejected`。历史日志仍按容量保留，可以通过 response ID 查询。过去只记异常类型且没有抓取的旧回复无法追溯恢复。

回归：`.venv/bin/python -m unittest discover -s tests -p test_api_log.py -v`，覆盖 FIFO 硬上限、完整内容、无损压缩、不可压缩超限、并发更新、HTTP/连接错误、流式正常/提前关闭、认证脱敏及日志失败不影响调用；真实 SDK/普通文本管线协作由 `tests/plain_text_reply_smoke.py` 的本地模拟测试覆盖。
