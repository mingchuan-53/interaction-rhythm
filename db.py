"""SQLite 数据库层"""
import sqlite3
import threading
import random
from collections import Counter
from pathlib import Path
from datetime import datetime, time, timedelta

SCHEMA = """
CREATE TABLE IF NOT EXISTS keystrokes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS mouse_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS app_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL DEFAULT '',
    start TEXT NOT NULL,
    end TEXT
);
CREATE TABLE IF NOT EXISTS app_paths (
    app TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    updated TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS app_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    app TEXT NOT NULL,
    path TEXT NOT NULL DEFAULT '',
    keyboard INTEGER NOT NULL DEFAULT 0,
    mouse INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS insight_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL,
    responses INTEGER NOT NULL DEFAULT 0,
    active_seconds INTEGER NOT NULL DEFAULT 0,
    top_app TEXT NOT NULL DEFAULT '',
    peak_hour INTEGER,
    summary TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_key_ts ON keystrokes(ts);
CREATE INDEX IF NOT EXISTS idx_mouse_ts ON mouse_events(ts);
CREATE INDEX IF NOT EXISTS idx_app_start ON app_usage(start);
CREATE INDEX IF NOT EXISTS idx_app_name ON app_usage(app);
CREATE INDEX IF NOT EXISTS idx_interact_ts ON app_interactions(ts);
CREATE INDEX IF NOT EXISTS idx_interact_app ON app_interactions(app);
CREATE INDEX IF NOT EXISTS idx_insight_generated ON insight_history(generated_at);
"""


