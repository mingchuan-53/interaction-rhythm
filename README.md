# 交互节律

[![Windows](https://img.shields.io/badge/Windows-10%2B-15803d)](#)
[![Python](https://img.shields.io/badge/Python-3.10%2B-2563eb)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-111827.svg)](LICENSE)

交互节律是一个本地优先的 Windows 桌面小工具，用来观察键盘响应、鼠标响应和前台应用使用节律。

它不尝试判断你是不是“高效”，也不记录输入内容。它只把一天里的操作强度、应用停留和时间分布整理成更容易回忆的线索：什么时候最活跃，主要和哪些应用发生交互，哪些时间段更像输入、浏览、整理或停留。

> 当前仓库只包含 Windows 桌面端。Android 版仍在单独实验中，暂不随本次开源。

## 功能

| 模块 | 作用 |
| --- | --- |
| 键盘 / 鼠标响应 | 只记录次数，不记录按键内容、鼠标位置或文本内容。 |
| 小时热力图 | 以小时为格子查看最近 6 天的响应节律，可切换键盘、鼠标显示。 |
| 应用时长排行 | 查看前台应用的停留时长，并支持点开单个应用分析。 |
| 单应用强度 | 对照应用时长和键鼠响应，发现“停留很多但操作少”或“时间不长但交互很密”的应用。 |
| 节律助手 | 本地规则分析，先给结论，再挑少量重点发现和建议。 |
| 托盘后台 | 关闭窗口默认隐藏到托盘，可从托盘打开、刷新或退出后台。 |
| 数据导出 | 支持 JSON 和 CSV，方便后续归档或自行分析。 |
| 检查更新 | 启动后可轻量检查更新，有新版时提醒，安装必须由用户确认。 |

## 隐私边界

交互节律默认只在本机运行，数据保存在本地 SQLite 数据库中。

它会记录：

- 每批键盘响应次数
- 每批鼠标响应次数
- 前台应用名称、窗口标题、应用路径
- 应用前台停留的开始和结束时间
- 键盘 / 鼠标响应对应的前台应用

它不会记录：

- 具体按下了哪个键
- 输入的文字内容
- 鼠标坐标或屏幕截图
- 浏览器页面内容
- 后台上传数据

## 节律助手如何工作

节律助手当前使用本地规则分析，不调用外部 AI 模型。它会从这些线索中选少量最值得看的内容：

- 全局键盘 / 鼠标响应比例
- 每小时响应高峰
- 应用时长占比
- 单个应用的响应占比
- 单个应用的响应密度
- 应用回返次数
- 最近两次分析之间的变化

因此它更像“帮你回忆电脑前发生了什么”的观察助手，而不是生产力评分器。

## 本地运行

环境要求：

- Windows 10 或更高版本
- Python 3.10 或更高版本

安装依赖：

```powershell
pip install -r requirements.txt
```

启动：

```powershell
python main.py
```

启动后会打开一个无边框桌面窗口，并在后台托盘保留入口。

## 打包

项目使用 PyInstaller 打包：

```powershell
.\build.ps1
```

构建完成后主要产物在：

- `dist/current/`：当前可运行版本
- `dist/releases/交互节律.zip`：可分发压缩包
- `dist/releases/interaction-rhythm.zip`：GitHub Release 使用的稳定英文包名
- `dist/releases/update.json`：更新清单

如果需要生成 Windows 安装器，先安装 Inno Setup 6，然后运行：

```powershell
.\build-installer.ps1
```

安装器输出在：

- `installer/output/interaction-rhythm-setup-v版本号.exe`

`dist/`、`data/`、数据库文件和调试截图不会进入 Git 仓库。

## 目录

```text
.
├─ main.py              # 应用入口、单实例和启动流程
├─ monitor.py           # 键盘、鼠标、前台窗口记录
├─ db.py                # SQLite 数据、统计、节律助手逻辑
├─ stats.py             # 本地 HTTP API 与导出接口
├─ window.py            # 桌面窗口和拖动桥接
├─ tray.py              # 托盘菜单与后台行为
├─ update_manager.py    # 更新检查和安装流程
├─ settings.py          # 用户设置
├─ static/index.html    # 主界面
├─ build.ps1            # Windows 便携包打包脚本
├─ build-installer.ps1  # Windows 安装器构建脚本
└─ installer/           # Inno Setup 安装器脚本
```

## 版本日志

完整开发脉络见 [CHANGELOG.md](CHANGELOG.md)。

后续版本采用半月或一月一次的低频维护节奏，排期见 [docs/planning/iteration-calendar.md](docs/planning/iteration-calendar.md)。

## 许可

本项目使用 [MIT License](LICENSE)。
