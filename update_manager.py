"""交互节律一键更新管理。"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import config


class UpdateError(RuntimeError):
    pass


@dataclass
class UpdatePackage:
    manifest: dict[str, Any]
    zip_path: Path
    staging_dir: Path


_CACHE_MAX_AGE_SECONDS = 60 * 60
_CHECK_LOCK = threading.Lock()
_CHECKING = False


def app_root() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent


def data_dir() -> Path:
    p = app_root() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def updates_dir() -> Path:
    p = data_dir() / "updates"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_path() -> Path:
    return updates_dir() / "update-cache.json"


def _read_update_cache() -> dict[str, Any] | None:
    path = _cache_path()
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
    except Exception:
        return None
    return None


def _write_update_cache(raw: dict[str, Any]) -> None:
    try:
        _cache_path().write_text(
            json.dumps({"checked_at": time.time(), "raw": raw}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for chunk in str(value).strip().lstrip("v").split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num or 0))
    return tuple(parts or [0])


def _http_json(url: str) -> dict[str, Any]:
    if not url:
        raise UpdateError("还没有配置更新清单地址")
    req = urllib.request.Request(url, headers={"User-Agent": f"InteractionRhythm/{config.APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=config.UPDATE_TIMEOUT) as resp:
        status = getattr(resp, "status", None) or resp.getcode() or 200
        if status >= 400:
            raise UpdateError(f"更新清单读取失败：HTTP {status}")
        return json.loads(resp.read().decode("utf-8"))


def _manifest_url() -> str:
    for path in (data_dir() / "update-url.txt", app_root() / "update-url.txt"):
        if path.is_file():
            url = path.read_text(encoding="utf-8").strip()
            if url:
                return url
    return config.UPDATE_MANIFEST_URL


def _unconfigured_manifest() -> dict[str, Any]:
    return {
        "app": config.APP_NAME,
        "channel": config.UPDATE_CHANNEL,
        "latest": config.APP_VERSION,
        "current": config.APP_VERSION,
        "has_update": False,
        "download_url": "",
        "sha256": "",
        "size": 0,
        "notes": ["当前测试版还没有配置更新清单地址。"],
        "published_at": "",
        "update_configured": False,
    }


def _normalize_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    latest = str(raw.get("latest") or raw.get("version") or "").strip().lstrip("v")
    download_url = str(raw.get("download_url") or raw.get("url") or "").strip()
    sha256 = str(raw.get("sha256") or "").strip().lower()
    if not latest:
        raise UpdateError("更新清单缺少 latest/version")
    if not download_url:
        raise UpdateError("更新清单缺少 download_url")
    if sha256 and (len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256)):
        raise UpdateError("更新清单里的 sha256 格式不正确")
    notes = raw.get("notes") or []
    if isinstance(notes, str):
        notes = [notes]
    return {
        "app": raw.get("app") or config.APP_NAME,
        "channel": raw.get("channel") or config.UPDATE_CHANNEL,
        "latest": latest,
        "current": config.APP_VERSION,
        "has_update": _version_tuple(latest) > _version_tuple(config.APP_VERSION),
        "download_url": download_url,
        "sha256": sha256,
        "size": int(raw.get("size") or 0),
        "notes": [str(item) for item in notes],
        "published_at": raw.get("published_at") or "",
        "update_configured": True,
    }


def check_update() -> dict[str, Any]:
    url = _manifest_url()
    if not url:
        return {"ok": True, "manifest": _unconfigured_manifest(), "cached": False, "checking": False}
    raw = _http_json(url)
    manifest = _normalize_manifest(raw)
    _write_update_cache(raw)
    return {"ok": True, "manifest": manifest, "cached": False, "checking": False, "checked_at": time.time()}


def _manifest_from_cache(cache: dict[str, Any] | None) -> tuple[dict[str, Any] | None, float]:
    if not cache:
        return None, 0
    raw = cache.get("raw")
    if not isinstance(raw, dict):
        raw = cache.get("manifest")
    if not isinstance(raw, dict):
        return None, 0
    try:
        checked_at = float(cache.get("checked_at") or 0)
        return _normalize_manifest(raw), checked_at
    except Exception:
        return None, 0


def _background_check_update() -> None:
    global _CHECKING
    try:
        check_update()
    except Exception:
        pass
    finally:
        with _CHECK_LOCK:
            _CHECKING = False


def start_update_check_async() -> bool:
    global _CHECKING
    if not _manifest_url():
        return False
    with _CHECK_LOCK:
        if _CHECKING:
            return True
        _CHECKING = True
    threading.Thread(target=_background_check_update, name="UpdateCheck", daemon=True).start()
    return True


def update_status(max_age_seconds: int = _CACHE_MAX_AGE_SECONDS) -> dict[str, Any]:
    if not _manifest_url():
        return {"ok": True, "manifest": _unconfigured_manifest(), "cached": False, "checking": False}

    manifest, checked_at = _manifest_from_cache(_read_update_cache())
    fresh = bool(manifest and checked_at and (time.time() - checked_at) < max_age_seconds)
    if fresh:
        return {"ok": True, "manifest": manifest, "cached": True, "checking": False, "checked_at": checked_at}

    checking = start_update_check_async()
    if manifest:
        return {"ok": True, "manifest": manifest, "cached": True, "checking": checking, "checked_at": checked_at}

    pending = {
        "app": config.APP_NAME,
        "channel": config.UPDATE_CHANNEL,
        "latest": config.APP_VERSION,
        "current": config.APP_VERSION,
        "has_update": False,
        "download_url": "",
        "sha256": "",
        "size": 0,
        "notes": ["正在后台检查更新。"],
        "published_at": "",
        "update_configured": True,
    }
    return {"ok": True, "manifest": pending, "cached": False, "checking": checking, "checked_at": 0}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, target: Path) -> None:
    tmp = target.with_suffix(target.suffix + ".part")
    if tmp.exists():
        tmp.unlink()
    req = urllib.request.Request(url, headers={"User-Agent": f"InteractionRhythm/{config.APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=config.UPDATE_TIMEOUT) as resp, tmp.open("wb") as f:
        status = getattr(resp, "status", None) or resp.getcode() or 200
        if status >= 400:
            raise UpdateError(f"更新包下载失败：HTTP {status}")
        shutil.copyfileobj(resp, f)
    tmp.replace(target)


def _prepare_staging(manifest: dict[str, Any]) -> UpdatePackage:
    root = updates_dir()
    version = manifest["latest"]
    zip_path = root / f"InteractionRhythm-v{version}.zip"
    staging_dir = root / f"staging-v{version}"

    _download(manifest["download_url"], zip_path)
    expected = manifest.get("sha256") or ""
    if expected and _sha256(zip_path).lower() != expected:
        raise UpdateError("更新包校验失败，sha256 不匹配")

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            base = staging_dir.resolve()
            for member in zf.infolist():
                target = (staging_dir / member.filename).resolve()
                try:
                    target.relative_to(base)
                except ValueError:
                    raise UpdateError("更新包包含不安全路径")
            zf.extractall(staging_dir)
    except zipfile.BadZipFile as exc:
        raise UpdateError("更新包不是有效 zip 文件") from exc

    if not _find_new_exe(staging_dir):
        raise UpdateError("更新包里没有找到 InteractionRhythm.exe")
    return UpdatePackage(manifest=manifest, zip_path=zip_path, staging_dir=staging_dir)


def _find_new_exe(staging_dir: Path) -> Path | None:
    direct = staging_dir / "InteractionRhythm.exe"
    if direct.is_file():
        return direct
    matches = list(staging_dir.glob("**/InteractionRhythm.exe"))
    return matches[0] if matches else None


def _write_updater(package: UpdatePackage) -> Path:
    script_path = updates_dir() / "run-update.ps1"
    root = app_root()
    exe = root / "InteractionRhythm.exe"
    new_exe = _find_new_exe(package.staging_dir)
    if not new_exe:
        raise UpdateError("更新包里没有找到 InteractionRhythm.exe")
    source_root = new_exe.parent
    backup = Path(tempfile.gettempdir()) / f"InteractionRhythm-backup-{config.APP_VERSION}-{int(time.time())}"

    script = f"""$ErrorActionPreference = "Stop"
