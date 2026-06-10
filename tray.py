"""系统托盘图标（pystray + Pillow）高分辨率版"""
from PIL import Image, ImageDraw

import config


def make_icon(size: int = 256) -> Image.Image:
    """生成高清节律方格图标。

    小尺寸图标减少格子数量，避免 Windows 桌面和任务栏缩放后发糊。
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(1, int(size * 0.075))
    r = max(3, int(size * 0.19))
    shadow = max(1, int(size * 0.018))
    draw.rounded_rectangle(
        [pad + shadow, pad + shadow, size - pad + shadow, size - pad + shadow],
        radius=r,
        fill=(20, 83, 45, 42),
    )
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=r,
        fill=(239, 248, 241),
    )
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=r,
        outline=(20, 83, 45, 220),
        width=max(1, size // 28),
    )

    grid = 2 if size <= 24 else 3 if size <= 48 else 4
    inner = int(size * (0.25 if grid == 2 else 0.20 if grid == 3 else 0.17))
    gap = max(1, int(size * (0.06 if grid == 2 else 0.045 if grid == 3 else 0.035)))
    cell = max(2, (size - pad * 2 - inner * 2 - gap * (grid - 1)) // grid)
    x0 = pad + inner
    y0 = pad + inner
    palette = [
        (187, 247, 208, 255), (134, 239, 172, 255), (74, 222, 128, 255), (34, 197, 94, 255),
        (22, 163, 74, 255), (21, 128, 61, 255), (22, 101, 52, 255), (20, 83, 45, 255),
        (166, 226, 185, 255), (86, 211, 132, 255), (39, 174, 96, 255), (27, 120, 63, 255),
        (210, 245, 220, 255), (115, 226, 155, 255), (31, 145, 76, 255), (18, 96, 52, 255),
    ]
    if grid == 2:
        colors = [palette[3], palette[5], palette[1], palette[7]]
    elif grid == 3:
        colors = [palette[i] for i in (12, 2, 5, 1, 6, 10, 4, 8, 7)]
    else:
        colors = palette

    for row in range(grid):
        for col in range(grid):
            x = x0 + col * (cell + gap)
            y = y0 + row * (cell + gap)
            draw.rounded_rectangle(
                [x, y, x + cell, y + cell],
                radius=max(1, int(cell * 0.22)),
                fill=colors[row * grid + col],
            )
    return img


def make_ico(ico_path: str):
    """生成 .ico 文件（多分辨率）"""
    sizes = [16, 32, 48, 64, 128, 256]
    imgs = [make_icon(s) for s in sizes]
    imgs[-1].save(
        ico_path,
        format="ICO",
        append_images=imgs[:-1],
        sizes=[(s, s) for s in sizes],
    )


def create_tray(tracker, port: int):
    """返回 (icon, start_fn) — icon.run() 在后台线程启动托盘"""
    import os
    import pystray
    import webbrowser

    _APP_NAMES = {
        "Code": "VS Code", "chrome": "Chrome", "msedge": "Edge",
        "firefox": "Firefox", "explorer": "文件管理器",
        "cmd": "命令提示符", "powershell": "PowerShell",
        "WindowsTerminal": "终端", "wt": "终端",
        "WeChat": "微信", "wechat": "微信", "QQ": "QQ",
        "DingTalk": "钉钉", "dingtalk": "钉钉",
        "Lark": "飞书", "feishu": "飞书",
        "Teams": "Teams", "Telegram": "Telegram",
        "Discord": "Discord", "Slack": "Slack",
        "notepad": "记事本", "notepad++": "Notepad++",
        "Obsidian": "Obsidian", "Notion": "Notion",
        "Typora": "Typora", "Spotify": "Spotify",
        "Zoom": "Zoom", "Docker Desktop": "Docker",
        "Photoshop": "Photoshop", "Figma": "Figma",
        "idea64": "IntelliJ", "pycharm64": "PyCharm",
        "devenv": "Visual Studio",
        "ApplicationFrameHost": "UWP应用",
    }

    def _fmt(sec):
        h, m = divmod(sec // 60, 60)
        return f"{h}h {m:02d}m" if h else f"{m}m"

    def _noop(icon=None, item=None):
        pass

    def _app_name(app):
        if app in _APP_NAMES:
            return _APP_NAMES[app]
        base = app.replace(".exe", "")
        return _APP_NAMES.get(base, base.title())

    def _clip(text, limit=26):
        return text if len(text) <= limit else text[: limit - 1] + "…"

    def _tooltip():
        s = tracker.stats
        total = int(s.get("keystrokes", 0)) + int(s.get("mouse_events", 0))
        return f"{config.APP_NAME} · 响应 {total:,} · 活跃 {_fmt(s.get('total_seconds', 0))}"

    def _restore_window():
        import ctypes

        user32 = ctypes.windll.user32
        _set_window_pos = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_uint,
        )(("SetWindowPos", user32))
        user32.GetParent.argtypes = [ctypes.c_void_p]
        user32.GetParent.restype = ctypes.c_void_p
        user32.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetWindow.restype = ctypes.c_void_p
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int
        user32.SystemParametersInfoW.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        user32.SystemParametersInfoW.restype = ctypes.c_bool
        user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        user32.GetWindowRect.restype = ctypes.c_bool
        SW_SHOW = 5
        SW_RESTORE = 9
        GWL_EXSTYLE = -20
        GW_OWNER = 4
        WS_EX_APPWINDOW = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080
        SWP_NOZORDER = 0x0004
        SWP_NOOWNERZORDER = 0x0200
        SWP_SHOWWINDOW = 0x0040
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_FRAMECHANGED = 0x0020
        SPI_GETWORKAREA = 0x0030
        SM_CXSCREEN = 0
        SM_CYSCREEN = 1
        WINDOW_WIDTH = 540
        WINDOW_HEIGHT = 610

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long),
            ]

        def _center_position(width, height):
            work = RECT()
            if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(work), 0):
                left, top, right, bottom = work.left, work.top, work.right, work.bottom
            else:
                left, top = 0, 0
                right = user32.GetSystemMetrics(SM_CXSCREEN)
                bottom = user32.GetSystemMetrics(SM_CYSCREEN)
            return (
                left + max(0, (right - left - width) // 2),
                top + max(0, (bottom - top - height) // 2),
            )

        def _is_offscreen_or_tiny(hwnd):
            rect = RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            width = max(0, rect.right - rect.left)
            height = max(0, rect.bottom - rect.top)
            if width < WINDOW_WIDTH // 2 or height < WINDOW_HEIGHT // 2:
                return True

            work = RECT()
            if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(work), 0):
                return (
                    rect.right <= work.left
                    or rect.left >= work.right
                    or rect.bottom <= work.top
                    or rect.top >= work.bottom
                    or rect.left < work.left - 200
                    or rect.top < work.top - 200
                )
            return rect.left < -200 or rect.top < -200

        candidates = []

        def _enum(hwnd, _):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if buf.value == config.APP_NAME:
                    rect = RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
                    exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    score = area
                    if exstyle & WS_EX_APPWINDOW:
                        score += 1_000_000_000
                    if exstyle & WS_EX_TOOLWINDOW:
                        score -= 1_000_000_000
                    if user32.GetParent(hwnd):
                        score -= 1_000_000
                    if user32.GetWindow(hwnd, GW_OWNER):
                        score -= 1_000_000
                    candidates.append((score, hwnd))
            return True

        callback = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(_enum)
        user32.EnumWindows(callback, 0)
        if not candidates:
            return False
        hwnd = max(candidates, key=lambda item: item[0])[1]
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.ShowWindow(hwnd, SW_RESTORE)
        if _is_offscreen_or_tiny(hwnd):
            x, y = _center_position(WINDOW_WIDTH, WINDOW_HEIGHT)
            _set_window_pos(
                hwnd, 0, x, y, WINDOW_WIDTH, WINDOW_HEIGHT,
                SWP_NOZORDER | SWP_NOOWNERZORDER | SWP_FRAMECHANGED | SWP_SHOWWINDOW,
            )
        else:
            _set_window_pos(
                hwnd, 0, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOOWNERZORDER | SWP_FRAMECHANGED | SWP_SHOWWINDOW,
            )
        user32.SetForegroundWindow(hwnd)
        return True

    def _open_dashboard(icon=None, item=None):
        if not _restore_window():
            webbrowser.open(f"http://localhost:{port}")

    def _refresh_now(icon, item=None):
        icon.title = _tooltip()
        icon.menu = _build_menu()
        icon.update_menu()

    def _build_menu():
        s = tracker.stats
        kd = f"{s.get('keystrokes', 0):,}"
        md = f"{s.get('mouse_events', 0):,}"
        rd = f"{s.get('keystrokes', 0) + s.get('mouse_events', 0):,}"
        total = _fmt(s["total_seconds"])
        apps = s.get("apps", [])[:8]

        items = [
            pystray.MenuItem(f"打开 {config.APP_NAME}", _open_dashboard, default=True),
            pystray.MenuItem(f"今日响应  {rd}", _noop, enabled=False),
            pystray.MenuItem(f"键盘  {kd}    鼠标  {md}", _noop, enabled=False),
            pystray.MenuItem(f"活跃时长  {total}", _noop, enabled=False),
            pystray.Menu.SEPARATOR,
        ]
        for a in apps:
            name = _clip(_app_name(a["app"]))
            t = _fmt(a["seconds"])
            items.append(pystray.MenuItem(f"{len(items)-4}. {name}  {t}", _noop, enabled=False))
        items += [
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("刷新数据", _refresh_now),
            pystray.MenuItem(f"退出 {config.APP_NAME}", _on_quit),
        ]
        return pystray.Menu(*items)

    def _on_quit(icon, item):
        def _quit():
            import time

            def _force_exit():
                time.sleep(1.2)
                os._exit(0)

            import threading
            threading.Thread(target=_force_exit, daemon=True).start()
            try:
                tracker.stop()
            except Exception:
                pass
            try:
                icon.visible = False
            except Exception:
                pass
            os._exit(0)

        import threading
        threading.Thread(target=_quit, daemon=True).start()

    icon = pystray.Icon(
        config.APP_NAME,
        make_icon(64),
        _tooltip(),
        menu=_build_menu(),
    )

    def _refresh():
        """每隔一段时间刷新菜单数据"""
        import time
        while True:
            time.sleep(15)
            try:
                icon.title = _tooltip()
                icon.menu = _build_menu()
                icon.update_menu()
            except Exception:
                pass

    def start():
        import threading
        threading.Thread(target=_refresh, daemon=True).start()
        icon.run()

    return icon, start
