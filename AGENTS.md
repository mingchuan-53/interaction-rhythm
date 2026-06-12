# 交互节律 Agent 接手入口

本仓库是交互节律 Windows 桌面端的正式代码主线。新对话继续迭代时，先读本文件，再按顺序读取下面的文件，不要从旧的 `type-tracker` 工作区继续开发。

## 当前状态

- 当前版本：`v1.7.1`
- 产品名称：交互节律
- 正式仓库：`D:\10_Projects\10_Products\interaction-rhythm`
- GitHub：`https://github.com/mingchuan-53/interaction-rhythm`
- 更新清单：`https://github.com/mingchuan-53/interaction-rhythm/releases/latest/download/update.json`
- Poiesis 项目档案：`D:\10_Projects\00_Core\Poiesis\_40-阿莱是台珍妮机\05-应用工具\01-交互节律`
- 当前仓库只包含 Windows 桌面端。Android 端仍是单独实验，不要混入本仓库。

## 必读顺序

1. `README.md`
2. `CHANGELOG.md`
3. `docs/handoff/agent-handoff.md`
4. `docs/planning/iteration-calendar.md`
5. `D:\10_Projects\00_Core\Poiesis\_40-阿莱是台珍妮机\05-应用工具\01-交互节律\交互节律桌面\版本维护\README.md`

如果任务涉及发布、更新、版本排期或对外测试，还要读取：

1. `D:\10_Projects\00_Core\Poiesis\_40-阿莱是台珍妮机\05-应用工具\01-交互节律\交互节律桌面\版本维护\版本路线.md`
2. `D:\10_Projects\00_Core\Poiesis\_40-阿莱是台珍妮机\05-应用工具\01-交互节律\交互节律桌面\版本维护\维护日历.md`

## 下一轮默认动作

新 Agent 接到“继续”时，先给出当前判断：

- no-op：没有真实问题，不发版。
- patch：修复小问题，发布维护版。
- release：有明确功能或稳定性提升，发布正式版本。
- blocked：需要明川确认、外部反馈或环境条件。

然后再进入代码修改。不要直接扩大功能范围。

## 近期排期

- `2026-06-26`：`v1.7.2` 维护版，重点是诊断日志、数据备份、更新失败回滚、打包前检查。
- `2026-07-25`：`v1.8` 解释能力版，重点是节律助手偏好、单应用强度标签、专注 / 切换 / 高摩擦线索。
- `2026-08-29`：`v1.9` 稳定体验版，重点是启动速度、后台退出、多实例互斥、托盘图标和应用图标缓存。
- `2026-09-26`：`v2.0` 方向评审，判断周报、应用分类、Android 对齐、数据库迁移和正式发布准备。

这些排期已经同步到 Super Productivity，标题以 `[交互节律]` 开头，通过 `dueDay` 进入日历。

## 关键边界

- 不记录键盘内容、文本内容、鼠标坐标、截图或浏览器页面内容。
- 数据默认保存在本地 SQLite，不做后台上传。
- 节律助手当前是本地规则分析，不调用外部 AI 模型。
- 关闭按钮默认隐藏到托盘；完全退出在托盘菜单。
- 旧版本应用内检查更新必须能发现新版。
- 发布前必须确认用户数据不会被新版覆盖。
- `dist/`、`data/`、数据库、日志、截图、缓存和构建产物不要提交。

## 常用验证

```powershell
python main.py
.\build.ps1
.\build-installer.ps1
```

发布或更新相关修改必须额外验证：

- 打包版能启动。
- 热力图、应用排行、节律助手、设置、导出和检查更新正常。
- 托盘打开、刷新数据、退出后台正常。
- 旧版本能通过应用内检查更新发现最新版本。