$Target = {json.dumps(str(root), ensure_ascii=False)}
$Source = {json.dumps(str(source_root), ensure_ascii=False)}
$Backup = {json.dumps(str(backup), ensure_ascii=False)}
$Exe = {json.dumps(str(exe), ensure_ascii=False)}
$Log = Join-Path {json.dumps(str(updates_dir()), ensure_ascii=False)} "last-update.log"
function Log($m) {{ Add-Content -LiteralPath $Log -Value ("[{0}] {{1}}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m) -Encoding UTF8 }}
try {{
  Log "update started"
  Start-Sleep -Milliseconds 1200
  $ProcessNames = @("InteractionRhythm", "TypeTracker")
  $deadline = (Get-Date).AddSeconds(20)
  while ((Get-Process -Name $ProcessNames -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {{
    Start-Sleep -Milliseconds 500
  }}
  Get-Process -Name $ProcessNames -ErrorAction SilentlyContinue | Stop-Process -Force

  if (Test-Path $Backup) {{ Remove-Item -LiteralPath $Backup -Recurse -Force }}
  New-Item -Path $Backup -ItemType Directory -Force | Out-Null
  $Data = Join-Path $Target "data"
  $DataBackup = Join-Path $Backup "data-preserved"
  if (Test-Path $Data) {{
    Copy-Item -LiteralPath $Data -Destination $DataBackup -Recurse -Force
    Log "user data preserved"
  }}
  Get-ChildItem -LiteralPath $Target -Force | Where-Object {{ $_.Name -ne "data" }} | ForEach-Object {{
    Move-Item -LiteralPath $_.FullName -Destination $Backup -Force
  }}

  Get-ChildItem -LiteralPath $Source -Force | Where-Object {{ $_.Name -ne "data" }} | ForEach-Object {{
    Copy-Item -LiteralPath $_.FullName -Destination $Target -Recurse -Force
  }}
  if (-not (Test-Path $Data)) {{ New-Item -Path $Data -ItemType Directory -Force | Out-Null }}
  if (Test-Path $DataBackup) {{
    Get-ChildItem -LiteralPath $DataBackup -Force | ForEach-Object {{
      Copy-Item -LiteralPath $_.FullName -Destination $Data -Recurse -Force
    }}
  }}
  $SourceData = Join-Path $Source "data"
  if (Test-Path $SourceData) {{
    foreach ($name in @("update-url.txt","交互节律.ico","interaction-rhythm-title.png")) {{
      $sourceItem = Join-Path $SourceData $name
      if (Test-Path $sourceItem) {{
        Copy-Item -LiteralPath $sourceItem -Destination $Data -Recurse -Force
      }}
    }}
  }}
  foreach ($name in @("tracker.db","tracker.db-wal","tracker.db-shm","settings.json")) {{
    $backupItem = Join-Path $DataBackup $name
    $targetItem = Join-Path $Data $name
    if ((Test-Path $backupItem) -and -not (Test-Path $targetItem)) {{
      Copy-Item -LiteralPath $backupItem -Destination $Data -Force
    }}
  }}

  Start-Process -FilePath $Exe -WorkingDirectory $Target
  Log "update finished"
  try {{ Remove-Item -LiteralPath $Backup -Recurse -Force }} catch {{}}
}} catch {{
  Log ("update failed: " + $_.Exception.Message)
  try {{
    if (Test-Path $Backup) {{
      Get-ChildItem -LiteralPath $Backup -Force | Where-Object {{ $_.Name -ne "data-preserved" }} | ForEach-Object {{
        Copy-Item -LiteralPath $_.FullName -Destination $Target -Recurse -Force
      }}
      if (Test-Path (Join-Path $Backup "data-preserved")) {{
        New-Item -Path (Join-Path $Target "data") -ItemType Directory -Force | Out-Null
        Get-ChildItem -LiteralPath (Join-Path $Backup "data-preserved") -Force | ForEach-Object {{
          Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Target "data") -Recurse -Force
        }}
      }}
      Start-Process -FilePath $Exe -WorkingDirectory $Target
    }}
  }} catch {{}}
}}
"""
    script_path.write_text(script, encoding="utf-8")
    return script_path


def install_update_async(manifest: dict[str, Any], shutdown_callback) -> dict[str, Any]:
    if not getattr(sys, "frozen", False):
        raise UpdateError("源码运行模式不执行自我更新，请打包后测试")
    if not callable(shutdown_callback):
        raise UpdateError("更新退出回调未配置")
    manifest = _normalize_manifest(manifest)
    if not manifest["has_update"]:
        return {"ok": True, "message": "已经是最新版本"}

    package = _prepare_staging(manifest)
    script = _write_updater(package)
    subprocess.Popen([
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
    ], cwd=str(app_root()), close_fds=True)

    def _shutdown():
        time.sleep(0.4)
        shutdown_callback()

    threading.Thread(target=_shutdown, daemon=True).start()
    return {"ok": True, "message": "更新包已下载，应用即将关闭并自动重启"}
