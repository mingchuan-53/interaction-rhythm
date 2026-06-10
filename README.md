# 交互节律

键盘、鼠标响应和应用使用节律观察器。

## 功能

- 键盘响应计数：全局键盘监听，统计每小时/每天键盘响应。
- 鼠标响应计数：记录点击和滚轮响应，不记录鼠标移动。
- 应用使用时间：追踪每个应用的真实前台使用时长。
- Web 仪表盘：键鼠响应、贡献图式小时热力图、两列应用时长排行。
- 真实应用图标：本地提取正在运行应用的 exe 图标并缓存为 PNG。
- 系统托盘：关闭按钮默认隐藏到托盘，只能从托盘菜单完全退出。
- 应用内更新：可检查远程更新清单，下载朋友测试包后关闭自身、替换并重启。
- 窄窗口一屏呈现：页面宽度贴合热力图，首页直接展示完整核心统计。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动
python main.py
```

或双击 `start.bat` 自动创建虚拟环境并安装依赖。

启动后打开本地仪表盘：

```text
http://localhost:18923
```

## 窗口行为

- 最小化按钮：最小化到任务栏。
- 关闭按钮：隐藏到托盘，后台继续记录。
- 完全退出：只能从托盘菜单选择“退出交互节律”。

## 页面

| 页面 | 地址 | 说明 |
| --- | --- | --- |
| 仪表盘 | `http://localhost:18923/` | 键鼠响应、贡献图式小时热力图、应用时长排行 |

## 项目结构

```text
interaction-rhythm/
├── main.py          # 主入口
├── config.py        # 配置
├── db.py            # SQLite 数据库
├── monitor.py       # 键盘、鼠标、窗口监控
├── stats.py         # HTTP API 服务
├── tray.py          # 系统托盘图标
├── static/
│   └── index.html   # 仪表盘页面
├── data/            # 运行时数据，自动创建
│   ├── tracker.db   # SQLite 数据库
│   └── icons/       # 应用图标 PNG 缓存
├── dist/
│   ├── build/        # 临时打包输出，可删除重建
│   ├── current/      # 本机正在使用的当前版，桌面快捷方式指向这里
│   ├── releases/     # 可回溯的版本包和发朋友的测试包
│   └── archive/      # 旧包和旧快捷方式归档
├── requirements.txt
├── start.bat        # Windows 一键启动
└── README.md
```

## 打包和发布层级

运行 `build.ps1` 后，目录只按四层使用：

| 目录 | 用途 |
| --- | --- |
| `dist/build/InteractionRhythm` | PyInstaller 临时输出，下一次打包会覆盖。 |
| `dist/current/InteractionRhythm` | 本机当前运行版，桌面 `交互节律.lnk` 指向这里。 |
| `dist/releases/InteractionRhythm-v1.1` | 带本机数据的版本快照，用于回退和核对。 |
| `dist/releases/交互节律.zip` | 发给朋友测试的分享包，不包含本机数据库。 |
| `dist/releases/update.json` | 更新清单，发布时和 `交互节律.zip` 一起上传到稳定地址。 |
| `dist/archive/` | 旧包、旧 zip、旧快捷方式。 |

桌面快捷方式使用 `dist/current/InteractionRhythm/InteractionRhythm.ico` 作为图标。若 Windows 桌面仍显示旧图标，通常是 Explorer 图标缓存尚未刷新。

## 技术栈

- Python：pynput、psutil、pystray、pywebview、ctypes、Pillow。
- SQLite：本地数据存储。
- 原生 HTML/CSS/JS：无外部依赖的 Web 仪表盘。

## 配置

编辑 `config.py`：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | 18923 | Web 服务端口 |
| `POLL_INTERVAL` | 0.5 | 窗口轮询间隔，单位秒 |
| `BATCH_INTERVAL` | 1 | 键鼠计数批量写入间隔，单位秒 |
| `DB_RETENTION_DAYS` | 30 | 数据保留天数 |
| `HEATMAP_DAYS` | 6 | 首页热力图历史天数：当前日期前 5 天 + 当前日期，不再显示未来空白列 |
| `HOURLY_RETENTION_DAYS` | 180 | 逐小时汇总保留天数 |
| `UPDATE_MANIFEST_URL` | 空 | 远程 `update.json` 地址；也可用环境变量 `INTERACTION_RHYTHM_UPDATE_URL` 覆盖 |

也可以在运行目录或 `data/` 下创建 `update-url.txt`，只写一行远程 `update.json` 地址。应用会优先读取这个文件。

## 数据隐私

- 所有数据仅存储在本地 SQLite 数据库。
- 默认不上传任何数据。只有配置更新清单地址时，应用才会请求 `update.json` 检查版本。
- 仅记录按键、点击和滚轮数量，不记录具体按键内容，也不记录鼠标移动轨迹。
- 应用图标来自本机可执行文件路径，只缓存在本地 `data/icons/`。
