"""内建 HTTP 服务器 + REST API"""
import csv
import io
import json
import sys
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from config import PORT

if getattr(sys, 'frozen', False):
    STATIC_DIR = Path(sys._MEIPASS) / "static"
else:
    STATIC_DIR = Path(__file__).parent / "static"


def _safe_int(value: str, default: int, lo: int = 1, hi: int = 365) -> int:
    """安全地将查询参数转为整数，越界或非法值回退到 default。"""
    try:
        return max(lo, min(int(value), hi))
    except (ValueError, TypeError):
        return default


class Handler(SimpleHTTPRequestHandler):
    db = None
    shutdown_callback = None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = {k: v[-1] for k, v in parse_qs(parsed.query).items()}

        if path == "/api/today":
            self._json(Handler.db.today_stats())
        elif path == "/api/day":
            d = params.get("date", "")
            from datetime import datetime
            d = d or datetime.now().strftime("%Y-%m-%d")
            self._json(Handler.db.day_stats(d))
        elif path == "/api/heatmap":
            days = _safe_int(params.get("days", "7"), 7)
            tomorrow = params.get("tomorrow", "0") == "1"
            self._json({"days": days, "data": Handler.db.heatmap_data(days, tomorrow, params.get("end", ""))})
        elif path == "/api/month-heatmap":
            self._json(Handler.db.month_heatmap(params.get("month", "")))
        elif path == "/api/year-heatmap":
            self._json(Handler.db.year_heatmap(params.get("year", "")))
        elif path == "/api/icon":
            from icons import icon_bytes
            raw_path = unquote(params.get("path", ""))
            # 安全检查：只允许绝对路径，拒绝路径穿越
            icon_path = Path(raw_path)
            if not raw_path or ".." in raw_path or len(raw_path) > 500 or not icon_path.is_absolute():
                self.send_error(400)
                return
            data = icon_bytes(raw_path)
            if not data:
                self.send_response(404)
                self.send_header("Cache-Control", "public, max-age=900")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/hourly":
            d = params.get("date", "")
            from datetime import datetime
            d = d or datetime.now().strftime("%Y-%m-%d")
            self._json({"date": d, "hourly": Handler.db.hourly_chart(d)})
        elif path == "/api/hour-detail":
            d = params.get("date", "")
            from datetime import datetime
            d = d or datetime.now().strftime("%Y-%m-%d")
            hour = _safe_int(params.get("hour", "0"), 0, 0, 23)
            self._json(Handler.db.hour_detail(d, hour))
        elif path == "/api/apps":
            d = params.get("date", "")
            from datetime import datetime
            d = d or datetime.now().strftime("%Y-%m-%d")
            self._json({"date": d, "apps": Handler.db.app_chart(d)})
        elif path == "/api/app-detail":
            from datetime import datetime
            d = params.get("date", datetime.now().strftime("%Y-%m-%d"))
            a = params.get("app", "")
            self._json(Handler.db.app_detail(a, d))
        elif path == "/api/app-analysis":
            days = _safe_int(params.get("days", "7"), 7)
            self._json(Handler.db.app_analysis(params.get("app", ""), days))
        elif path == "/api/export":
            days = _safe_int(params.get("days", "30"), 30)
            fmt = params.get("format", "json").lower()
            data = Handler.db.export_data(days)
            if fmt == "csv":
                self._download_csv(data)
            else:
                self._download_json(data)
        elif path == "/api/day-replay":
            d = params.get("date", "")
            from datetime import datetime
            d = d or datetime.now().strftime("%Y-%m-%d")
            self._json(Handler.db.day_replay(d))
        elif path == "/api/media-snapshot":
            d = params.get("date", "")
            from datetime import datetime
            d = d or datetime.now().strftime("%Y-%m-%d")
            self._json(Handler.db.media_snapshot(d))
        elif path == "/api/mimo-replay":
            d = params.get("date", "")
            from datetime import datetime
            d = d or datetime.now().strftime("%Y-%m-%d")
            try:
                from mimo_client import mimo_day_replay
                self._json(mimo_day_replay(Handler.db, d))
            except Exception as e:
                self._json({"ok": False, "error": str(e), "fallback": Handler.db.day_replay(d)})
        elif path == "/api/insights":
            days = _safe_int(params.get("days", "7"), 7)
            self._json(Handler.db.insights(days))
        elif path == "/api/daily":
            days = _safe_int(params.get("days", "7"), 7)
            dr = Handler.db.date_range()
            self._json({
                "range": dr,
                "daily": Handler.db.daily_keystrokes(days),
            })
        elif path == "/api/update/check":
            self._handle_update_check()
        elif path == "/api/update/status":
            self._handle_update_status()
        elif path == "/api/settings":
            self._handle_settings()
        else:
            self._serve_static()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/update/install":
            self._handle_update_install()
        elif parsed.path == "/api/settings":
            self._handle_settings_save()
        else:
            self.send_error(404)

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > 1024 * 1024:
            raise ValueError("请求体过大")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _handle_update_check(self):
        try:
            from update_manager import check_update
            self._json(check_update())
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _handle_update_status(self):
        try:
            from update_manager import update_status
            self._json(update_status())
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _handle_update_install(self):
        try:
            from update_manager import install_update_async
            body = self._read_json_body()
            manifest = body.get("manifest") if isinstance(body, dict) else None
            if not isinstance(manifest, dict):
                raise ValueError("缺少更新清单")
            self._json(install_update_async(manifest, Handler.shutdown_callback))
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _handle_settings(self):
        try:
            from settings import get_settings
            self._json({"ok": True, "settings": get_settings()})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _handle_settings_save(self):
        try:
            from settings import save_settings
            body = self._read_json_body()
            self._json({"ok": True, "settings": save_settings(body)})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _download_json(self, data):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        name = f"kouxian-{data['range']['start']}-{data['range']['end']}.json"
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _download_csv(self, data):
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["section", "date", "hour", "app", "title", "path", "keyboard", "mouse", "responses", "seconds"])
        for row in data.get("daily", []):
            writer.writerow(["daily", row["date"], "", "", "", "", row["keyboard"], row["mouse"], row["responses"], ""])
        for day in data.get("heatmap", []):
            keyboard = day.get("keyboard_hourly", [])
            mouse = day.get("mouse_hourly", [])
            total = day.get("hourly", [])
            for hour in range(24):
                writer.writerow([
                    "hourly", day["date"], hour, "", "", "",
                    keyboard[hour] if hour < len(keyboard) else 0,
                    mouse[hour] if hour < len(mouse) else 0,
                    total[hour] if hour < len(total) else 0,
                    "",
                ])
        for app in data.get("applications", []):
            writer.writerow(["application", "", "", app["app"], "", app.get("path", ""), "", "", "", app["seconds"]])
        for item in data.get("interactions", []):
            ts = item.get("ts", "")
            writer.writerow([
                "interaction", ts[:10], ts[11:13], item.get("app", ""), "",
                item.get("path", ""), item.get("keyboard", 0), item.get("mouse", 0),
                item.get("responses", 0), "",
            ])
        for session in data.get("sessions", []):
            writer.writerow([
                "session", session["start"][:10], "", session["app"], session.get("title", ""),
                session.get("path", ""), "", "", "", session["seconds"],
            ])
        body = ("\ufeff" + out.getvalue()).encode("utf-8")
        name = f"kouxian-{data['range']['start']}-{data['range']['end']}.csv"
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self):
        raw = urlparse(self.path).path.lstrip("/") or "index.html"
        if raw == "detail":
            raw = "detail.html"
        # favicon: 返回托盘图标 PNG，避免浏览器 404 噪音
        if raw == "favicon.ico":
            from tray import make_icon
            import io
            buf = io.BytesIO()
            make_icon(32).save(buf, "PNG")
            data = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(data)
            return
        fp = (STATIC_DIR / raw).resolve()
        if not str(fp).startswith(str(STATIC_DIR.resolve())):
            self.send_error(403)
            return
        if fp.is_file():
            # MIME 类型映射
            MIME_TYPES = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css",
                ".js": "application/javascript",
                ".json": "application/json",
                ".webmanifest": "application/manifest+json",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".svg": "image/svg+xml",
                ".ico": "image/x-icon",
                ".woff": "font/woff",
                ".woff2": "font/woff2",
                ".ttf": "font/ttf",
            }
            ct = MIME_TYPES.get(fp.suffix, "application/octet-stream")
            body = fp.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body)))
            
            if fp.suffix in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf"):
                self.send_header("Cache-Control", "public, max-age=86400")
            
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)


class ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True


class StatsServer:
    def __init__(self, db, port: int = PORT, host: str = "127.0.0.1", shutdown_callback=None):
        Handler.db = db
        Handler.shutdown_callback = shutdown_callback
        self._httpd = ReusableHTTPServer((host, port), Handler)
        self._port = port

    def start(self):
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def stop(self):
        try:
            self._httpd.shutdown()
        finally:
            self._httpd.server_close()
