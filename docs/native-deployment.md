# 原生部署与排障经验

适用于 Python 3.12+、AstrBot v4.29.0 的 Telegram 部署。无需 Docker。这里记录可复用的步骤，不包含部署者身份、聊天内容或真实凭证。

## 首次安装

在完整仓库根目录执行：

```bash
cp deploy/.env.example deploy/.env
chmod 600 deploy/.env
# 用本机编辑器填写 token、主人数字 ID、模型 key 和可选群白名单。
bash deploy/start-local.sh
```

运行文件放在项目内：`.venv` 为 Python 环境，`.runtime/AstrBot` 为固定版本的框架源码，`deploy/data` 为持久数据。`.env` 不作为 shell 脚本执行，只使用 `NAME=value`，不要为值额外加 shell 引号。

首次生成 Telegram 配置和内置插件；已有数据与插件配置会保留。聊天默认使用兼容名称 `deepseek-chat`，可在面板切换为 `deepseek-flash` 并开启对应图片能力。模型实际服务版本、推理模式和默认 effort 以服务端为准；部署时核对官方文档及模型元数据，需要固定行为时显式配置参数。

打开面板后创建人格，将 [大肥鱼人格](../persona/大肥鱼-人格.md) 中分隔线之后的正文导入，设为默认。已有会话若指定过其他人格，还需检查会话覆盖设置。只看到机器人自称“大肥鱼”，不能证明完整人格已加载。

## systemd 常驻

仓库提供 [dafeiyu.service](../deploy/dafeiyu.service)。模板中的用户和绝对路径以示例安装目录为准；部署到其他位置时先修改 `User`、`WorkingDirectory` 与 `ExecStart`。

停止首次运行的前台进程，再执行：

```bash
sudo install -m 644 deploy/dafeiyu.service /etc/systemd/system/dafeiyu.service
sudo systemctl daemon-reload
sudo systemctl enable --now dafeiyu.service
systemctl status dafeiyu
journalctl -u dafeiyu -n 100 --no-pager
```

服务直接调用虚拟环境中的 Python，不在开机时运行安装器。不要同时运行前台进程和 systemd 服务，否则同一 token 的长轮询会冲突。`enabled` 代表开机启动，`active (running)` 才代表进程当前运行。

原生版面板端口为 6185，监听地址由 AstrBot 的 `dashboard.host` 决定，不能因为 Compose 仅映射本机就假定原生版也是如此。首次生成的随机密码只在初次启动时显示；后续配置存储密码哈希，哈希不能直接用于登录。

## FFmpeg 与语音

`pip install imageio-ffmpeg` 不会自动在 shell 中提供名为 `ffmpeg` 的命令。AstrBot 在发送语音前会调用该命令转码，即使 Breeze 已成功返回 MP3，也可能在这一步报 `ffmpeg not found`。

本仓库通过 [requirements-native.txt](../deploy/requirements-native.txt) 固定依赖，由 [native_audio.py](../deploy/native_audio.py) 将二进制链接到 `.venv/bin/ffmpeg`，启动器再把该目录加入 PATH。包升级后失效的链接会重新建立，不需要修改系统 `/usr/bin`。

```bash
.venv/bin/python -m pip install -r deploy/requirements-native.txt
.venv/bin/python deploy/native_audio.py
.venv/bin/ffmpeg -version
sudo systemctl restart dafeiyu
```

Breeze Blue 使用 `.env` 的 `BREEZE_API_KEY`，不要将 key 写入提供商配置。填写 key 后重启，注册类型 `breeze_blue_tts`。在面板添加并启用该类型，模型填 `breeze-tts-2`，音色可填 `voc_8yud7hz7c9q2`（公共音色“大肥鱼（迷糊版）”），将 [声音指令](../deploy/breeze_voice_prompt.txt) 全文填入 `instructions`，并在 TTS 设置中选中该提供商、启用 TTS、关闭文字语音双输出。音色可替换为账号中可用的其他 `voice_id`。

设置 `.env` 中 `DAFEIYU_RARE_VOICE=1` 后重启：普通信息默认用文字，强情绪台词可作为自动语音候选；自动语音全局十分钟最多一次。用户明确或语境明确点播语音时绕过自动冷却，不延长自动冷却。成功只发送语音，合成失败回退文字。上游长度、并发和余额限制仍适用。

