"""键盘响应、鼠标响应与前台窗口使用时间监控。"""
import ctypes
import ctypes.wintypes as wintypes
import ntpath
import threading
import time
from datetime import datetime

from config import POLL_INTERVAL, BATCH_INTERVAL

try:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    _HAS_WIN32 = True
except Exception:
    _HAS_WIN32 = False


ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
LowLevelProc = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MAX_PATH = 260

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
HC_ACTION = 0
WM_QUIT = 0x0012
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207
WM_XBUTTONDOWN = 0x020B
WM_MOUSEWHEEL = 0x020A
WM_MOUSEHWHEEL = 0x020E
VK_ESCAPE = 0x1B


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ULONG_PTR),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * MAX_PATH),
    ]


if _HAS_WIN32:
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, LowLevelProc, wintypes.HINSTANCE, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = wintypes.HANDLE
    user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallNextHookEx.restype = LRESULT
    user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostThreadMessageW.restype = wintypes.BOOL

    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    kernel32.Process32NextW.restype = wintypes.BOOL


def _query_process_path(pid: int) -> str:
    if not _HAS_WIN32 or not pid:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32767)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
    except Exception:
        return ""
    finally:
        kernel32.CloseHandle(handle)
    return ""


def collect_running_app_paths() -> dict[str, str]:
    """扫描进程路径，用原生 API 避免拉起沉重的进程库。"""
    if not _HAS_WIN32:
        return {}
    paths: dict[str, str] = {}
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == INVALID_HANDLE_VALUE:
        return paths
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            name = entry.szExeFile
            path = _query_process_path(entry.th32ProcessID)
            if name and path:
                paths[name] = path
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return paths


class _LowLevelHook:
    def __init__(self, hook_id: int, messages: set[int], on_event):
        self._hook_id = hook_id
        self._messages = messages
        self._on_event = on_event
        self._callback = None
        self._hook = None
        self._thread = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._stop = threading.Event()

    def start(self) -> bool:
        if not _HAS_WIN32:
            return False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(1.2)
        return bool(self._hook)

    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()

        def _proc(n_code, w_param, l_param):
            try:
                if n_code == HC_ACTION and int(w_param) in self._messages:
                    self._on_event(int(w_param), l_param)
            except Exception:
                pass
            return user32.CallNextHookEx(self._hook, n_code, w_param, l_param)

        self._callback = LowLevelProc(_proc)
        hmod = kernel32.GetModuleHandleW(None)
        self._hook = user32.SetWindowsHookExW(self._hook_id, self._callback, hmod, 0)
        if not self._hook:
            self._hook = user32.SetWindowsHookExW(self._hook_id, self._callback, None, 0)
        self._ready.set()
        if not self._hook:
            return

        msg = wintypes.MSG()
        while not self._stop.is_set():
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def stop(self):
        self._stop.set()
        if _HAS_WIN32 and self._thread_id:
            try:
                user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass


# ── 键盘计数器 ──────────────────────────────────────────────

class KeystrokeMonitor:
    """全局键盘监听，计数写入 DB（按 BATCH_INTERVAL 批量）。"""

    def __init__(self, db, current_app):
        self._db = db
        self._current_app = current_app
        self._buf = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._hook = None
        self._thread = None

    def _count(self):
        with self._lock:
            self._buf += 1

    def _on_key(self, _message, l_param):
        info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        if info.vkCode != VK_ESCAPE:
            self._count()

    def _flush_loop(self):
        while not self._stop.wait(BATCH_INTERVAL):
            with self._lock:
                n, self._buf = self._buf, 0
            if n:
                app, _title, path = self._current_app()
                self._db.add_keystrokes(n, app, path)

    def start(self):
        if self._stop.is_set():
            return
        self._hook = _LowLevelHook(WH_KEYBOARD_LL, {WM_KEYDOWN, WM_SYSKEYDOWN}, self._on_key)
        self._hook.start()
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._hook:
            self._hook.stop()
        with self._lock:
            n, self._buf = self._buf, 0
        if n:
            app, _title, path = self._current_app()
            self._db.add_keystrokes(n, app, path)

    def flush(self):
        with self._lock:
            n, self._buf = self._buf, 0
        if n:
            app, _title, path = self._current_app()
            self._db.add_keystrokes(n, app, path)


# ── 鼠标响应计数器 ──────────────────────────────────────────