class DB:
    def __init__(self, path: Path):
        self._path = path
        self._local = threading.local()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.executescript(SCHEMA)
        self._migrate(conn)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.commit()
        self._local.conn = conn

    def _migrate(self, conn: sqlite3.Connection):
        cols = {row[1] for row in conn.execute("PRAGMA table_info(app_usage)").fetchall()}
        if "path" not in cols:
            conn.execute("ALTER TABLE app_usage ADD COLUMN path TEXT NOT NULL DEFAULT ''")
        path_cols = {row[1] for row in conn.execute("PRAGMA table_info(app_paths)").fetchall()}
        if "updated" not in path_cols:
            conn.execute("ALTER TABLE app_paths ADD COLUMN updated TEXT NOT NULL DEFAULT ''")

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            c = sqlite3.connect(str(self._path), check_same_thread=False)
            c.execute("PRAGMA journal_mode=WAL")
            self._local.conn = c
        return self._local.conn

    def close(self):
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            del self._local.conn

    def checkpoint(self):
        self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self._conn.commit()

    def _remember_app_path(self, app: str, path: str):
        if not app or not path:
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO app_paths(app,path,updated) VALUES(?,?,?)",
            (app, path, datetime.now().isoformat(timespec="seconds")),
        )

    def _add_app_interaction(self, ts: str, app: str, path: str = "", keyboard: int = 0, mouse: int = 0):
        app = (app or "").strip()
        if not app or app == "unknown" or (keyboard <= 0 and mouse <= 0):
            return
        self._conn.execute(
            "INSERT INTO app_interactions(ts,app,path,keyboard,mouse) VALUES(?,?,?,?,?)",
            (ts, app, path or "", max(0, int(keyboard or 0)), max(0, int(mouse or 0))),
        )
        self._remember_app_path(app, path or "")

    def add_keystrokes(self, count: int, app: str = "", path: str = ""):
        ts = datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            "INSERT INTO keystrokes(ts,count) VALUES(?,?)",
            (ts, count),
        )
        self._add_app_interaction(ts, app, path, keyboard=count)
        self._conn.commit()

    def add_mouse_events(self, count: int, app: str = "", path: str = ""):
        ts = datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            "INSERT INTO mouse_events(ts,count) VALUES(?,?)",
            (ts, count),
        )
        self._add_app_interaction(ts, app, path, mouse=count)
        self._conn.commit()

    def add_session(self, app: str, title: str, start: str, end: str, path: str = ""):
        self._conn.execute(
            "INSERT INTO app_usage(app,title,start,end,path) VALUES(?,?,?,?,?)",
            (app, title, start, end, path or ""),
        )
        if app and path:
            self._remember_app_path(app, path)
        self._conn.commit()

    def remember_app_paths(self, paths: dict[str, str]):
        rows = [(app, path) for app, path in (paths or {}).items() if app and path]
        if not rows:
            return
        updated = datetime.now().isoformat(timespec="seconds")
        self._conn.executemany(
            "INSERT OR REPLACE INTO app_paths(app,path,updated) VALUES(?,?,?)",
            [(app, path, updated) for app, path in rows],
        )
        self._conn.commit()

    def backfill_hourly_counts(self):
        """预留：如需从原始记录回填逐小时汇总，可在此实现。"""
        return None

    def _sum_table_today(self, table: str, today: str) -> int:
        row = self._conn.execute(
            f"SELECT COALESCE(SUM(count),0) FROM {table} WHERE ts>=?",
            (today,),
        ).fetchone()
        return int(row[0] or 0)

    def today_stats(self) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().isoformat(timespec="seconds")
        total_keys = self._sum_table_today("keystrokes", today)
        total_mouse = self._sum_table_today("mouse_events", today)

        rows = self._conn.execute(
            "SELECT au.app, "
            "  SUM((julianday(MIN(COALESCE(end, ?), ? || 'T23:59:59')) "
            "     - julianday(MAX(start, ?))) * 86400) AS dur_s, "
            "  MAX(title) AS title, "
            "  COALESCE(NULLIF(MAX(au.path), ''), MAX(ap.path), '') AS path "
            "FROM app_usage au LEFT JOIN app_paths ap ON ap.app=au.app "
            "WHERE start >= ? "
            "GROUP BY au.app ORDER BY dur_s DESC",
            (now, today, today, today),
        ).fetchall()

        apps = []
        total_time = 0.0
        for app, seconds, title, path in rows:
            seconds = seconds if seconds and seconds > 0 else 0
            total_time += seconds
            apps.append({
                "app": app,
                "seconds": round(seconds),
                "title": title or "",
                "path": path or "",
            })

        return {
            "date": today,
            "keystrokes": total_keys,
            "mouse_events": total_mouse,
            "responses": total_keys + total_mouse,
            "total_seconds": round(total_time),
            "apps": apps[:20],
        }

    def _hourly_table(self, table: str, date: str) -> list[int]:
        rows = self._conn.execute(
            f"SELECT substr(ts,12,2) as h, SUM(count) "
            f"FROM {table} WHERE substr(ts,1,10)=? "
            "GROUP BY h ORDER BY h",
            (date,),
        ).fetchall()
        data = [0] * 24
        for h, c in rows:
            data[int(h)] = int(c or 0)
        return data

    def hourly_chart(self, date: str) -> list[int]:
        k = self._hourly_table("keystrokes", date)
        m = self._hourly_table("mouse_events", date)
        return [k[i] + m[i] for i in range(24)]

    def app_chart(self, date: str) -> list:
        now = datetime.now().isoformat(timespec="seconds")
        rows = self._conn.execute(
            "SELECT au.app, "
            "  SUM((julianday(MIN(COALESCE(end, ?), ? || 'T23:59:59')) "
            "     - julianday(MAX(start, ?))) * 86400) AS dur_s, "
            "  COALESCE(NULLIF(MAX(au.path), ''), MAX(ap.path), '') AS path "
            "FROM app_usage au LEFT JOIN app_paths ap ON ap.app=au.app "
            "WHERE substr(start,1,10)=? "
            "GROUP BY au.app ORDER BY dur_s DESC LIMIT 10",
            (now, date, date, date),
        ).fetchall()
        return [{"app": a, "seconds": round(max(s or 0, 0)), "path": p or ""} for a, s, p in rows]

    def daily_summary(self, date: str) -> dict:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(count),0) FROM keystrokes WHERE substr(ts,1,10)=?",
            (date,),
        ).fetchone()
        return {"date": date, "keystrokes": row[0]}

    def app_detail(self, app: str, date: str) -> dict:
        rows = self._conn.execute(
            "SELECT start, end, title FROM app_usage "
            "WHERE app=? AND substr(start,1,10)=? ORDER BY start",
            (app, date),
        ).fetchall()
        sessions = []
        for s, e, t in rows:
            start_dt = datetime.fromisoformat(s)
            end_dt = datetime.fromisoformat(e) if e else datetime.now()
            dur = (end_dt - start_dt).total_seconds()
            sessions.append({
                "start": s[11:19],
                "end": (e or datetime.now().isoformat())[11:19],
                "duration": round(dur),
                "title": t or "",
            })
        total = sum(s["duration"] for s in sessions)
        return {"app": app, "date": date, "sessions": sessions, "total_seconds": total}

    def _dt(self, value: str | None, fallback: datetime) -> datetime:
        if not value:
            return fallback
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return fallback

    def _range(self, days: int) -> tuple[datetime, datetime, list[str]]:
        days = max(1, min(int(days or 1), 365))
        now = datetime.now()
        start_day = (now - timedelta(days=days - 1)).date()
        start = datetime.combine(start_day, time.min)
        dates = [(start_day + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
        return start, now, dates

    def app_analysis(self, app: str, days: int = 7) -> dict:
        app = (app or "").strip()
        start, end, dates = self._range(days)
        now_iso = end.isoformat(timespec="seconds")
        start_iso = start.isoformat(timespec="seconds")
        end_iso = end.isoformat(timespec="seconds")
        path_row = self._conn.execute("SELECT path FROM app_paths WHERE app=?", (app,)).fetchone()
        known_path = path_row[0] if path_row else ""

        rows = self._conn.execute(
            "SELECT start, COALESCE(end, ?), title, path "
            "FROM app_usage "
            "WHERE app=? AND start < ? AND COALESCE(end, ?) > ? "
            "ORDER BY start",
            (now_iso, app, end_iso, now_iso, start_iso),
        ).fetchall()

        daily = {d: 0.0 for d in dates}
        heatmap = {d: [0.0] * 24 for d in dates}
        hourly = [0.0] * 24
        sessions = []
        titles: dict[str, float] = {}
        path = known_path

        for raw_start, raw_end, title, row_path in rows:
            row_start = self._dt(raw_start, start)
            row_end = self._dt(raw_end, end)
            clipped_start = max(row_start, start)
            clipped_end = min(row_end, end)
            if clipped_end <= clipped_start:
                continue
            if row_path:
                path = row_path

            duration = (clipped_end - clipped_start).total_seconds()
            sessions.append({
                "date": clipped_start.strftime("%Y-%m-%d"),
                "start": clipped_start.isoformat(timespec="seconds"),
                "end": clipped_end.isoformat(timespec="seconds"),
                "duration": round(duration),
                "title": title or "",
                "path": row_path or known_path or "",
            })
            if title:
                titles[title] = titles.get(title, 0.0) + duration

            cursor = clipped_start
            while cursor < clipped_end:
                next_hour = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                segment_end = min(next_hour, clipped_end)
                seconds = (segment_end - cursor).total_seconds()
                d = cursor.strftime("%Y-%m-%d")
                h = cursor.hour
                if d in daily:
                    daily[d] += seconds
                    heatmap[d][h] += seconds
                    hourly[h] += seconds
                cursor = segment_end

        total_seconds = round(sum(daily.values()))
        session_count = len(sessions)
        longest = max((s["duration"] for s in sessions), default=0)
        peak_hour = max(range(24), key=lambda h: hourly[h]) if total_seconds else None
        top_titles = [
            {"title": title, "seconds": round(seconds)}
            for title, seconds in sorted(titles.items(), key=lambda item: item[1], reverse=True)[:5]
        ]
        interaction_rows = self._conn.execute(
            "SELECT substr(ts,1,10) AS d, CAST(substr(ts,12,2) AS INTEGER) AS h, "
            "  SUM(keyboard), SUM(mouse) "
            "FROM app_interactions "
            "WHERE app=? AND ts>=? AND ts<=? "
            "GROUP BY d, h ORDER BY d, h",
            (app, start_iso, end_iso),
        ).fetchall()
        interaction_daily = {d: {"keyboard": 0, "mouse": 0} for d in dates}
        interaction_heatmap = {d: [{"keyboard": 0, "mouse": 0} for _ in range(24)] for d in dates}
        interaction_hourly = [{"keyboard": 0, "mouse": 0} for _ in range(24)]
        keyboard_total = 0
        mouse_total = 0
        for d, h, keys, clicks in interaction_rows:
            if d not in interaction_daily or h is None or h < 0 or h > 23:
                continue
            keys = int(keys or 0)
            clicks = int(clicks or 0)
            keyboard_total += keys
            mouse_total += clicks
            interaction_daily[d]["keyboard"] += keys
            interaction_daily[d]["mouse"] += clicks
            interaction_heatmap[d][h]["keyboard"] += keys
            interaction_heatmap[d][h]["mouse"] += clicks
            interaction_hourly[h]["keyboard"] += keys
            interaction_hourly[h]["mouse"] += clicks
        response_total = keyboard_total + mouse_total

        return {
            "app": app,
            "path": path or "",
            "days": len(dates),
            "date_start": dates[0] if dates else "",
            "date_end": dates[-1] if dates else "",
            "total_seconds": total_seconds,
            "today_seconds": round(daily.get(datetime.now().strftime("%Y-%m-%d"), 0)),
            "session_count": session_count,
            "average_session_seconds": round(total_seconds / session_count) if session_count else 0,
            "longest_session_seconds": longest,
            "active_hours": sum(1 for value in hourly if value > 0),
            "peak_hour": peak_hour,
            "keyboard": keyboard_total,
            "mouse": mouse_total,
            "responses": response_total,
            "response_density": round(response_total / max(1, total_seconds / 60), 2) if total_seconds else 0,
            "interaction_source": "direct" if response_total else "duration_only",
            "first_seen": sessions[0]["start"] if sessions else "",
            "last_seen": sessions[-1]["end"] if sessions else "",
            "daily": [{"date": d, "seconds": round(daily[d])} for d in dates],
            "hourly": [round(v) for v in hourly],
            "heatmap": [{"date": d, "hourly": [round(v) for v in heatmap[d]]} for d in dates],
            "interaction_daily": [
                {
                    "date": d,
                    "keyboard": interaction_daily[d]["keyboard"],
                    "mouse": interaction_daily[d]["mouse"],
                    "responses": interaction_daily[d]["keyboard"] + interaction_daily[d]["mouse"],
                }
                for d in dates
            ],
            "interaction_hourly": [
                {
                    "hour": h,
                    "keyboard": row["keyboard"],
                    "mouse": row["mouse"],
                    "responses": row["keyboard"] + row["mouse"],
                }
                for h, row in enumerate(interaction_hourly)
            ],
            "interaction_heatmap": [
                {
                    "date": d,
                    "hourly": [
                        {
                            "keyboard": cell["keyboard"],
                            "mouse": cell["mouse"],
                            "responses": cell["keyboard"] + cell["mouse"],
                        }
                        for cell in interaction_heatmap[d]
                    ],
                }
                for d in dates
            ],
            "sessions": list(reversed(sessions[-30:])),
            "top_titles": top_titles,
        }

    def export_data(self, days: int = 30) -> dict:
        start, end, dates = self._range(days)
        now_iso = end.isoformat(timespec="seconds")
        start_iso = start.isoformat(timespec="seconds")
        end_iso = end.isoformat(timespec="seconds")
        heatmap = self.heatmap_data(len(dates), False)
        daily = []
        for row in heatmap:
            keyboard = sum(row.get("keyboard_hourly", []))
            mouse = sum(row.get("mouse_hourly", []))
            daily.append({
                "date": row["date"],
                "keyboard": keyboard,
                "mouse": mouse,
                "responses": keyboard + mouse,
            })

        app_rows = self._conn.execute(
            "SELECT au.app, "
            "  SUM((julianday(MIN(COALESCE(end, ?), ?)) - julianday(MAX(start, ?))) * 86400) AS dur_s, "
            "  COALESCE(NULLIF(MAX(au.path), ''), MAX(ap.path), '') AS path "
            "FROM app_usage au LEFT JOIN app_paths ap ON ap.app=au.app "
            "WHERE start < ? AND COALESCE(end, ?) > ? "
            "GROUP BY au.app ORDER BY dur_s DESC",
            (now_iso, end_iso, start_iso, end_iso, now_iso, start_iso),
        ).fetchall()
        applications = [
            {"app": app, "seconds": round(max(seconds or 0, 0)), "path": path or ""}
            for app, seconds, path in app_rows
        ]

        session_rows = self._conn.execute(
            "SELECT app, title, path, start, COALESCE(end, ?) "
            "FROM app_usage "
            "WHERE start < ? AND COALESCE(end, ?) > ? "
            "ORDER BY start DESC",
            (now_iso, end_iso, now_iso, start_iso),
        ).fetchall()
        sessions = []
        for app, title, path, raw_start, raw_end in session_rows:
            row_start = self._dt(raw_start, start)
            row_end = self._dt(raw_end, end)
            clipped_start = max(row_start, start)
            clipped_end = min(row_end, end)
            if clipped_end <= clipped_start:
                continue
            sessions.append({
                "app": app,
                "title": title or "",
                "path": path or "",
                "start": clipped_start.isoformat(timespec="seconds"),
                "end": clipped_end.isoformat(timespec="seconds"),
                "seconds": round((clipped_end - clipped_start).total_seconds()),
            })

        interaction_rows = self._conn.execute(
            "SELECT app, path, ts, keyboard, mouse "
            "FROM app_interactions "
            "WHERE ts>=? AND ts<=? "
            "ORDER BY ts DESC",
            (start_iso, end_iso),
        ).fetchall()
        interactions = [
            {
                "app": app,
                "path": path or "",
                "ts": ts,
                "keyboard": int(keyboard or 0),
                "mouse": int(mouse or 0),
                "responses": int(keyboard or 0) + int(mouse or 0),
            }
            for app, path, ts, keyboard, mouse in interaction_rows
        ]

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "range": {"start": dates[0], "end": dates[-1], "days": len(dates)},
            "today": self.today_stats(),
            "daily": daily,
            "heatmap": heatmap,
            "applications": applications,
            "sessions": sessions,
            "interactions": interactions,
        }

    def _previous_insight(self) -> dict | None:
        row = self._conn.execute(
            "SELECT generated_at, responses, active_seconds, top_app, peak_hour, summary "
            "FROM insight_history ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        generated_at, responses, active_seconds, top_app, peak_hour, summary = row
        return {
            "generated_at": generated_at,
            "responses": responses,
            "active_seconds": active_seconds,
            "top_app": top_app,
            "peak_hour": peak_hour,
            "summary": summary,
        }

    def _save_insight(self, result: dict):
        summary = "；".join((result.get("findings") or result.get("judgments") or [])[:2])
        top_app = ((result.get("summary") or {}).get("top_app") or {}).get("app", "")
        self._conn.execute(
            "INSERT INTO insight_history(generated_at,responses,active_seconds,top_app,peak_hour,summary) "
            "VALUES(?,?,?,?,?,?)",
            (
                result.get("generated_at", datetime.now().isoformat(timespec="seconds")),
                int((result.get("summary") or {}).get("responses") or 0),
                int((result.get("summary") or {}).get("average_daily_seconds") or 0),
                top_app or "",
                (result.get("summary") or {}).get("peak_hour"),
                summary,
            ),
        )
        self._conn.execute(
            "DELETE FROM insight_history WHERE id NOT IN "
            "(SELECT id FROM insight_history ORDER BY generated_at DESC LIMIT 2)"
        )
        self._conn.commit()

    def _comparison_text(self, previous: dict | None, responses: int, avg_seconds: int, top_app: dict, peak_hour):
        if not previous:
            return "这是第一次生成分析，还没有上次结果可以比较。"
        prev_responses = int(previous.get("responses") or 0)
        prev_seconds = int(previous.get("active_seconds") or 0)
        resp_delta = responses - prev_responses
        sec_delta = avg_seconds - prev_seconds
        parts = []
        if abs(resp_delta) < max(50, prev_responses * 0.05):
            parts.append("响应次数变化不大")
        elif resp_delta > 0:
            parts.append(f"响应次数多了约 {resp_delta} 次")
        else:
            parts.append(f"响应次数少了约 {abs(resp_delta)} 次")
        if abs(sec_delta) < 10 * 60:
            parts.append("日均活跃时长基本持平")
        elif sec_delta > 0:
            parts.append(f"日均活跃时长增加约 {round(sec_delta / 60)} 分钟")
        else:
            parts.append(f"日均活跃时长减少约 {round(abs(sec_delta) / 60)} 分钟")
        prev_app = previous.get("top_app") or ""
        current_app = top_app.get("app") if top_app else ""
        if prev_app and current_app and prev_app != current_app:
            parts.append(f"最集中的应用从 {self._app_display_name(prev_app)} 变成 {self._app_display_name(current_app)}")
        elif current_app:
            parts.append(f"最集中的应用仍然是 {self._app_display_name(current_app)}")
        return "跟上次相比，" + "，".join(parts) + "。"

    def _app_display_name(self, app: str) -> str:
        name = (app or "").strip()
        stem = name[:-4] if name.lower().endswith(".exe") else name
        lower = stem.lower()
        if lower in {"interactionrhythm", "typetracker"} or name == "交互节律":
            return "交互节律"
        aliases = {
            "code": "VS Code",
            "codex": "Codex",
            "chrome": "Chrome",
            "msedge": "Edge",
            "explorer": "文件管理器",
            "wechat": "微信",
            "obsidian": "Obsidian",
            "python": "Python",
            "pythonw": "Python",
        }
        return aliases.get(lower, stem or name)

    def _hour_range_text(self, hour: int) -> str:
        return f"{hour:02d}:00-{(hour + 1) % 24:02d}:00"

    def _apps_during_hour(self, sessions: list[dict], date: str, hour: int, limit: int = 2) -> list[str]:
        start = datetime.fromisoformat(f"{date}T{hour:02d}:00:00")
        end = start + timedelta(hours=1)
        app_seconds: dict[str, float] = {}
        for session in sessions:
            try:
                raw_start = datetime.fromisoformat(session["start"])
                raw_end = datetime.fromisoformat(session["end"])
            except (KeyError, ValueError, TypeError):
                continue
            overlap = (min(end, raw_end) - max(start, raw_start)).total_seconds()
            if overlap <= 0:
                continue
            app = self._app_display_name(session.get("app") or "")
            if app:
                app_seconds[app] = app_seconds.get(app, 0) + overlap
        return [
            app for app, _seconds in sorted(app_seconds.items(), key=lambda item: item[1], reverse=True)[:limit]
        ]

    def _recall_lines(self, heatmap: list[dict], sessions: list[dict], limit: int = 3) -> list[str]:
        slots = []
        for day in heatmap:
            date = day.get("date", "")
            keyboard = day.get("keyboard_hourly", [])
            mouse = day.get("mouse_hourly", [])
            for hour in range(24):
                k = int(keyboard[hour]) if hour < len(keyboard) else 0
                m = int(mouse[hour]) if hour < len(mouse) else 0
                total = k + m
                if total > 0:
                    slots.append((total, date, hour, k, m))
        slots.sort(reverse=True)
        lines = []
        for total, date, hour, keyboard, mouse in slots[:limit]:
            apps = self._apps_during_hour(sessions, date, hour)
            app_text = "，主要应用：" + "、".join(apps) if apps else ""
            if keyboard > mouse * 1.5:
                action = "更像连续输入。"
            elif mouse > keyboard * 1.5:
                action = "更像浏览、筛选或整理。"
            else:
                action = "更像边输入边浏览。"
            lines.append(
                f"{date} {self._hour_range_text(hour)} 响应集中{app_text}，{action}"
            )
        return lines

    def _fresh_suggestions(self, base: list[str], limit: int = 4) -> list[str]:
        pool = list(dict.fromkeys(base))
        random.shuffle(pool)
        return pool[:limit]

    def _interaction_totals(self, start_iso: str, end_iso: str) -> dict[str, dict]:
        rows = self._conn.execute(
            "SELECT ai.app, SUM(ai.keyboard), SUM(ai.mouse), "
            "  COALESCE(NULLIF(MAX(ai.path), ''), MAX(ap.path), '') AS path "
            "FROM app_interactions ai LEFT JOIN app_paths ap ON ap.app=ai.app "
            "WHERE ai.ts>=? AND ai.ts<=? "
            "GROUP BY ai.app",
            (start_iso, end_iso),
        ).fetchall()
        totals = {}
        for app, keyboard, mouse, path in rows:
            keyboard = int(keyboard or 0)
            mouse = int(mouse or 0)
            totals[app] = {
                "app": app,
                "path": path or "",
                "keyboard": keyboard,
                "mouse": mouse,
                "responses": keyboard + mouse,
            }
        return totals

    def _app_strength_findings(
        self,
        apps: list[dict],
        sessions: list[dict],
        interactions: dict[str, dict],
        total_seconds: int,
    ) -> tuple[list[str], list[str], list[dict]]:
        session_counts = Counter(session.get("app") or "" for session in sessions)
        total_responses = sum(row.get("responses", 0) for row in interactions.values())
        rows = []
        known_apps = {app.get("app") for app in apps if app.get("app")}
        ordered_names = [app.get("app") for app in apps if app.get("app")]
        for app in sorted(set(interactions) - known_apps):
            ordered_names.append(app)

        for name in ordered_names:
            duration = next((int(app.get("seconds") or 0) for app in apps if app.get("app") == name), 0)
            row = interactions.get(name, {})
            keyboard = int(row.get("keyboard") or 0)
            mouse = int(row.get("mouse") or 0)
            responses = keyboard + mouse
            minutes = max(1, duration / 60) if duration else 1
            duration_share = duration / total_seconds if total_seconds else 0
            response_share = responses / total_responses if total_responses else 0
            density = responses / minutes if duration else 0
            rows.append({
                "app": name,
                "name": self._app_display_name(name),
                "seconds": duration,
                "sessions": int(session_counts.get(name, 0)),
                "keyboard": keyboard,
                "mouse": mouse,
                "responses": responses,
                "duration_share": round(duration_share, 4),
                "response_share": round(response_share, 4),
                "response_density": round(density, 2),
            })

        candidates = []
        advice = []
        for item in rows:
            name = item["name"]
            seconds = item["seconds"]
            sessions_count = item["sessions"]
            keyboard = item["keyboard"]
            mouse = item["mouse"]
            responses = item["responses"]
            duration_share = item["duration_share"]
            response_share = item["response_share"]
            density = item["response_density"]

            if responses and response_share - duration_share >= 0.12:
                candidates.append((
                    90 + int((response_share - duration_share) * 100),
                    f"{name} 的交互占比高于时长占比，更像今天需要主动操作的应用。",
                ))
                advice.append(f"把 {name} 相关任务集中到同一段时间处理，减少来回切换。")
            if seconds >= 20 * 60 and duration_share - response_share >= 0.15:
                candidates.append((
                    82 + int((duration_share - response_share) * 100),
                    f"{name} 停留较长，但键鼠响应不高，更像阅读、观看、等待或资料浏览。",
                ))
                advice.append(f"如果 {name} 是阅读或观看场景，可以给自己设一个明确的收尾点。")
            if sessions_count >= 6 and seconds < 90 * 60:
                candidates.append((
                    78 + sessions_count,
                    f"{name} 回返次数偏多，可能经常插入到其它任务之间。",
                ))
                advice.append(f"把 {name} 的查看频率收成几次固定检查，专注时间会更完整。")
            if keyboard >= max(300, mouse * 1.6):
                candidates.append((
                    75 + min(20, keyboard // 300),
                    f"{name} 的键盘响应更突出，更像输入、搜索、整理或开发现场。",
                ))
                advice.append("键盘响应连续变高时，手指和前臂需要短暂停顿。")
            if mouse >= max(300, keyboard * 1.6):
                candidates.append((
                    75 + min(20, mouse // 300),
                    f"{name} 的鼠标响应更突出，更像浏览、筛选、调整或文件整理。",
                ))
                advice.append("鼠标响应连续变高时，检查手腕位置，能用快捷键就少拖动。")
            if responses >= 600 and density >= 80:
                candidates.append((
                    72 + min(20, int(density // 20)),
                    f"{name} 单位时间响应密度偏高，说明这段使用不只是挂着，而是在密集操作。",
                ))
                advice.append(f"{name} 高密度使用后，下一段最好安排低刺激任务或短休息。")

        if rows and not candidates:
            lead = max(rows, key=lambda item: (item["responses"], item["seconds"]))
            if lead["responses"]:
                candidates.append((60, f"{lead['name']} 是目前交互最明显的应用，可以继续观察它在不同时间段的变化。"))
            elif lead["seconds"]:
                candidates.append((55, f"{lead['name']} 是目前停留最明显的应用，新版会继续积累它的键鼠强度。"))

        candidates.sort(key=lambda item: item[0], reverse=True)
        findings = []
        for _score, text in candidates:
            if text not in findings:
                findings.append(text)
            if len(findings) >= 3:
                break

        rows.sort(key=lambda item: (item["responses"], item["seconds"]), reverse=True)
        return findings, advice, rows[:6]

    def insights(self, days: int = 7) -> dict:
        data = self.export_data(days)
        daily = data["daily"]
        apps = data["applications"]
        heatmap = data["heatmap"]
        sessions = data["sessions"]
        keyboard = sum(row["keyboard"] for row in daily)
        mouse = sum(row["mouse"] for row in daily)
        responses = keyboard + mouse
        total_seconds = sum(app["seconds"] for app in apps)
        avg_responses = round(responses / max(1, len(daily)))
        avg_seconds = round(total_seconds / max(1, len(daily)))
        hourly = [0] * 24
        for day in heatmap:
            for i, value in enumerate(day.get("hourly", [])):
                hourly[i] += value
        peak_hour = max(range(24), key=lambda h: hourly[h]) if responses else None
        peak_day = max(daily, key=lambda row: row["responses"]) if daily else {"date": "", "responses": 0}
        top_app = apps[0] if apps else {"app": "", "seconds": 0}
        top_share = (top_app["seconds"] / total_seconds) if total_seconds else 0
        previous = self._previous_insight()
        recall = self._recall_lines(heatmap, sessions)
        start, end, _dates = self._range(days)
        interactions = self._interaction_totals(start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"))
        app_findings, app_suggestions, app_strength = self._app_strength_findings(
            apps, sessions, interactions, total_seconds
        )

        if responses == 0 and total_seconds == 0:
            conclusion = "现在还没有足够的记录。节律助手只能确认记录通道已经准备好。"
            findings = [
                "最近还没有记录到键盘、鼠标或应用使用数据。",
                "先正常使用一段时间，再回来查看节律线索。",
            ]
            suggestions = self._fresh_suggestions([
                "先正常使用半天，让热力图积累出时间块。",
                "如果一直在使用电脑却没有记录，检查后台是否仍在运行。",
                "第一次观察先看记录是否连续，不急着判断习惯。",
                "等应用排行出现稳定名称后，再看具体活动线索。",
                "如果开机自启已打开，明天的数据会更完整。",
            ])
        elif responses < 500 or total_seconds < 20 * 60:
            conclusion = "当前数据偏少，更适合作为记录通道检查，不适合直接判断稳定习惯。"
            findings = [
                "当前数据只能看出大概方向，还不能当成稳定习惯。",
                "等记录覆盖几个完整工作时段后，高峰时间和应用集中度会更准。",
            ]
            if peak_hour is not None:
                findings.append(f"目前少量记录里，响应主要出现在 {peak_hour:02d}:00 左右。")
            for text in app_findings:
                if len(findings) >= 3:
                    break
                if text not in findings:
                    findings.append(text)
            suggestions = self._fresh_suggestions([
                "先积累半天到一天的数据，再看趋势会更稳。",
                "现在可以先确认记录是否连续、应用名称是否正确。",
                "如果某个小时突然变深，可以回忆那一段是不是有集中任务。",
                "数据还少时，健康建议先按轻量休息执行即可。",
                "连续输入超过一小时后，给手腕和眼睛留 3 分钟缓冲。",
            ])
        else:
            if keyboard > mouse * 1.5:
                rhythm_type = "输入型"
            elif mouse > keyboard * 1.5:
                rhythm_type = "浏览和操作型"
            else:
                rhythm_type = "混合型"
            top_app_name = self._app_display_name(top_app["app"])
            if top_app["app"] and top_share >= 0.5:
                app_phrase = f"主要集中在 {top_app_name}"
            elif top_app["app"] and top_share >= 0.25:
                app_phrase = f"有一个较明显的主应用：{top_app_name}"
            else:
                app_phrase = "应用分布比较分散"
            hour_phrase = f"高峰多在 {peak_hour:02d}:00 左右" if peak_hour is not None else "高峰时间还不明显"
            conclusion = f"最近 {data['range']['days']} 天呈现{rhythm_type}节律，{app_phrase}，{hour_phrase}。"
            context_findings = []
            if avg_seconds >= 8 * 3600:
                context_findings.append("最近每天盯屏幕的时间偏长，身体恢复的空间不够。")
            elif avg_seconds >= 5 * 3600:
                context_findings.append("最近每天使用电脑的时间不低，最好把休息固定下来。")
            else:
                context_findings.append("最近总时长还可以，重点看有没有集中在某一两个小时里。")

            if peak_hour is not None:
                if peak_hour >= 22 or peak_hour <= 5:
                    context_findings.append(f"高峰在 {peak_hour:02d}:00 左右，说明夜间使用比较明显。")
                else:
                    context_findings.append(f"高峰在 {peak_hour:02d}:00 左右，这段时间更适合放重要工作。")
            findings = []
            for text in app_findings:
                if len(findings) >= 3:
                    break
                if text not in findings:
                    findings.append(text)
            for text in context_findings:
                if len(findings) >= 3:
                    break
                if text not in findings:
                    findings.append(text)

            suggestion_pool = [
                "每用电脑 45-60 分钟，离开屏幕 3-5 分钟，看远处，转动肩颈。",
                "把需要专注的事情放到高峰小时，零碎切换的事情放到低峰小时。",
                "热力图连续变深时，下一小时主动安排一次短休息。",
                "当天响应很多但应用分散时，先收束正在处理的应用，再继续做事。",
                "把重复点击多的操作改成快捷键，减少手腕来回移动。",
                "如果某个应用占比很高，结束前写一句“刚才完成了什么”，方便复盘。",
                "键盘响应持续偏高时，手指、前臂和肩膀都需要短暂停顿。",
                "鼠标响应持续偏高时，检查鼠标位置和手腕支撑是否舒服。",
            ]
            if avg_seconds >= 5 * 3600:
                suggestion_pool.append("每天留一段 20 分钟以上的不看屏幕时间，不要把休息切得太碎。")
            if peak_hour is not None and (peak_hour >= 22 or peak_hour <= 5):
                suggestion_pool.append("如果晚上还在高强度输入，睡前 30 分钟尽量收尾。")
            if mouse > keyboard * 1.5 and mouse > 1000:
                suggestion_pool.append("鼠标用得多时，把最常用的动作换成快捷键，少让手腕来回移动。")
            suggestions = self._fresh_suggestions(app_suggestions + suggestion_pool, 4)

        comparison = self._comparison_text(previous, responses, avg_seconds, top_app, peak_hour)
        if previous and comparison and responses >= 500 and total_seconds >= 20 * 60:
            ordered = []
            if findings:
                ordered.append(findings[0])
            ordered.append(comparison)
            ordered.extend(findings[1:])
            findings = list(dict.fromkeys(ordered))[:3]
        result = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "assistant": "节律助手",
            "model": "本地规则分析",
            "model_note": "节律助手当前使用本地规则分析，没有调用外部 AI 模型，记录不会离开本机。",
            "interface": "GET /api/insights?days=7",
            "prompt_design": [
                "先给结论，再列证据和建议。",
                "用键盘响应、鼠标响应、小时高峰、应用集中度和前台应用时间段帮助用户回忆也许做了什么。",
                "不评价人格，不给效率打分，不假装知道用户真实意图。",
                "使用“也许是”等保守表达，保持严肃、克制和可校正。",
            ],
            "days": data["range"]["days"],
            "conclusion": conclusion,
            "summary": {
                "keyboard": keyboard,
                "mouse": mouse,
                "responses": responses,
                "average_daily_responses": avg_responses,
                "average_daily_seconds": avg_seconds,
                "peak_day": peak_day,
                "peak_hour": peak_hour,
                "top_app": top_app,
            },
            "recall": recall,
            "findings": findings[:3],
            "judgments": findings[:3],
            "comparison": comparison,
            "suggestions": suggestions[:4],
            "app_strength": app_strength,
            "charts": {
                "daily": daily,
                "hourly": hourly,
                "apps": apps[:5],
            },
        }
        self._save_insight(result)
        return result

    def date_range(self) -> tuple:
        r1 = self._conn.execute("SELECT MIN(substr(ts,1,10)) FROM keystrokes").fetchone()
        r2 = self._conn.execute("SELECT MAX(substr(ts,1,10)) FROM keystrokes").fetchone()
        return (r1[0], r2[0]) if r1 and r2 else (None, None)

    def daily_keystrokes(self, days: int = 7) -> list:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = self._conn.execute(
            "SELECT substr(ts,1,10) as d, SUM(count) "
            "FROM keystrokes WHERE d >= ? "
            "GROUP BY d ORDER BY d",
            (cutoff,),
        ).fetchall()
        return [{"date": d, "count": c} for d, c in rows]

    def heatmap_data(self, days: int = 7, tomorrow: bool = False) -> list:
        actual_days = max(1, days)
        end_offset = 1 if tomorrow else 0
        start_offset = actual_days - 1 - end_offset
        cutoff = (datetime.now() - timedelta(days=start_offset)).strftime("%Y-%m-%d")

        def _by_day(table):
            rows = self._conn.execute(
                f"SELECT substr(ts,1,10) as d, CAST(substr(ts,12,2) AS INTEGER) as h, SUM(count) "
                f"FROM {table} WHERE substr(ts,1,10) >= ? "
                "GROUP BY d, h ORDER BY d, h",
                (cutoff,),
            ).fetchall()
            out = {}
            for d, h, c in rows:
                out.setdefault(d, [0] * 24)[h] = int(c or 0)
            return out

        keyboard_by_day = _by_day("keystrokes")
        mouse_by_day = _by_day("mouse_events")
        today = datetime.now().strftime("%Y-%m-%d")
        result = []
        for i in range(actual_days):
            offset = start_offset - i
            d = (datetime.now() - timedelta(days=offset)).strftime("%Y-%m-%d")
            keyboard_hourly = keyboard_by_day.get(d, [0] * 24)
            mouse_hourly = mouse_by_day.get(d, [0] * 24)
            hourly = [keyboard_hourly[h] + mouse_hourly[h] for h in range(24)]
            result.append({
                "date": d,
                "hourly": hourly,
                "keyboard_hourly": keyboard_hourly,
                "mouse_hourly": mouse_hourly,
                "isToday": d == today,
            })
        return result

    def cleanup(self, days: int, hourly_days: int | None = None):
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        self._conn.execute("DELETE FROM keystrokes WHERE ts < ?", (cutoff,))
        self._conn.execute("DELETE FROM mouse_events WHERE ts < ?", (cutoff,))
        self._conn.execute("DELETE FROM app_usage WHERE start < ?", (cutoff,))
        self._conn.execute("DELETE FROM app_interactions WHERE ts < ?", (cutoff,))
        if hourly_days and hourly_days > days:
            hourly_cutoff = (datetime.now() - timedelta(days=hourly_days)).strftime("%Y-%m-%d")
            self._conn.execute("DELETE FROM keystrokes WHERE substr(ts,1,10) < ?", (hourly_cutoff,))
            self._conn.execute("DELETE FROM mouse_events WHERE substr(ts,1,10) < ?", (hourly_cutoff,))
        self._conn.commit()
