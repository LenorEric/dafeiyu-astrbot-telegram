> Telegram 专用版本。本文不构成真实账号联调记录；配置与验收以部署指南和验证报告为准。

# 她的小小房间 v0.2 · 大肥鱼与记忆分区

## 实现

## 数据接入

```powershell
python -B -m deploy.memory_observatory.server --port 8767 --livingmemory-ssh --life-ssh
```

访问 `/room` 和 `/`。已运行的旧进程需要先正常停止，再以新版本启动；不会替换或终止其他进程。
现有桌面入口默认带 `--life-ssh`，双击即同时连接记忆与活动账本；已有真实服务在运行时直接复用。
若旧进程没有活动源，先正常停止一次再双击。

真实 LivingMemory 保持固定 SSH 读取器、只读 SQLite SELECT 和本机内存快照；未变更访问计数、强化、真实遗忘或 Telegram 行为。
活动账本有独立的「同步近况」按钮；缓存超过三分钟会显示旧快照，不冒充实时状态。它不跟随记忆的 60 秒刷新。
启动时不指定真实来源则展示明确标记的虚构样例；真实来源失败不会变成演示。

| 验证 | 结果 |
| --- | --- |
| Windows：`<本机Python路径> -B -m unittest discover -s tests -p "test_memory_*.py" -v` | 81 项，11.9 秒，OK，0 skip |
| WSL：`wsl.exe -e bash -lc 'cd /mnt/d/GitHub/dafeiyu-astrbot && python3 -B -m unittest discover -s tests -p "test_memory_*.py" -v'` | 81 项，11.5 秒，OK，1 skip（Windows 命名互斥锁） |
| `node tests/memory_observatory_browser.mjs --spawn-demo` | 18 项 PASS；只用虚构数据，测试进程结束即关闭 |
| `node tests/memory_observatory_browser.mjs --live-readonly --live-activity` | 7 项 PASS；实际连接 LivingMemory 和活动账本，不保存正文或截图 |
| JS 语法检查、`git diff --check` | 通过 |

新增/扩展检查覆盖：6 个素材的明确静态白名单、路径越界拒绝、类型布局、选中关联、遗忘过程中画布连续变化、镜头中间位置、快速导航、动作换帧、昼夜、移动端、减少动画，以及 60 秒回调的状态保持/隐藏暂停/关闭暂停/慢同步期间切换作用域。
自动同步的边界由模拟来源与调用原计时器回调验证，没有把模拟结果说成真实时间流逝验收。

[房间总览](assets/room-v02-overview.png) · [书桌特写](assets/room-v02-desk.png) · [记忆分区](assets/room-v02-atlas.png)

 ·

- 活动快照的“超过三分钟即旧”改按本机单调时钟的加载时长计算（服务端 `age_seconds` + 页面接收后的本地时长），不再拿远端 `as_of` 对浏览器时钟。
- 六组精灵图由 1774×887 的 443.5px 网格重排为 1786×894（444px 整数格 + 2px 透明隔断），Canvas 源矩形全为整数。
- `graph.js` 的数字三元改为显式 `cond ? a : b`，Node 24 可直接解析。
- 被拒绝的 POST 先排空请求体，消除 Windows 下偶发 `ConnectionAbortedError` 的测试 flake。
- 本目录 README 顶部介绍对齐 v0.2；新增远端时钟漂移与图集尺寸的回归测试。

## 素材与边界

仍未验证：Safari/Firefox、长时运行和低端设备的帧率、逐格美术一致性之外的连续骨骼运动、实际生活策略或 Telegram 行为。
真实数据只读接通不等于拟人记忆策略已经上线。原有 B站、审批、Executor、transport、预算、人格和手机脚本均未修改。
回滚只需停止本机服务并恢复页面/素材文件；无需回滚真实库或云端配置。没有 push 或部署。
