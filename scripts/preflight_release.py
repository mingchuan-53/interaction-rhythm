"""Release package checks for 扣舷."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path


FORBIDDEN_EXACT = {
    ".current-app.pid",
    ".source-ui-test.pid",
    "tracker.db",
    "tracker.db-wal",
    "tracker.db-shm",
    "settings.json",
    "update-cache.json",
    "last-update.log",
    "last-update-state.json",
    "startup-error.log",
    "tray-error.log",
}

FORBIDDEN_SUFFIXES = {
    ".db",
    ".db-wal",
    ".db-shm",
    ".sqlite",
    ".sqlite3",
    ".log",
    ".err",
    ".out",
    ".pid",
}

FORBIDDEN_PARTS = {
    "__pycache__",
    ".venv",
    "build",
    "dist",
    "installer/output",
    "data/updates",
    "data/diagnostics",
}

ALLOWED_DATA_FILES = {
    "data/update-url.txt",
    "data/交互节律.ico",
    "data/叩舷.ico",
    "data/扣舷.ico",
    "data/interaction-rhythm-title.png",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_names(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as zf:
        return [name.replace("\\", "/") for name in zf.namelist()]


def _check_names(package_name: str, names: list[str], require_exe: bool = True, require_update_url: bool = True) -> list[str]:
    errors: list[str] = []
    lowered = [name.lower().strip("/") for name in names]
    if require_exe and not any(name.endswith("InteractionRhythm.exe") for name in names):
        errors.append(f"{package_name}: missing InteractionRhythm.exe")
    if require_update_url and "update-url.txt" not in lowered:
        errors.append(f"{package_name}: missing root update-url.txt")

    for original, name in zip(names, lowered):
        is_dir = original.endswith("/") or original.endswith("\\")
        clean_name = name.strip("/")
        leaf = clean_name.rsplit("/", 1)[-1]
        if not clean_name:
            continue
        if is_dir:
            continue
        if leaf in FORBIDDEN_EXACT:
            errors.append(f"{package_name}: forbidden file {original}")
            continue
        if any(clean_name.startswith(part + "/") or clean_name == part for part in FORBIDDEN_PARTS):
            errors.append(f"{package_name}: forbidden path {original}")
            continue
        if any(clean_name.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
            errors.append(f"{package_name}: forbidden suffix {original}")
            continue
        if clean_name.startswith("debug-") or leaf.startswith("debug-") or leaf.startswith("screenshot"):
            errors.append(f"{package_name}: debug artifact {original}")
            continue
        if clean_name.startswith("data/") and not clean_name.endswith("/"):
            if clean_name.startswith("data/icons/"):
                errors.append(f"{package_name}: icon cache must stay out of release package: {original}")
                continue
            if clean_name not in ALLOWED_DATA_FILES:
                errors.append(f"{package_name}: unexpected data file {original}")
    return errors


def check_zip(zip_path: Path) -> list[str]:
    if not zip_path.is_file():
        return [f"missing zip: {zip_path}"]
    try:
        names = normalized_names(zip_path)
    except zipfile.BadZipFile:
        return [f"invalid zip: {zip_path}"]
    return _check_names(zip_path.name, names)


def check_release_dir(release_dir: Path) -> list[str]:
    if not release_dir.is_dir():
        return [f"missing release dir: {release_dir}"]
    names = [
        path.relative_to(release_dir).as_posix()
        for path in release_dir.rglob("*")
        if path.is_file()
    ]
    return _check_names(release_dir.name, names)


def check_manifest(release_root: Path, version: str) -> list[str]:
    errors: list[str] = []
    manifest_path = release_root / "update.json"
    github_zip = release_root / "interaction-rhythm.zip"
    if not manifest_path.is_file():
        return [f"missing manifest: {manifest_path}"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid update.json: {exc}"]
    if str(manifest.get("latest", "")).lstrip("v") != version.lstrip("v"):
        errors.append(f"manifest latest mismatch: {manifest.get('latest')} != {version}")
    if not github_zip.is_file():
        errors.append("missing interaction-rhythm.zip for manifest check")
        return errors
    actual_hash = sha256(github_zip)
    if str(manifest.get("sha256", "")).lower() != actual_hash:
        errors.append("manifest sha256 does not match interaction-rhythm.zip")
    actual_size = github_zip.stat().st_size
    if int(manifest.get("size") or 0) != actual_size:
        errors.append("manifest size does not match interaction-rhythm.zip")
    download_url = str(manifest.get("download_url") or "")
    if f"v{version.lstrip('v')}" not in download_url:
        errors.append("manifest download_url does not include the current version tag")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", default="dist/releases")
    parser.add_argument("--version", required=True)
    parser.add_argument("--json-report", default="")
    args = parser.parse_args()

    release_root = Path(args.release_root)
    zips = [
        release_root / "扣舷.zip",
        release_root / "interaction-rhythm.zip",
    ]
    errors: list[str] = []
    for zip_path in zips:
        errors.extend(check_zip(zip_path))
    errors.extend(check_release_dir(release_root / f"InteractionRhythm-v{args.version.lstrip('v')}"))
    errors.extend(check_manifest(release_root, args.version))

    report = {
        "ok": not errors,
        "version": args.version,
        "release_root": str(release_root),
        "errors": errors,
    }
    if args.json_report:
        Path(args.json_report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if errors:
        print("Release preflight failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Release preflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
