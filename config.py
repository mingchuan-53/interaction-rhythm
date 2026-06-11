"""交互节律全局配置"""
import os

APP_NAME = "交互节律"
APP_ICON_TEXT = "节"
APP_VERSION = "1.5"
APP_MUTEX_NAME = os.getenv("INTERACTION_RHYTHM_MUTEX_NAME", r"Local\Mingchuan.InteractionRhythm.SingleInstance")

PORT = 18923
POLL_INTERVAL = 0.5
BATCH_INTERVAL = 1
DB_RETENTION_DAYS = 30
HEATMAP_DAYS = 6
HOURLY_RETENTION_DAYS = 180

# Frameless mode uses the custom titlebar drag bridge. Flip this to False
# if a Windows/WebView2 update ever regresses dragging behavior.
BORDERLESS_WINDOW = True
BORDERLESS_DRAG_SELECTOR = ".window-drag"

# 远程更新清单地址。发布时把 dist/releases/update.json 上传到稳定地址，
# 再把这里或环境变量 INTERACTION_RHYTHM_UPDATE_URL 指向它。
UPDATE_MANIFEST_URL = os.getenv("INTERACTION_RHYTHM_UPDATE_URL", "")
UPDATE_CHANNEL = os.getenv("INTERACTION_RHYTHM_UPDATE_CHANNEL", "stable")
UPDATE_TIMEOUT = 20
