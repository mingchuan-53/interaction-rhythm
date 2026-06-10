"""键盘打字计数 & 前台窗口使用时间监控"""
import threading
import time
from datetime import datetime

import psutil
from pynput import keyboard, mouse

try:
    import ctypes
    import ctypes.wintypes as wintypes
    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False

from config import POLL_INTERVAL, BATCH_INTERVAL


def collect_running_app_paths() -> dict[str, str]:
    """扫描当前可见进程，建立进程名到 exe 路径的快速映射。"""
    paths: dict[str, str] = {}
    for proc in psutil.process_iter(["name", "exe"]):
        try:
            name = proc.info.get("name") or proc.name()
            exe = proc.info.get("exe") or proc.exe()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        if name and exe:
            paths[name] = exe
    return paths


# ── 键盘计数器 ──────────────────────────────────────────────

class KeystrokeMonitor:
    """全局键盘监听，计数写入 DB（按 BATCH_INTERVAL 批量）"""

    def __init__(self, db):
        self._db = db
        self._buf = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._listener = None
        self._thread = None

    # pynput 回调
    def _on_press(self, key):
        if key == keyboard.Key.esc:
            return  # ESC 不计数
        with self._lock:
            self._buf += 1

    # 批量写入线程
    def _flush_loop(self):
        while not self._stop.wait(BATCH_INTERVAL):
            with self._lock:
                n, self._buf = self._buf, 0
            if n:
                self._db.add_keystrokes(n)

    def start(self):
        self._listener = keyboard.Listener(on_press=self._on_press)
        self._listener.daemon = True
        self._listener.start()
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
        with self._lock:
            n, self._buf = self._buf, 0
        if n:
            self._db.add_keystrokes(n)


# ── 鼠标响应计数器 ──────────────────────────────────────────

class MouseMonitor:
    """全局鼠标监听，记录点击和滚轮响应，不记录移动。"""

    def __init__(self, db):
        self._db = db
        self._buf = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._listener = None
        self._thread = None

    def _count(self):
        with self._lock:
            self._buf += 1

    def _on_click(self, x, y, button, pressed):
        if pressed:
            self._count()

    def _on_scroll(self, x, y, dx, dy):
        self._count()

    def _flush_loop(self):
        while not self._stop.wait(BATCH_INTERVAL):
            with self._lock:
                n, self._buf = self._buf, 0
            if n:
                self._db.add_mouse_events(n)

    def start(self):
        self._listener = mouse.Listener(on_click=self._on_click, on_scroll=self._on_scroll)
        self._listener.daemon = True
        self._listener.start()
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
        with self._lock:
            n, self._buf = self._buf, 0
        if n:
            self._db.add_mouse_events(n)


# ── 前台窗口监控 ────────────────────────────────────────────

def _get_foreground() -> tuple[str, str, str]:
    """返回 (进程名, 窗口标题, 可执行文件路径)"""
    if not _HAS_WIN32:
        return ("unknown", "", "")
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return ("unknown", "", "")
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc = psutil.Process(pid.value)
        try:
            exe_path = proc.exe()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            exe_path = ""
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return (proc.name(), buf.value, exe_path)
    except Exception:
        return ("unknown", "", "")


class WindowMonitor:
    """轮询前台窗口，切换时记录上一段使用时间"""

    def __init__(self, db):
        self._db = db
        self._cur_app = None
        self._cur_title = ""
        self._cur_path = ""
        self._cur_start = None
        self._stop = threading.Event()

    def _loop(self):
        while not self._stop.wait(POLL_INTERVAL):
            app, title, path = _get_foreground()
            now = datetime.now().isoformat(timespec="seconds")
            if app != self._cur_app:
                # 结束上一段
                if self._cur_app and self._cur_start:
                    self._db.add_session(self._cur_app, self._cur_title, self._cur_start, now, self._cur_path)
                self._cur_app = app
                self._cur_title = title
                self._cur_path = path
                self._cur_start = now
            elif path and path != self._cur_path:
                self._cur_path = path

    def start(self):
        app, title, path = _get_foreground()
        self._cur_app = app
        self._cur_title = title
        self._cur_path = path
        self._cur_start = datetime.now().isoformat(timespec="seconds")
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()
        if self._cur_app and self._cur_start:
            now = datetime.now().isoformat(timespec="seconds")
            self._db.add_session(self._cur_app, self._cur_title, self._cur_start, now, self._cur_path)


# ── 总监控器 ────────────────────────────────────────────────

class Tracker:
    def __init__(self, db):
        self._db = db
        self._keys = KeystrokeMonitor(db)
        self._mouse = MouseMonitor(db)
        self._win = WindowMonitor(db)

    def start(self):
        self._keys.start()
        self._mouse.start()
        self._win.start()
        threading.Thread(target=self._remember_paths, daemon=True).start()

    def _remember_paths(self):
        try:
            self._db.remember_app_paths(collect_running_app_paths())
        except Exception:
            pass

    def stop(self):
        self._keys.stop()
        self._mouse.stop()
        self._win.stop()

    @property
    def stats(self):
        return self._db.today_stats()
