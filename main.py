"""扣舷 — 主入口（原生桌面客户端）"""
import sys
import os
import signal
import threading
from pathlib import Path
from urllib.request import urlopen

from config import PORT, APP_NAME, APP_MUTEX_NAME, DB_RETENTION_DAYS, HOURLY_RETENTION_DAYS
from diagnostics import log_event, log_exception
from db import DB
from stats import StatsServer

_JOB_HANDLE = None
_INSTANCE_MUTEX_HANDLE = None


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


def legacy_database_candidates() -> list[Path]:
    """Find old tracker.db files from installed and portable-era layouts."""
    candidates = []
    app_root = data_path().parent
    candidates.extend([
        app_root / "data" / "tracker.db",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "InteractionRhythm" / "data" / "tracker.db",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "TypeTracker" / "data" / "tracker.db",
        Path(os.environ.get("APPDATA", "")) / "InteractionRhythm" / "tracker.db",
        Path(os.environ.get("APPDATA", "")) / "TypeTracker" / "tracker.db",
    ])

    source_root = Path(__file__).parent
    for base in (
        source_root / "data",
        source_root / "dist" / "current" / "InteractionRhythm" / "data",
        source_root / "dist" / "build" / "InteractionRhythm" / "data",
    ):
        candidates.append(base / "tracker.db")
    for parent in (
        source_root / "dist" / "releases",
        source_root / "dist" / "archive",
    ):
        if parent.exists():
            candidates.extend(parent.glob("**/data/tracker.db"))

    seen = set()
    result = []
    current = str(DB_PATH.resolve())
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key == current or key in seen:
            continue
        seen.add(key)
        if resolved.exists():
            result.append(resolved)
    return result


def local_server_healthy(timeout: float = 0.12) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{PORT}/api/today", timeout=timeout) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def set_windows_app_id():
    """让 Windows 任务栏把进程归到扣舷，而不是 python.exe。"""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Mingchuan.InteractionRhythm")
    except Exception:
        pass


