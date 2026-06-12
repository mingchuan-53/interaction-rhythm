# 交互节律 Agent 交接说明

更新时间：2026-06-12

## 一句话状态

交互节律 Windows 桌面端已经进入可公开测试的稳定维护阶段，当前正式版本是 `v1.7.1`。后续不做高频冲刺，按半月或一月节奏处理真实使用里的稳定性、更新链路、数据保护和节律助手解释质量。

## 正式位置

| 类型 | 位置 |
| --- | --- |
| 产品仓库 | `D:\10_Projects\10_Products\interaction-rhythm` |
| GitHub | `https://github.com/mingchuan-53/interaction-rhythm` |
| Poiesis 项目档案 | `D:\10_Projects\00_Core\Poiesis\_40-阿莱是台珍妮机\05-应用工具\01-交互节律` |
| 维护入口 | `D:\10_Projects\00_Core\Poiesis\_40-阿莱是台珍妮机\05-应用工具\01-交互节律\交互节律桌面\版本维护\README.md` |
| 迭代日历 | `docs/planning/iteration-calendar.md` |
| 更新清单 | `https://github.com/mingchuan-53/interaction-rhythm/releases/latest/download/update.json` |

旧的 `C:\Users\mingchuan\Documents\Codex\2026-06-08\type-tracker` 只保留为历史入口提示，不再作为开发主线。

## 产品定位

交互节律不是生产力评分器。它记录键盘响应、鼠标响应、前台应用停留和单应用交互强度，帮助用户回忆电脑前的使用节律：

- 什么时候活跃。
- 哪些应用占用时间。
- 哪些应用交互密度高。
- 哪些应用停留很多但操作少。
- 最近一次和上一次相比有什么变化。

节律助手只选择少量值得看的线索，不输出完整分析报告。

## 当前版本能力

- 键盘 / 鼠标响应次数统计。
- 最近 6 天小时热力图，可切换键盘和鼠标响应。
- 应用时长排行，两列竖向展示。
- 单应用分析入口。
- 本地规则版节律助手。
- JSON / CSV 数据导出。
- 托盘后台运行。
- 启动后轻量检查更新。
- 便携包和 Inno Setup 安装器打包。

## 近期路线

| 日期 | 版本 | 判断重点 |
| --- | --- | --- |
| 2026-06-26 | `v1.7.2` | 诊断日志、数据备份、更新失败回滚、打包前检查。 |
| 2026-07-25 | `v1.8` | 节律助手偏好、单应用强度标签、专注 / 切换 / 高摩擦线索。 |
| 2026-08-29 | `v1.9` | 启动速度、后台退出、多实例互斥、托盘图标、应用图标缓存。 |
| 2026-09-26 | `v2.0` | 周报、应用分类、Android 对齐、数据库迁移和正式发布准备。 |

每次检查先判断 `no-op / patch / release / blocked`，不要为了排期强行发布。

## Super Productivity 同步状态

Super Productivity 里已有 4 条交互节律后续任务：

- `[交互节律] 1.7.2 维护版：诊断、备份和更新失败日志`
- `[交互节律] 1.8 解释能力版：节律助手偏好和单应用强度标签`
- `[交互节律] 1.9 稳定体验版：启动、后台、多实例和图标缓存`
- `[交互节律] 2.0 方向评审：周报、分类、Android 对齐和数据库迁移`

Super Productivity 本地 REST API 当前没有暴露项目创建接口，所以不要直接改它的数据库。用任务标题前缀和 `dueDay` 管理日历即可。

## 接手流程

1. 读取仓库根目录 `AGENTS.md`。
2. 读取本文件、`README.md`、`CHANGELOG.md`、`docs/planning/iteration-calendar.md`。
3. 如果涉及 Poiesis 写回，先读取 `D:\10_Projects\00_Core\Poiesis\AGENTS.md` 和 `_00-OPC\README.md`。
4. 如果涉及版本、发布或维护日历，读取 Poiesis 版本维护文件夹。
5. 明确本轮结论：`no-op / patch / release / blocked`。
6. 修改代码。
7. 验证打包版和更新链路。
8. 写回 `CHANGELOG.md`、版本文档和 Poiesis 维护记录。

## 发布前检查

- `config.py` 里的 `APP_VERSION` 已更新。
- `CHANGELOG.md` 写入版本变化。
- `dist/releases/交互节律.zip` 是中文分享包。
- `dist/releases/interaction-rhythm.zip` 是 GitHub Release 包。
- `dist/releases/update.json` 指向正确版本和下载地址。
- GitHub Release 上传了 `interaction-rhythm.zip` 和 `update.json`。
- 旧版本应用内检查更新能发现新版。
- 用户数据目录不会被打包覆盖。
- 分享包不包含数据库、日志、截图、缓存。

## 历史坑位

- 无边框拖动曾反复失效。改窗口拖动逻辑前先读 `window.py` 和 `static/index.html`。
- 启动和托盘退出曾有卡顿。改后台线程、数据库关闭、托盘退出前要实际运行测试。
- 更新后曾出现数据像是丢失的问题。更新流程必须保护用户数据，并在退出前执行数据库落盘。
- 检查更新曾阻塞设置页。更新状态应缓存，网络检查应后台执行。
- 应用内图标、桌面图标、托盘图标曾不一致。发版前要检查三处。
- Super Productivity API 调试时不要使用未知删除接口；写入前先备份。

## 需要明川确认的事项

- 对外正式发布承诺。
- 自动上传、账号、云同步、反馈回流。
- GitHub Release 正式发布。
- 改名、定位变化、隐私边界变化。
- 删除历史档案或旧版本包。

