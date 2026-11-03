> Telegram 专用版本。本文不构成真实账号联调记录；配置与验收以部署指南和验证报告为准。

# B 站自主活动：源码检查与验收记录

## 版本与接入决定

| 检查对象 | 固定版本或提交 | 用途与结论 |
| --- | --- | --- |
| 本项目 | `46638f9822ec8233090959e419176b640d658da7` | 修改前基线；新增代码通过独立分支交付，生产尚未部署 |
| AstrBot | `v4.29.0`，`db4ce0c4b0ae94f443c641f0f78cc9228ddabbeb` | 对照原生 Agent 构建、工具调用和事件接口；真实部署版本仍需读取确认 |
| PhoneMCP | `v0.5.0`，`6c93431b8430b91d92cabc9b08b1b2054b51ed48` | 对照截图返回结构；真实运行版本仍需确认 |
| [Iseenope/bilibili-mcp-server](https://github.com/Iseenope/bilibili-mcp-server) | `20eedd09862aea2c160163007f45221c544651b2`；包版本 `1.2.0` | 已检查源码、锁文件、依赖、构建及测试；服务初始化的版本字段仍为 `1.0.0` |
| 本地伴随服务依赖 | `aiohttp==3.13.3`、`mcp==1.26.0`、`Pillow==12.1.0`、`qrcode==8.2` | 见 `requirements.txt`；Windows 需要 Python 3.12+ 和 ffmpeg |

本次选择独立的 Python 伴随服务，参考候选项目对应的 B 站接口，增加分页、回复、收藏夹管理、写操作账本和回读核实。**候选项目本身没有作为生产 MCP 服务接入。** 新服务通过真正的 MCP Streamable HTTP `/mcp` 提供工具，仅绑定 Windows 回环地址 `127.0.0.1:8011`。云端经 SSH 反向转发和 Docker 网关代理访问；已有 PhoneMCP 的 `8009/Phone` 链路保留。AstrBot 插件直接调用此 MCP，原始 `bili_execute` 等内部工具不得直接暴露给聊天模型。

## 实现与验证范围

新建服务下载总预算为每次准备最多 160 MiB，处理范围最多 300 秒、8 帧，返回媒体包最多 3 MiB。原始媒体与临时 ffmpeg 文件留在 Windows 处理并清理。截图使用独立压缩路径并保持文字可读；真实设备图像清晰度和 2 Mbit/s 链路耗时仍需测量。

## 已执行的本地检查

测试文件及主要证据范围：

候选项目已用锁文件安装依赖并执行构建和原有测试。候选项目结果日志位于开发环境 `/tmp/bilibili-build.log`、`/tmp/bilibili-test.log`。新增实现的最终测试次数、退出状态和回归记录由本次交付的验证报告列出；这里不将先前运行次数当作最终代码的验证结论。

`phone_screenshot.patch` 已针对上述 PhoneMCP 提交执行补丁适用性检查。补丁用于提高源截图 JPEG 质量，并在真实截图失败时返回错误，避免旧实现用黑图伪装成功。尚未应用到用户实际 PhoneMCP。Linux 中没有 PowerShell，Windows 启停脚本尚未执行。

## 实际联调阻塞与待验项目

当前 Codex 环境是 `/workspace` 下的隔离 Linux 开发环境。已检查的本机没有生产 `/opt/dafeiyu` 部署目录、可用生产 SSH 连接或 Windows/ADB 执行入口，不能复用仅存在于用户机器上的会话。仓库记录的 `/opt/dafeiyu`、Docker 网关和历史 Telegram 私聊标识是线索，不能当作当前运行事实或接收人配置。

对 `https://api.bilibili.com/x/web-interface/nav` 的实际只读请求被本环境 HTTPS 代理拒绝，返回 `403 ClientHttpProxyError`。这是开发环境出口阻塞证据，不能据此断言用户 Windows 或云服务器无法访问 B 站。没有绕过代理、关闭 TLS 校验或输出账号凭证。

仍需真实运行入口才能完成：

可靠身份提取目前不解析 `b23.tv` 短链接，也不从标题或评论猜测当前 BV。某些 B 站 App 页面可能不给出可读 BV/分 P，或 UI dump 因画面活动失败，此时返回未知；需要真实界面联调后补齐可验证的来源，不能将启动参数当作已经打开目标视频的证明。

## 完整运行记录的状态

**真实完整运行记录尚不存在。** 尚无“自主触发 → 选视频 → 读取真实内容 → 发出提议 → 用户回答 → 实际执行 → 回读核实 → LivingMemory 保存”的生产证据，也没有对应真实 Telegram 截图消息 ID。不得以测试替身填充此记录。

联调后应从 `activity.sqlite3` 的 `runs`、`events`、`videos`、`proposals`、`deliveries`、`memories` 和 Windows `operations.sqlite3` 中，按运行 ID、提议 ID、视频标识及 Telegram 消息 ID 串联真实记录；将账号凭证与登录参数排除在导出内容之外。生产运行的开关、部署路径与具体命令见同目录 `README.md`。
