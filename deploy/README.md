# Telegram 部署

## 必需条件

Docker Compose、可出站访问 `api.telegram.org` 和模型 API 的网络、BotFather 创建的机器人 token、主人数字用户 ID。不要使用用户名作为权限凭据。

在仓库根目录执行：

```sh
cp deploy/.env.example deploy/.env
chmod 600 deploy/.env
# 在本机编辑器中填写 deploy/.env，不要把凭证贴进聊天或日志。
docker compose -f deploy/compose.yaml up -d --build
```

工作目录必须保留完整仓库：镜像从 `deploy/Dockerfile` 构建，数据位于 `deploy/data`。面板仅绑定本机 6185；远程使用 SSH 隧道。首次启动后设置强面板密码。

`TELEGRAM_BOT_TOKEN`、`TELEGRAM_OWNER_ID` 必填；`DEEPSEEK_API_KEY` 用于默认对话模型。`TELEGRAM_ALLOWED_GROUPS` 是逗号分隔的负数群 ID，留空禁用群聊。加入群不会自动授权，必须由部署者更新此列表并重建容器。不要把 token 写到命令行参数。

启动器先生成配置，再安装访问保护，保护初始化失败则停止启动。已有不同平台配置会报冲突；不会自动导入旧数据。首次安装复制仓库插件，后续保留已安装插件及用户配置；升级插件请停容器、备份数据后手动同步对应插件目录，再重启。

## 机器人初始化

1. 在 BotFather `/newbot` 创建机器人；设置名称、简介和头像。
2. 用 Telegram 客户端或可信的 ID 查询方式获取自己的数字用户 ID，配置为主人 ID。
3. 主人先打开机器人私聊并点击 Start，然后发送文字。机器人不能主动建立私聊。
4. 将机器人加入所需群，配置群 ID。默认保留 BotFather 隐私模式，仅响应 @ 或回复机器人。话题群按话题隔离。
5. 非主人私聊、未允许群、其他机器人的消息均被拒绝；群中不开放主人专属审批和工具权限。

同一 token 只运行一个长轮询实例。已有 Webhook 时，先在自己的部署环境取消 Webhook，再启动轮询，不同时运行两条更新消费链路。

## 模型及扩展

面板配置 DeepSeek `https://api.deepseek.com/v1`、`deepseek-chat` 为对话模型。百炼视觉 `qwen3-vl-plus`、ASR `qwen3-asr-flash`、TTS 和音色须单独配置；`DASHSCOPE_API_KEY` 提供媒体理解凭证。TTS 音色在百炼控制台创建后填入提供商配置。缺少凭证时只反馈无法识别，不编造媒体内容。

长期记忆安装 livingmemory，并在面板选择 bge-m3 嵌入提供商（Ollama 或兼容托管服务）。主动联系安装 proactive_chat 后按其文档配置主人会话。手机、浏览器、B站伴随服务分别按子目录文档配置；外部账号写入默认需要主人审批，不因 Telegram 迁移自动开启。

主人会话为 `telegram:FriendMessage:<用户ID>`；群和话题会话使用 `/sid` 实际返回值，不手工猜测。日程、记忆和权限必须使用同一会话标识。生活节律沿用 Asia/Shanghai。

## 限制与诊断

媒体默认最多下载 20 MiB。静态贴纸作为图片处理，动画贴纸仅使用缩略图；上传音频经 AstrBot/FFmpeg 转换。API 回执不等于已读，不存在任意历史消息回读接口。发送超时或部分成功后禁止自动重发。

- 401：检查 token，在 BotFather 撤销后安全更新配置。
- 403：检查主人是否已 Start、机器人是否被屏蔽或移出群。
- 409：停止重复实例，检查已有 Webhook。
- 网络失败：检查 DNS、出站 HTTPS、代理和 CA；保持 TLS 校验，勿使用不明 API 镜像。

`docker compose -f deploy/compose.yaml logs --tail 100 astrbot` 查看脱敏日志。容器进程存在不代表收发链路已验证。真实验收依次测试文字、群触发、图片、语音、视频和主人截图确认。

备份需停止数据写入再打包 `deploy/data`、部署配置和补丁。配置包含凭证，备份按敏感文件保护，禁止上传公开位置。恢复到独立目录并确认无其他实例使用相同 token 后启动。

备份命令：在完整仓库根目录运行 `bash deploy/backup.sh "$PWD"`。恢复前停止机器人，在仓库根目录解压备份；文件路径包含 `deploy/data` 与配套插件和补丁，不包含另行管理的 `.env` 文件。恢复后安全填写 `.env` 并重新启动。备份保留最近七份，恢复启动失败返回非零。
