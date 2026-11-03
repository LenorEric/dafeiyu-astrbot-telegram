> Telegram 专用版本。本文不构成真实账号联调记录；配置与验收以部署指南和验证报告为准。

# 大肥鱼 B 站自主活动与截图分享

当前代码为自主生活 **v0.4.1**（v0.4.0 研究方法 + 工具截图上下文修复），在[持续目标、经历与预算](LIFE_V02.md)、[来源笔记与自主续写](LIFE_V03.md)之上增加[研究方法提炼、版本与复用结果](LIFE_V04.md)。新功能默认关闭，现有人格、周期与免打扰配置保留。

## 文件与部署位置

以上是默认目标路径，**不代表已在这些位置安装**。必须先从实际主机确认部署根目录、容器名、Docker 网关、PhoneMCP 地址和版本。

## 连接结构

```text
Windows emulator-5554
  ├─ 现有 PhoneMCP ─ 原有 8009 连接 ─ AstrBot：真实截图、已有手机工具
  └─ 新增 Bili MCP 127.0.0.1:8011/mcp
       └─ SSH 反向转发 → 云端 127.0.0.1:8011
            └─ Docker 私有网关:8011 → AstrBot 活动插件内的 MCPClient
```

Bili 服务使用真正的 MCP Streamable HTTP；PhoneMCP 继续使用 SSE。云端 `172.18.0.1:8010` 已被现有 browser-use MCP 占用，因此本服务固定使用 **8011**，两端端口必须一致。候选 `Iseenope/bilibili-mcp-server` 仅支持 stdio，已审查其源码，但本实现没有把 stdio 地址伪装为 HTTP 服务。新增服务实现所需端点，并把执行接口限制在控制插件内；**不要将伴随服务的全部工具直接注册到 AstrBot 的普通聊天工具列表**。插件只向 Agent 暴露 `df_*` 工具，执行写入由真实 Telegram 答复触发。

较大媒体仅在 Windows 下载、抽帧与切音频；单次下载预算 160 MiB、分析最长 300 秒、最多 8 帧，返回媒体包不超过 3 MiB。云端复用已加载 `telegram_chat` 的 `_vl_describe` 和 `_asr_file`。字幕存在时优先使用字幕；失败保留已取得的部分。记录的是抽样分析时间和证据，不宣称连续看完了整段视频。

## 首次安装与联调顺序

1. 在实际云主机核对现有人格、主人私聊 `unified_msg_origin`、主人 Telegram 数字用户 ID、免打扰时段、PhoneMCP 配置、telegram_chat 的视觉/转写配置和 LivingMemory 版本。只读取所需字段，不输出密钥、Cookie、完整配置文件。`owner_scope` 不可照抄仓库其他用户 ID。活动只允许发到核实过的主人私聊；群聊不会继承私聊审批或记忆。
2. 将本仓库的新文件放到实际云主机，在仓库根执行下述安装命令。脚本在覆盖插件/工具前归档旧文件和受影响配置，SQLite 使用在线备份及完整性检查，保留已有 `control.json`。备份位于 `/opt/dafeiyu/backups/bili-activity-*.tar.gz`。脚本不会改动其他 cron、人格、语音或身份识别设置；已有暂停任务继续保持暂停。

   ```bash
   bash deploy/bili_activity/deploy.sh /opt/dafeiyu --install-deps
   ```

   非默认容器名通过 `ASTRBOT_CONTAINER` 指定；非默认数据挂载需先调整并核对脚本中的容器路径。依赖检查通过后，在 AstrBot 管理界面仅重载新插件。必须检查真实插件加载日志；本地 SDK 替身测试不能替代这一步。

