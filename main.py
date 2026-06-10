"""交互节律 — 主入口（原生桌面客户端）"""
import sys
import os
import signal
import threading
from pathlib import Path

from config import PORT, APP_NAME, DB_RETENTION_DAYS, HOURLY_RETENTION_DAYS
from db import DB
from monitor import Tracker
from stats import StatsServer


def resource_path(relative: str) -> Path:
    """获取资源路径，兼容 PyInstaller 打包模式"""
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent
    return base / relative


def data_path() -> Path:
    """获取数据目录（DB 等可写文件），打包模式下放在 exe 同级"""
    if getattr(sys, 'frozen', False):
        p = Path(sys.executable).parent / "data"
    else:
        p = Path(__file__).parent / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


DB_PATH = data_path() / "tracker.db"


def set_windows_app_id():
    """让 Windows 任务栏把进程归到交互节律，而不是 python.exe。"""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Mingchuan.InteractionRhythm")
    except Exception:
        pass


def main():
    set_windows_app_id()
    print(f"[{APP_NAME}] 启动中...")

    db = DB(DB_PATH)

    tracker = Tracker(db)
    server = None

    def shutdown(*_):
        print(f"\n[{APP_NAME}] 关闭中...")
        tracker.stop()
        if server:
            server.stop()
        print(f"[{APP_NAME}] 已退出")
        sys.exit(0)

    def exit_for_update():
        print(f"\n[{APP_NAME}] 准备安装更新...")
        try:
            tracker.stop()
        except Exception:
            pass
        try:
            if server:
                server.stop()
        except Exception:
            pass
        os._exit(0)

    server = StatsServer(db, PORT, shutdown_callback=exit_for_update)

    server.start()

    def start_tracker_async():
        import time
        time.sleep(0.2)
        try:
            tracker.start()
        except Exception as e:
            print(f"[{APP_NAME}] 记录器启动失败: {e}")

    threading.Thread(target=start_tracker_async, daemon=True).start()

    def cleanup_async():
        import time
        time.sleep(3)
        try:
            db.cleanup(DB_RETENTION_DAYS, HOURLY_RETENTION_DAYS)
        except Exception as e:
            print(f"[{APP_NAME}] 历史数据清理跳过: {e}")

    threading.Thread(target=cleanup_async, daemon=True).start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"[{APP_NAME}] 已启动  http://localhost:{PORT}")

    # 启动系统托盘（后台加载，避免拖慢窗口显示）
    def start_tray_async():
        try:
            import time
            time.sleep(1.2)
            tray_error = data_path() / "tray-error.log"
            if tray_error.exists():
                tray_error.unlink()
            from tray import create_tray
            _, tray_start = create_tray(tracker, PORT)
            tray_start()
        except Exception as e:
            print(f"[{APP_NAME}] 托盘启动失败: {e}")
            try:
                import traceback
                (data_path() / "tray-error.log").write_text(traceback.format_exc(), encoding="utf-8")
            except Exception:
                pass

    tray_thread = threading.Thread(target=start_tray_async, daemon=True)
    tray_thread.start()
    print(f"[{APP_NAME}] 系统托盘加载中")

    # 生成应用图标（用于任务栏、窗口和原生标题栏）
    icon_path = data_path() / f"{APP_NAME}.ico"
    title_icon_path = data_path() / "interaction-rhythm-title.png"
    if not icon_path.exists() or icon_path.stat().st_size < 1024:
        try:
            from tray import make_ico
            make_ico(str(icon_path))
        except Exception as e:
            print(f"[{APP_NAME}] 图标生成失败: {e}")
            icon_path = None
    if not title_icon_path.exists():
        try:
            from tray import make_icon
            make_icon(96).save(title_icon_path, "PNG")
        except Exception as e:
            print(f"[{APP_NAME}] 标题栏图标生成失败: {e}")
            title_icon_path = None

    # 主线程：原生桌面窗口（阻塞直到窗口关闭）
    try:
        from window import create_window
        _, window_start = create_window(
            PORT,
            icon_path=str(icon_path) if icon_path else None,
            title_icon_path=str(title_icon_path) if title_icon_path else None,
        )
        window_start()  # 阻塞主线程
    except Exception as e:
        print(f"[{APP_NAME}] 窗口启动失败: {e}")

    # 窗口关闭后清理
    shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        if getattr(sys, "frozen", False):
            log_path = Path(sys.executable).parent / "startup-error.log"
        else:
            log_path = Path(__file__).parent / "startup-error.log"
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        raise