关键经验：AstrBot 会在启动时清理不认识的 JSON 配置字段，自定义路由开关因此放在环境变量中。启动日志应显示 `rare_emotional_voice=True`、`global_cooldown_seconds=600`。只确认配置文件写入成功不够，还需确认启动后的配置及日志。

## 群消息与表情包

群数字 ID 必须出现在 `TELEGRAM_ALLOWED_GROUPS` 中，修改后重启。普通 @ 文本和群背景需要 Telegram 实际投递：在 BotFather 为机器人关闭隐私模式，再从群中移除并重新添加。保留隐私模式时先用 `/start@机器人用户名` 或回复机器人消息测试。

明确授权把群背景发往已配置的模型接口后，可开启 `DAFEIYU_GROUP_CONTEXT_ENABLED=1`。缓存只保留同群、同话题此前 20 条、30 分钟内的文字或媒体说明，重启清空；不补读历史，不因普通消息自动调用模型，也不下载未点名的图片或贴纸。

普通消息没有出现在 AstrBot 的对话事件列表，不等于未接收。临时开启 `DAFEIYU_GROUP_CONTEXT_DEBUG=1` 后，接收、缓存快照和请求注入会记录消息编号与数量，不记录普通消息正文。

Telegram 适配器用机器人用户名作为 `self_id`，引用作者却是数字 ID。上游只对文本回复补了唤醒前缀，回复机器人时发送贴纸会因此出现“已经收到图片，却不调用模型”。本仓库覆盖层为这类回复补充匹配的唤醒组件，保留引用作者数字身份；没有放开未授权群或回复其他群友时的触发限制。

静态贴纸按图片处理，动态/视频贴纸只读取缩略图。回复其他人的贴纸时仍需 @ 机器人；回复机器人的消息来发送贴纸则可以直接触发。

## 气泡与句号

模型可以生成多句、多段，先按原有规则拆分和合并气泡，再决定发送时的末尾句号。默认只删除每个最终气泡末尾句号，中间句号不受影响；表达不满、刻意冷淡或傲娇时，可通过内部控制约定保留结尾的一个句号。问号、感叹号和代码不做这种删除。原始模型文本、保存的对话和最终展示文本可能因此不同。

## 升级、备份与验证

升级前停止服务，对 `deploy/data` 做一致性备份，并单独保护 `.env`。现有插件不会被初始化器覆盖；审查新版后手动同步需要升级的插件源码，再运行 `.venv/bin/python deploy/setup-native.py` 应用框架补丁和依赖，最后启动服务。`deploy/backup.sh` 依赖 Docker，不能直接当作 systemd 备份脚本使用。

不要提交 `.env`、`deploy/data`、根目录备份、`.venv`、`.runtime`、服务日志或试听文件。数据库和备份可能含有聊天、推理字段及其他凭证。对外分享日志时先脱敏 token、API key 和初始面板密码。

需要检查下一次 DeepSeek 请求时，可在 `deploy/data/debug_api/` 创建空文件 `capture-next`（目录权限 700、文件权限 600）。原生入口在 HTTP 发送边界检查此标记，下一次发往官方 `/v1/chat/completions`、模型为 `deepseek-flash` 的请求会消耗标记，并在该目录的新子目录中保存 `request.log`、原样请求体 `request-body.json`、原样非流式响应体 `response-body.json` 和响应状态 `response.log`。认证头不采集；正文包含真实聊天、人格和推理，仅保存在本机且文件权限为 600。标记按 HTTP 尝试消费，失败不会自动再抓；流式响应仅记录状态，不额外读取响应流。若开启了主动对话，下一次主动调用也可能先消耗标记，可按请求正文核对目标消息。没有标记时不记录 API 内容，旧请求无法事后恢复为原始请求。

本地关键检查：

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m unittest discover -s tests -p 'test_telegram_*.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_rare_voice.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_breeze_tts.py' -v
.venv/bin/python tests/test_chat_layout.py
.venv/bin/python tests/test_face_rules.py
.venv/bin/python tests/telegram_sticker_smoke.py
```

贴纸 smoke 使用真实 PTB 和 AstrBot 类型，但 Bot API、贴纸下载和模型均不访问外网，不发送真实消息。完整运行状态应另看 [验证记录](VALIDATION.md)。

网络排障要区分执行环境：命令沙箱内 DNS 失败并不能证明宿主机服务也无法联网。分别核对服务日志、运行用户的出站网络、DNS、代理和 CA。保持 TLS 校验，不用不明 API 镜像替代官方接口。