3. 将 `deploy/bili_activity` 文件放到 Windows 的 `D:\AI\BiliActivity\src`。使用 Python 3.12+，把 `ffmpeg.exe` 放到 `D:\AI\BiliActivity\bin`（或启动时用 `-FfmpegDir` 指向实际目录），确认 `D:\leidian\LDPlayer14\adb.exe -s emulator-5554 get-state` 返回在线。Windows 还需 `tzdata`（已在 requirements.txt）。在 PowerShell 执行（主机、SSH 端口与密钥路径使用现有实际值）：

   ```powershell
   cd D:\AI\BiliActivity\src
   .\start_bili_service.ps1 -Server <实际云主机> -User <现有SSH用户> -Key <现有私钥路径>
   .\status_bili_service.ps1
   ```

   脚本创建独立 venv、运行 `preflight.py`（Python、时区、ffmpeg、ADB、8011 端口），通过后才启动本地服务和 8011 隧道；复用现有 SSH 身份，保留原 PhoneMCP 8009 连接。首个 SSH 主机指纹必须已经通过现有连接信任，不自动关闭主机校验。云端代理仅绑定实际 Docker 私有网关，默认 `172.18.0.1`，不绑定公网。单独预检可用：

   ```powershell
   .\.venv\Scripts\python.exe .\preflight.py --adb D:\leidian\LDPlayer14\adb.exe --ffmpeg-dir D:\AI\BiliActivity\bin --port 8011
   ```

   需要登录自启时，运行 `.\install_bili_autostart.ps1 -Server <主机>`（写入当前用户启动目录，不需要管理员；`-Remove` 卸载）。不传 `-Server` 时读取 `DAFEIYU_SSH_HOST` 或 `~/.dafeiyu-admin/host`。它只启动 Bili 服务与隧道，PhoneMCP 和模拟器仍需各自的启动方式。

   ```powershell
   D:\AI\BiliActivity\.venv\Scripts\python.exe .\login.py --state-dir D:\AI\BiliActivity\state
   ```

5. 核对当前 PhoneMCP 源码及未提交改动，备份 `phone_mcp/adb/screenshot.py`、`phone_mcp/server.py`、`phone_mcp/cli.py` 后，先执行 `git apply --check <补丁绝对路径>`，再应用补丁并按现有方式重启 PhoneMCP。补丁以 PhoneMCP v0.5.0 审查版本为基础；检查失败时不能强行覆盖现有代码。插件也会拒绝旧实现返回的纯黑兜底图。
6. 在云端写入已核对的私聊和免打扰设置。下例的变量应由现场读取结果填入；`ACTUAL_DND_JSON` 为例如 `[["23:00","08:00"]]` 的 JSON，只有确认原来没有免打扰时才能用 `[]`：

   ```bash
   python3 /opt/dafeiyu/tools/bili_activity/ops.py configure \
     --owner-scope "$ACTUAL_OWNER_SCOPE" --owner-id "$ACTUAL_OWNER_ID" \
     --dnd-ranges "$ACTUAL_DND_JSON"
   python3 /opt/dafeiyu/tools/bili_activity/ops.py status
   ```

   在 AstrBot 的实际容器内验证两个 MCP 的初始化与工具调用，然后核对实际会话使用的视觉模型能看到截图、工具结果能回到聊天模型，不能仅凭“截图成功”验收。
7. Telegram 发送“截图看看”，核对收到可打开的当前真实画面、简短配文、`message_id` 与读回图片段。之后创建三分钟后触发的一次性活动：

   ```bash
   python3 /opt/dafeiyu/tools/bili_activity/ops.py once --delay-seconds 180
   ```

   此时周期任务仍关闭。活动按实际内容决定是否分享；不能为了验收伪造有趣画面或假装自主选择。一次未分享不能作为主动截图通过证据。
8. 对真实活动的内容、时间、截图及操作闭环验收后，填写证据 JSON（真实值，不可从单元测试复制）：

   ```json
   {
     "run_id": "真实运行ID",
     "read_content_verified": true,
     "screenshot_opened": true,
     "telegram_screenshot_message_id": "真实Telegram消息ID"
   }
   ```

   ```bash
   python3 /opt/dafeiyu/tools/bili_activity/ops.py accept-one-shot --evidence /实际路径/acceptance.json
   python3 /opt/dafeiyu/tools/bili_activity/ops.py enable-periodic
   ```

   命令要求同一次已完成活动存在实际自动分享、发送回执和图片读回记录。证据中的“可打开”仍需主人在 Telegram 真实确认。评论及各项管理操作必须另按具体提议批准并逐项验收，不能由这个开关替代。

## 启停、日志与开关

以下命令用于完成首次配置后的实际主机。`ops.py` 默认数据目录见上表，非默认位置统一加 `--data-dir <实际目录>`，放在子命令之前。

| 目的 | 云端命令 |
| --- | --- |
| 立即禁止自主浏览并取消本插件当前活动 | `python3 /opt/dafeiyu/tools/bili_activity/ops.py stop` |
| 允许活动但不自动启用周期 | `python3 /opt/dafeiyu/tools/bili_activity/ops.py start` |
| 首次或再次安排一次性运行 | `python3 /opt/dafeiyu/tools/bili_activity/ops.py once --delay-seconds 180` |
| 一键启动已验收的周期活动 | `python3 /opt/dafeiyu/tools/bili_activity/ops.py enable-periodic` |
| 只暂停周期 | `python3 /opt/dafeiyu/tools/bili_activity/ops.py disable-periodic` |
| 查看开关、最近活动、提议、Telegram 回执 | `python3 /opt/dafeiyu/tools/bili_activity/ops.py status` |
| 最近结构化日志 | `python3 /opt/dafeiyu/tools/bili_activity/ops.py logs --lines 100` |
| AstrBot 加载/异常日志 | `docker logs --tail 100 astrbot` |
| 云端代理日志 | `bash /opt/dafeiyu/tools/bili_activity/cloud_service.sh logs` |

