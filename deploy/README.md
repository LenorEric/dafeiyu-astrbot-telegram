# Telegram 部署

## 必需条件

Python 3.12+、可出站访问 `api.telegram.org` 和模型 API 的网络、BotFather 创建的机器人 token、主人数字用户 ID。不要使用用户名作为权限凭据。原生部署不需要 Docker；容器部署才需要 Docker Compose。

在仓库根目录执行：

```sh
cp deploy/.env.example deploy/.env
chmod 600 deploy/.env
# 在本机编辑器中填写 deploy/.env。
bash deploy/start-local.sh
```

首次启动会下载 AstrBot v4.29.0 到 `.runtime/AstrBot`，在 `.venv` 安装依赖，应用补丁并以前台进程运行；后续启动复用源码和依赖。数据位于 `deploy/data`，完整仓库需要保留。面板端口为 6185，原生版的监听地址取决于 `dashboard.host`；需要仅本机访问时在面板或配置中显式设为 `127.0.0.1`，远程使用 SSH 隧道。首次启动的随机密码见本机日志。

systemd 常驻、人格导入、Breeze 配置及升级步骤见[原生部署与排障经验](../docs/native-deployment.md)。服务直接运行虚拟环境中的 Python，不在每次开机时安装依赖。

容器方式仍可用：`docker compose -f deploy/compose.yaml up -d --build`。镜像从 `deploy/Dockerfile` 构建；Compose 只将面板映射到主机 `127.0.0.1:6185`。

`TELEGRAM_BOT_TOKEN`、`TELEGRAM_OWNER_ID` 必填；`DEEPSEEK_API_KEY` 用于默认对话模型。`TELEGRAM_ALLOWED_GROUPS` 是逗号分隔的负数群 ID，留空禁用群聊。加入群不会自动授权，必须由部署者更新此列表并重启进程或重建容器。不要把 token 写到命令行参数。

启动器先生成配置，再安装访问保护，保护初始化失败则停止启动。已有不同平台配置会报冲突；不会自动导入旧数据。首次安装复制仓库插件，后续保留已安装插件及用户配置；升级插件请停止服务、备份数据后手动同步对应插件目录，再重启。

## 机器人初始化

1. 在 BotFather `/newbot` 创建机器人；设置名称、简介和头像。
2. 用 Telegram 客户端或可信的 ID 查询方式获取自己的数字用户 ID，配置为主人 ID。
3. 主人先打开机器人私聊并点击 Start，然后发送文字。机器人不能主动建立私聊。
4. 将机器人加入所需群，配置群 ID。若要使用普通 `@机器人 你好`，在 BotFather 用 `/setprivacy` 为该机器人选择 Disable，然后从群移除并重新添加，使新隐私设置在群内生效。程序仍仅响应 @ 或回复机器人，不响应普通群聊。保留隐私模式时，用 `/start@机器人用户名` 或回复机器人的消息测试；不要假定普通 @ 文本一定会被 Telegram 投递。话题群按话题隔离。
5. 非主人私聊、未允许群、其他机器人的消息均被拒绝；群中不开放主人专属审批和工具权限。

在部署者明确授权将授权群的近期发言发送到已配置的模型 API 后，将 `.env` 中的 `DAFEIYU_GROUP_CONTEXT_ENABLED` 设为 `1` 并重启。此开关默认关闭；关闭时不缓存普通群消息，也不附加群背景。开启后，授权群的近期文字和媒体说明会缓存在进程内，仅在被 @ 或回复时作为背景交给模型，不因普通群消息自动回复。每次最多引用此前 20 条、30 分钟以内的发言；单条文字最多 800 字符，总文字最多 8000 字符，按群和话题隔离，重启后缓存清空。未点名的图片、语音、视频不下载或识别，只缓存已有的文字说明。只有 Telegram 实际投递给机器人的消息才能进入缓存，启动前的群历史无法自动补读。引用背景通过本次请求的系统提示词附加，不写成独立的聊天记录；模型生成的回复仍按原有会话设置保存。

同一 token 只运行一个长轮询实例。已有 Webhook 时，先在自己的部署环境取消 Webhook，再启动轮询，不同时运行两条更新消费链路。

## 模型及扩展

Breeze Blue 语音：在 `.env` 设置 `BREEZE_API_KEY` 和 `DAFEIYU_RARE_VOICE=1`；提供商类型 `breeze_blue_tts` 从环境变量取 key，使用 `breeze-tts-2`、`大肥鱼（迷糊版）`（`voc_8yud7hz7c9q2`）及 `deploy/breeze_voice_prompt.txt` 中的完整指令。关闭 TTS 配置中的 `dual_output`。调度开关必须通过环境变量设置，AstrBot 会清理未知 JSON 配置字段。模型只为强烈而丰富的情绪台词提出语音候选，普通信息回复仍用文字。唯一频率限制是跨所有群聊/私聊共用的十分钟冷却；没有回复次数间隔、随机概率或每日次数上限。冷却状态在 `deploy/data/plugin_data/rare_voice/cooldown.json` 持久保存，重启不重置；在合成请求前预留，失败也进入冷却以避免重复费用。成功只发语音，合成失败只发原文字；`/voice_off` 可关闭所在会话的语音，`/voice_on` 恢复候选功能。请求只向 `https://api.breeze.blue` 发送选中台词和声音指令，不发送群背景或完整聊天记录。供应商本身的文本长度、并发及余额限制仍适用。

