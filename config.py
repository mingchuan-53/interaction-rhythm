"""扣舷全局配置"""
import os

APP_NAME = "扣舷"
APP_ICON_TEXT = "扣"
APP_VERSION = "1.9.8"
APP_MUTEX_NAME = os.getenv("INTERACTION_RHYTHM_MUTEX_NAME", r"Local\Mingchuan.InteractionRhythm.SingleInstance")

PORT = 18923
POLL_INTERVAL = 0.5
BATCH_INTERVAL = 1
DB_RETENTION_DAYS = int(os.getenv("INTERACTION_RHYTHM_RETENTION_DAYS", "3650"))
HEATMAP_DAYS = 6
HOURLY_RETENTION_DAYS = 180

# Frameless mode uses the custom titlebar drag bridge. Flip this to False
# if a Windows/WebView2 update ever regresses dragging behavior.
BORDERLESS_WINDOW = True
BORDERLESS_DRAG_SELECTOR = ".window-drag"

# 远程更新清单地址。打包版也会写入 update-url.txt；这里作为源码运行和兜底地址。
UPDATE_MANIFEST_URL = os.getenv(
    "INTERACTION_RHYTHM_UPDATE_URL",
    "https://github.com/mingchuan-53/interaction-rhythm/releases/latest/download/update.json",
)
UPDATE_CHANNEL = os.getenv("INTERACTION_RHYTHM_UPDATE_CHANNEL", "stable")
UPDATE_TIMEOUT = 20