class MouseMonitor:
    """全局鼠标监听，记录点击和滚轮响应，不记录移动。"""

    def __init__(self, db, current_app):
        self._db = db
        self._current_app = current_app
        self._buf = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._hook = None
        self._thread = None

    def _count(self, *_):
        with self._lock:
            self._buf += 1

    def _flush_loop(self):
        while not self._stop.wait(BATCH_INTERVAL):
            with self._lock:
                n, self._buf = self._buf, 0
            if n:
                app, _title, path = self._current_app()
                self._db.add_mouse_events(n, app, path)

    def start(self):
        if self._stop.is_set():
            return
        self._hook = _LowLevelHook(
            WH_MOUSE_LL,
            {WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_XBUTTONDOWN, WM_MOUSEWHEEL, WM_MOUSEHWHEEL},
            self._count,
        )
        self._hook.start()
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._hook:
            self._hook.stop()
        with self._lock:
            n, self._buf = self._buf, 0
        if n:
            app, _title, path = self._current_app()
            self._db.add_mouse_events(n, app, path)

    def flush(self):
        with self._lock:
            n, self._buf = self._buf, 0
        if n:
            app, _title, path = self._current_app()
            self._db.add_mouse_events(n, app, path)


# ── 前台窗口监控 ────────────────────────────────────────────

def _get_foreground() -> tuple[str, str, str]:
    """返回 (进程名, 窗口标题, 可执行文件路径)。"""
    if not _HAS_WIN32:
        return ("unknown", "", "")
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ("unknown", "", "")

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        path = _query_process_path(pid.value)
        name = ntpath.basename(path) if path else "unknown"

        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return (name, buf.value, path)
    except Exception:
        return ("unknown", "", "")


class WindowMonitor:
    """轮询前台窗口，切换时记录上一段使用时间。"""

    def __init__(self, db):
        self._db = db
        self._cur_app = None
        self._cur_title = ""
        self._cur_path = ""
        self._cur_start = None
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def _loop(self):
        while not self._stop.wait(POLL_INTERVAL):
            app, title, path = _get_foreground()
            now = datetime.now().isoformat(timespec="seconds")
            if app != self._cur_app:
                with self._lock:
                    prev_app = self._cur_app
                    prev_title = self._cur_title
                    prev_path = self._cur_path
                    prev_start = self._cur_start
                    self._cur_app = app
                    self._cur_title = title
                    self._cur_path = path
                    self._cur_start = now
                if prev_app and prev_start:
                    self._db.add_session(prev_app, prev_title, prev_start, now, prev_path)
            elif path and path != self._cur_path:
                with self._lock:
                    self._cur_path = path

    def start(self):
        app, title, path = _get_foreground()
        with self._lock:
            self._cur_app = app
            self._cur_title = title
            self._cur_path = path
            self._cur_start = datetime.now().isoformat(timespec="seconds")
        threading.Thread(target=self._loop, daemon=True).start()

    def current_app(self) -> tuple[str, str, str]:
        with self._lock:
            return (self._cur_app or "unknown", self._cur_title, self._cur_path)

    def stop(self):
        self._stop.set()
        with self._lock:
            app = self._cur_app
            title = self._cur_title
            path = self._cur_path
            start = self._cur_start
        if app and start:
            now = datetime.now().isoformat(timespec="seconds")
            self._db.add_session(app, title, start, now, path)

    def flush(self):
        app, title, path = _get_foreground()
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            prev_app = self._cur_app
            prev_title = self._cur_title
            prev_path = self._cur_path
            prev_start = self._cur_start
            self._cur_app = app
            self._cur_title = title
            self._cur_path = path
            self._cur_start = now
        if prev_app and prev_start:
            self._db.add_session(prev_app, prev_title, prev_start, now, prev_path)


# ── 总监控器 ────────────────────────────────────────────────

class Tracker:
    def __init__(self, db):
        self._db = db
        self._win = WindowMonitor(db)
        self._keys = KeystrokeMonitor(db, self._win.current_app)
        self._mouse = MouseMonitor(db, self._win.current_app)
        self._stop = threading.Event()

    def start(self):
        self._win.start()
        threading.Thread(target=self._start_input_monitors, daemon=True).start()
        threading.Thread(target=self._remember_paths, daemon=True).start()

    def _start_input_monitors(self):
        if self._stop.wait(0.25):
            return
        self._keys.start()
        if self._stop.wait(0.75):
            return
        self._mouse.start()

    def _remember_paths(self):
        if self._stop.wait(20):
            return
        try:
            self._db.remember_app_paths(collect_running_app_paths())
        except Exception:
            pass

    def stop(self):
        self._stop.set()
        self._keys.stop()
        self._mouse.stop()
        self._win.stop()

    def flush(self):
        self._keys.flush()
        self._mouse.flush()
        self._win.flush()

    def checkpoint(self):
        self._db.checkpoint()

    @property
    def stats(self):
        return self._db.today_stats()