上述十分钟冷却只限制自动语音。用户本轮明确或语境中明确点播语音、想听声音、朗读或唱一段时，走独立的点播路径，不读取、不消耗也不延长自动语音冷却，不要求强情绪。当前用户的文字要求优先；群背景、引用和代码中的“发语音”不作为直接点播。唱歌请求可生成适合语音演绎的内容，但 TTS 不保证旋律或伴奏。两条路径都沿用原有 TTS 启用状态、语音/文字互斥及失败回退行为。

面板配置 DeepSeek `https://api.deepseek.com/v1`、`deepseek-chat` 为对话模型。百炼视觉 `qwen3-vl-plus`、ASR `qwen3-asr-flash`、TTS 和音色须单独配置；`DASHSCOPE_API_KEY` 提供媒体理解凭证。TTS 音色在百炼控制台创建后填入提供商配置。缺少凭证时只反馈无法识别，不编造媒体内容。

长期记忆安装 livingmemory，并在面板选择 bge-m3 嵌入提供商（Ollama 或兼容托管服务）。主动联系安装 proactive_chat 后按其文档配置主人会话。手机、浏览器、B站伴随服务分别按子目录文档配置；外部账号写入默认需要主人审批，不因 Telegram 迁移自动开启。

主人会话为 `telegram:FriendMessage:<用户ID>`；群和话题会话使用 `/sid` 实际返回值，不手工猜测。日程、记忆和权限必须使用同一会话标识。生活节律沿用 Asia/Shanghai。

## 限制与诊断

大肥鱼的收尾句号在发送前按最终气泡处理：默认去掉气泡末尾句号，不以长度或中间标点作例外；中间句号、问号、感叹号和代码保持原样，不限制一轮只能有一句。只有表达不满、刻意冷淡或傲娇态度时才保留结尾的一个句号；认真讲解不再作为保留理由。情绪句号通过请求中的内部控制约定传递，控制标记在分段、朗读和保存历史之前消费，不会发给用户。模型原始文本与最终气泡文本因此可能不同。

本机音频依赖声明在 `deploy/requirements-native.txt`。`imageio-ffmpeg` 提供打包的二进制，`deploy/native_audio.py` 将它链接到项目 `.venv/bin/ffmpeg`；本机启动器在加载 AstrBot 前将该目录加入 PATH，供 AstrBot 的音频转换及 Telegram OGG/Opus 编码共用。仅安装 Python 包并不能保证 `ffmpeg` 命令可被服务找到。补装可运行 `.venv/bin/python -m pip install -r deploy/requirements-native.txt`；重启服务即可重新确认可执行链接和 PATH。

普通群消息只在入口缓存，不进入 AstrBot 对话事件列表；看不到普通消息的对话日志不代表未接收。调试时可在 `.env` 设置 `DAFEIYU_GROUP_CONTEXT_DEBUG=1` 并重启，观察 `group context receive`（接收及是否缓存）、`group context snapshot`（带入多少条背景）和 `group context injected`（已附加到模型请求）。这些诊断只记录消息编号、群/话题与数量，不记录普通消息正文；排查结束可设回 `0`。

媒体默认最多下载 20 MiB。静态贴纸作为图片处理，动画贴纸仅使用缩略图；上传音频经 AstrBot/FFmpeg 转换。API 回执不等于已读，不存在任意历史消息回读接口。发送超时或部分成功后禁止自动重发。

- 401：检查 token，在 BotFather 撤销后安全更新配置。
- 403：检查主人是否已 Start、机器人是否被屏蔽或移出群。
- 409：停止重复实例，检查已有 Webhook。
- 网络失败：检查 DNS、出站 HTTPS、代理和 CA；保持 TLS 校验，勿使用不明 API 镜像。

原生服务使用 `journalctl -u dafeiyu -n 100 --no-pager` 查看日志；容器使用 `docker compose -f deploy/compose.yaml logs --tail 100 astrbot`。运行状态正常不代表收发链路已验证。真实验收依次测试文字、群触发、图片、语音、视频和主人截图确认。

备份需停止数据写入再打包 `deploy/data`、部署配置和补丁。配置包含凭证，备份按敏感文件保护，禁止上传公开位置。恢复到独立目录并确认无其他实例使用相同 token 后启动。

`deploy/backup.sh` 使用 Docker 命令管理容器，只适用于 Compose 部署。原生部署应先 `systemctl stop dafeiyu`，再备份 `deploy/data`、配套插件/补丁和单独保护的 `.env`，完成后启动服务。恢复前停止机器人，恢复数据并确认凭证及群白名单，确保没有第二个实例使用相同 token。
