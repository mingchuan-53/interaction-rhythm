"""应用设置与 Windows 启动项管理。"""
import json
import os
import sys
from pathlib import Path

import winreg


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "交互节律"
DEFAULT_SETTINGS = {
    "auto_start": False,
    "background_start": False,
    "silent_start": False,
}


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def _data_dir() -> Path:
    path = _app_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _settings_path() -> Path:
    return _data_dir() / "settings.json"


def _load_file_settings() -> dict:
    data = dict(DEFAULT_SETTINGS)
    path = _settings_path()
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key in DEFAULT_SETTINGS:
                    if key in raw:
                        data[key] = bool(raw[key])
        except Exception:
            pass
    return data


def _save_file_settings(data: dict) -> None:
    _settings_path().write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _launcher_command(background: bool = False) -> str:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        args = ["--background"] if background else []
        return " ".join([f'"{exe}"', *args])

    packaged = Path(__file__).parent / "dist" / "current" / "InteractionRhythm" / "InteractionRhythm.exe"
    if packaged.exists():
        args = ["--background"] if background else []
        return " ".join([f'"{packaged}"', *args])

    main_py = Path(__file__).parent / "main.py"
    args = [f'"{main_py}"']
    if background:
        args.append("--background")
    return " ".join([f'"{Path(sys.executable)}"', *args])


def _read_run_value() -> str:
    if os.name != "nt":
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE_NAME)
            return str(value or "")
    except FileNotFoundError:
        return ""
    except OSError:
        return ""


def _write_run_value(command: str) -> None:
    if os.name != "nt":
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, command)


def _delete_run_value() -> None:
    if os.name != "nt":
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, RUN_VALUE_NAME)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def get_settings() -> dict:
    data = _load_file_settings()
    data["silent_start"] = bool(data.get("silent_start") or data.get("background_start"))
    data["background_start"] = data["silent_start"]
    run_command = _read_run_value()
    if run_command:
        data["auto_start"] = True
        silent = "--background" in run_command or "--hidden" in run_command or "--tray" in run_command
        data["background_start"] = silent
        data["silent_start"] = silent
    return data


def save_settings(patch: dict) -> dict:
    data = get_settings()
    if isinstance(patch, dict):
        for key in DEFAULT_SETTINGS:
            if key in patch:
                data[key] = bool(patch[key])
        if "silent_start" in patch:
            data["background_start"] = bool(patch["silent_start"])
        elif "background_start" in patch:
            data["silent_start"] = bool(patch["background_start"])

    _save_file_settings(data)
    if data["auto_start"]:
        _write_run_value(_launcher_command(data["silent_start"]))
    else:
        _delete_run_value()
    return get_settings()