def acquire_single_instance_lock() -> bool:
    """Use a named Windows mutex so newer builds cannot run side by side."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.GetLastError.restype = wintypes.DWORD
        handle = kernel32.CreateMutexW(None, False, APP_MUTEX_NAME)
        if not handle:
            return True

        global _INSTANCE_MUTEX_HANDLE
        _INSTANCE_MUTEX_HANDLE = handle
        return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return True


def set_kill_children_on_exit():
    """让 WebView2 子进程随主进程一起退出，避免后台残留一瞬间。"""
    if os.name != "nt":
        return
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_void_p),
                ("MaximumWorkingSetSize", ctypes.c_void_p),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_void_p),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_void_p),
                ("JobMemoryLimit", ctypes.c_void_p),
                ("PeakProcessMemoryUsed", ctypes.c_void_p),
                ("PeakJobMemoryUsed", ctypes.c_void_p),
            ]

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return
        if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            return
        kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess())

        global _JOB_HANDLE
        _JOB_HANDLE = job
    except Exception:
        pass


def restore_existing_window(retries: int = 0, delay: float = 0.2, require_server: bool = True) -> bool:
    if os.name != "nt":
        return False
    import time
    try:
        from window import _find_hwnd, _restore_main_window
        for attempt in range(max(0, retries) + 1):
            hwnd = _find_hwnd(APP_NAME)
            server_ok = local_server_healthy() if hwnd and require_server else True
            if hwnd and server_ok:
                _restore_main_window(hwnd)
                return True
            if attempt < retries:
                time.sleep(delay)
    except Exception:
        pass
    return False


def main():
    set_windows_app_id()
    background_start = any(arg in ("--background", "--hidden", "--tray") for arg in sys.argv[1:])
    log_event("startup_begin", {"background": background_start, "argv": sys.argv[1:]})
    if not acquire_single_instance_lock():
        log_event("startup_existing_instance", {"background": background_start})
        if not background_start:
            restore_existing_window(retries=10, delay=0.1, require_server=False)
        return
    if not background_start and restore_existing_window(retries=0, delay=0.05):
        log_event("startup_existing_window_restored")
        return
    print(f"[{APP_NAME}] 启动中...")

    db = DB(DB_PATH)

    tracker = None
    tracker_lock = threading.Lock()
    server = None

    class TrackerFacade:
        """托盘使用的轻量代理，避免托盘启动时顺手拉起全局监听器。"""

        @property
        def stats(self):
            active = tracker
            if active:
                return active.stats
            try:
                return db.today_stats()
            except Exception:
                return {"keystrokes": 0, "mouse_events": 0, "total_seconds": 0}

        def flush(self):
            active = tracker
            if active:
                active.flush()

    def ensure_tracker_started():
        nonlocal tracker
        if tracker:
            return tracker
        with tracker_lock:
            if tracker:
                return tracker
            from monitor import Tracker
            next_tracker = Tracker(db)
            next_tracker.start()
            tracker = next_tracker
            return tracker

    def shutdown(*_):
        print(f"\n[{APP_NAME}] 关闭中...")
        log_event("shutdown_begin")
        if tracker:
            tracker.stop()
        if server:
            server.stop()
        try:
            db.checkpoint()
            db.close()
        except Exception as e:
            log_exception("shutdown_db_close_failed", e)
        print(f"[{APP_NAME}] 已退出")
        log_event("shutdown_finished")
        sys.exit(0)

    def exit_for_update():
        print(f"\n[{APP_NAME}] 准备安装更新...")
        log_event("update_shutdown_begin")
        try:
            if tracker:
                tracker.stop()
        except Exception as e:
            log_exception("update_shutdown_tracker_failed", e)
            pass
        try:
            if server:
                server.stop()
        except Exception as e:
            log_exception("update_shutdown_server_failed", e)
            pass
        try:
            db.checkpoint()
        except Exception as e:
            log_exception("update_shutdown_checkpoint_failed", e)
            pass
        log_event("update_shutdown_exit")
        os._exit(0)

    try:
        server = StatsServer(db, PORT, shutdown_callback=exit_for_update)
    except OSError:
        if background_start or restore_existing_window(retries=10, delay=0.2):
            return
        raise

    server.start()

    def start_tracker_async():
        import time
        # 全局键鼠监听和前台窗口探测会让 WebView 启动期抖一下。
        # 可见启动时等窗口、标题栏、托盘都稳定后再拉起记录器。
        time.sleep(0.8 if background_start else 6.0)
        try:
            ensure_tracker_started()
        except Exception as e:
            print(f"[{APP_NAME}] 记录器启动失败: {e}")
            log_exception("tracker_start_failed", e)

    threading.Thread(target=start_tracker_async, daemon=True).start()

    def import_legacy_async():
        import time
        time.sleep(1.2 if background_start else 2.5)
        try:
            candidates = legacy_database_candidates()
            results = db.import_legacy_databases(candidates)
            imported = [
                item for item in results
                if not item.get("skipped") and not item.get("error")
                and sum(int(item.get(key) or 0) for key in (
                    "keystrokes", "mouse_events", "app_usage", "app_paths", "app_interactions", "insight_history"
                )) > 0
            ]
            if imported:
                log_event("legacy_data_imported", {"sources": len(imported), "results": imported})
                db.checkpoint()
        except Exception as e:
            print(f"[{APP_NAME}] 旧数据继承跳过: {e}")
            log_exception("legacy_import_skipped", e)

    threading.Thread(target=import_legacy_async, daemon=True).start()

    def cleanup_async():
        import time
        time.sleep(12)
        try:
            db.cleanup(DB_RETENTION_DAYS, HOURLY_RETENTION_DAYS)
            db.checkpoint()
        except Exception as e:
            print(f"[{APP_NAME}] 历史数据清理跳过: {e}")
            log_exception("cleanup_skipped", e)

    threading.Thread(target=cleanup_async, daemon=True).start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"[{APP_NAME}] 已启动  http://127.0.0.1:{PORT}")
    log_event("server_started", {"port": PORT})

    # 启动系统托盘（后台加载，避免拖慢窗口显示）
    def start_tray_async():
        try:
            import time
            time.sleep(0.4 if background_start else 3.0)
            tray_error = data_path() / "tray-error.log"
            if tray_error.exists():
                tray_error.unlink()
            from tray import create_tray
            def tray_shutdown():
                try:
                    if server:
                        server.stop()
                except Exception:
                    pass

            _, tray_start = create_tray(TrackerFacade(), PORT, shutdown_callback=tray_shutdown)
            tray_start()
        except Exception as e:
            print(f"[{APP_NAME}] 托盘启动失败: {e}")
            log_exception("tray_start_failed", e)
            try:
                import traceback
                (data_path() / "tray-error.log").write_text(traceback.format_exc(), encoding="utf-8")
            except Exception:
                pass

    tray_thread = threading.Thread(target=start_tray_async, daemon=True)
    tray_thread.start()
    print(f"[{APP_NAME}] 系统托盘加载中")

    # 生成应用图标（用于任务栏、窗口和原生标题栏）
    frozen = getattr(sys, "frozen", False)
    title_icon_path = data_path() / "interaction-rhythm-title.png"
    if frozen:
        icon_candidates = [
            Path(sys.executable).with_suffix(".ico"),
            Path(sys.executable).parent / "InteractionRhythm.ico",
            data_path() / f"{APP_NAME}.ico",
        ]
        icon_path = next((path for path in icon_candidates if path.exists() and path.stat().st_size >= 1024), None)
        if not title_icon_path.exists():
            title_icon_path = None
    else:
        bundled_icon = resource_path("app.ico")
        icon_path = bundled_icon if bundled_icon.exists() else data_path() / f"{APP_NAME}.ico"
        if not icon_path.exists() or icon_path.stat().st_size < 1024:
            try:
                from tray import make_ico
                make_ico(str(icon_path))
            except Exception as e:
                print(f"[{APP_NAME}] 图标生成失败: {e}")
                log_exception("icon_generate_failed", e)
                icon_path = None
        if not title_icon_path.exists():
            try:
                from tray import make_icon
                make_icon(96).save(title_icon_path, "PNG")
            except Exception as e:
                print(f"[{APP_NAME}] 标题栏图标生成失败: {e}")
                log_exception("title_icon_generate_failed", e)
                title_icon_path = None

    # 主线程：原生桌面窗口（阻塞直到窗口关闭）
    try:
        from window import create_window
        _, window_start = create_window(
            PORT,
            icon_path=str(icon_path) if icon_path else None,
            title_icon_path=str(title_icon_path) if title_icon_path else None,
            start_hidden=background_start,
        )
        window_start()  # 阻塞主线程
    except Exception as e:
        print(f"[{APP_NAME}] 窗口启动失败: {e}")
        log_exception("window_start_failed", e)

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
        log_exception("startup_crashed", sys.exc_info()[1])
        raise
