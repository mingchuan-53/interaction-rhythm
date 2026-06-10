"""Windows 应用图标提取与本地 PNG 缓存。"""
from __future__ import annotations

import ctypes
import hashlib
import sys
from ctypes import wintypes
from pathlib import Path

from PIL import Image

ICON_SIZE = 32
SHGFI_ICON = 0x000000100
SHGFI_LARGEICON = 0x000000000
DI_NORMAL = 0x0003
DIB_RGB_COLORS = 0
BI_RGB = 0


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [
        ("hIcon", wintypes.HICON),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", wintypes.WCHAR * 260),
        ("szTypeName", wintypes.WCHAR * 80),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 1),
    ]


def _data_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent
    path = base / "data" / "icons"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_path(exe_path: Path) -> Path:
    try:
        mtime = exe_path.stat().st_mtime_ns
    except OSError:
        mtime = 0
    key = f"{str(exe_path).lower()}|{mtime}".encode("utf-8", "ignore")
    return _data_dir() / f"{hashlib.sha1(key).hexdigest()}.png"


def _configure_win32():
    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    shell32.SHGetFileInfoW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(SHFILEINFOW),
        wintypes.UINT,
        wintypes.UINT,
    ]
    shell32.SHGetFileInfoW.restype = ctypes.c_size_t

    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    user32.DrawIconEx.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HICON,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
        wintypes.HBRUSH,
        wintypes.UINT,
    ]
    user32.DrawIconEx.restype = wintypes.BOOL
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    user32.DestroyIcon.restype = wintypes.BOOL

    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC,
        ctypes.POINTER(BITMAPINFO),
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL

    return shell32, user32, gdi32


def _extract_icon(path: Path, target: Path) -> bool:
    shell32, user32, gdi32 = _configure_win32()
    info = SHFILEINFOW()
    ok = shell32.SHGetFileInfoW(
        str(path),
        0,
        ctypes.byref(info),
        ctypes.sizeof(info),
        SHGFI_ICON | SHGFI_LARGEICON,
    )
    if not ok or not info.hIcon:
        return False

    hdc = None
    memdc = None
    bitmap = None
    old_bitmap = None
    bits = ctypes.c_void_p()
    try:
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = ICON_SIZE
        bmi.bmiHeader.biHeight = -ICON_SIZE
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB

        hdc = user32.GetDC(None)
        memdc = gdi32.CreateCompatibleDC(hdc)
        bitmap = gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
        if not bitmap or not bits.value:
            return False

        old_bitmap = gdi32.SelectObject(memdc, bitmap)
        if not user32.DrawIconEx(memdc, 0, 0, info.hIcon, ICON_SIZE, ICON_SIZE, 0, None, DI_NORMAL):
            return False

        raw = ctypes.string_at(bits.value, ICON_SIZE * ICON_SIZE * 4)
        image = Image.frombuffer("RGBA", (ICON_SIZE, ICON_SIZE), raw, "raw", "BGRA", 0, 1)
        if image.getbbox() is None:
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target, "PNG")
        return True
    finally:
        if old_bitmap and memdc:
            gdi32.SelectObject(memdc, old_bitmap)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memdc:
            gdi32.DeleteDC(memdc)
        if hdc:
            user32.ReleaseDC(None, hdc)
        if info.hIcon:
            user32.DestroyIcon(info.hIcon)


def icon_bytes(exe_path: str) -> bytes | None:
    """返回指定 exe 的 PNG 图标字节；失败时返回 None。"""
    if not exe_path:
        return None
    path = Path(exe_path)
    suffix = path.suffix.lower()
    if suffix not in {".exe", ".ico", ".lnk"} or not path.exists():
        return None

    cache = _cache_path(path)
    if cache.is_file():
        return cache.read_bytes()
    try:
        if _extract_icon(path, cache) and cache.is_file():
            return cache.read_bytes()
    except Exception:
        return None
    return None