| 功能 | `control.json` 字段 / 默认 | 修改命令 |
| --- | --- | --- |
| 自主浏览 | `enabled=false`、`periodic_enabled=false` | `start` / `stop` / `enable-periodic` |
| 发表评论、回复评论、发弹幕 | `public_interactions=false` | `ops.py switch public_interactions on` 或 `off` |
| 点赞/取消赞、投币 | `engagement_actions=false` | `ops.py switch engagement_actions on` 或 `off` |
| 回复监听、评论观察 | `reply_watch_enabled=false`、`comment_learning_enabled=false` | `ops.py switch <字段> on` 或 `off` |
| 收藏、收藏夹、关注与取消关注 | `collection_management=false` | `ops.py switch collection_management on` 或 `off` |
| 主动与被动截图分享 | `screenshot_enabled=true` | `ops.py switch screenshot_enabled on` 或 `off` |

默认 `interaction_mode=approval`：开关开启后仍需展示精确对象和完整内容，收到同一主人私聊随后发来的“可以”才执行；“算了”撤销。提议默认一小时过期，同时最多一个未决提议。v0.5 另有显式选择的自动模式，规则、推荐低配额、主人命令和回滚见 [INTERACT_V05.md](INTERACT_V05.md)。收藏/关注管理始终逐条审批。写入超时或结果不明会标为 `uncertain`，不得用新操作 ID 自动重试；先按账本中的对象和内容现场核对。

主人可发 `/bili互动 清理不确定`，再追加提议 ID 查看两份账本摘要，按返回的五分钟凭据明确确认 `abandoned` 或 `verified`。这是人工处理决定，保留机器回读结果、operations 账本和已占额度/判重，不重新执行。该功能需要插件和伴随服务同时更新；账本不可读时拒绝清理。`bili_operation` 为控制器只读工具，不应向模型开放。

审查后已按社区维护的 B站 Web API 文档校正点赞/弹幕、buvid3 和 WBI 参数，真实端点可用性仍待小号 smoke。`df_bili_status` 同时显示 `buvid3_present`；缺失时点赞/投币预览会尝试 SPI 获取，仍缺则零 POST。弹幕正向回执单独记 `accepted`，不等于 `verified` 或公开可见；匿名评论查询失败/未找到均为 `visibility=unknown`。投币的附带点赞单独显示 `like_ok`，`null` 表示尚未核实。

`stop` 关闭后台浏览；主人主动请求截图仍由截图开关控制。完全停用图片分享需要另关 `screenshot_enabled`。参数修改示例：

```bash
python3 /opt/dafeiyu/tools/bili_activity/ops.py configure --check-minutes 120 --check-jitter-minutes 60 --max-videos 3 --max-minutes 10
```

周期检查不是固定间隔：实际间隔在 `check_minutes ± check_jitter_minutes` 之间随机（上例为 60–180 分钟），每次运行结束后重新抽签；开启周期后的第一次运行也会先等一个随机间隔，不会立刻触发。`--check-jitter-minutes 0` 可退回固定间隔。

Windows 的一键启停与日志：

```powershell
cd D:\AI\BiliActivity\src
.\start_bili_service.ps1 -Server <实际云主机> -User <现有SSH用户> -Key <现有私钥路径> -SkipInstall
.\status_bili_service.ps1
.\status_bili_service.ps1 -Logs
.\stop_bili_service.ps1
```

只停止本次服务及 8011 隧道，不关闭模拟器或其他任务。云端代理单独使用 `cloud_service.sh stop`。没有注册系统开机自启，重启电脑后需要再次启动。

## 数据与故障恢复

## 本地开发复验

```bash
cd /workspace/dafeiyu-astrbot
.venv/bin/python -m pip install --no-cache-dir -r deploy/bili_activity/requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -m unittest discover -s tests -p 'test_bili_*.py' -v
.venv/bin/python tests/test_phone_video.py
.venv/bin/python tests/test_face_rules.py
.venv/bin/python tests/test_video_processing.py
bash -n deploy/bili_activity/deploy.sh deploy/bili_activity/cloud_service.sh
```
