"""SQLite 数据库层"""
import sqlite3
import threading
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

    def add_keystrokes(self, count: int):
        self._conn.execute(
            "INSERT INTO keystrokes(ts,count) VALUES(?,?)",
            (datetime.now().isoformat(timespec="seconds"), count),
        )
        self._conn.commit()

    def add_mouse_events(self, count: int):
        self._conn.execute(
            "INSERT INTO mouse_events(ts,count) VALUES(?,?)",
            (datetime.now().isoformat(timespec="seconds"), count),
        )
        self._conn.commit()

    def add_session(self, app: str, title: str, start: str, end: str, path: str = ""):
        self._conn.execute(
            "INSERT INTO app_usage(app,title,start,end,path) VALUES(?,?,?,?,?)",
            (app, title, start, end, path or ""),
        )
        if app and path:
            self._conn.execute(
                "INSERT OR REPLACE INTO app_paths(app,path,updated) VALUES(?,?,?)",
                (app, path, datetime.now().isoformat(timespec="seconds")),
            )
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
            "first_seen": sessions[0]["start"] if sessions else "",
            "last_seen": sessions[-1]["end"] if sessions else "",
            "daily": [{"date": d, "seconds": round(daily[d])} for d in dates],
            "hourly": [round(v) for v in hourly],
            "heatmap": [{"date": d, "hourly": [round(v) for v in heatmap[d]]} for d in dates],
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

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "range": {"start": dates[0], "end": dates[-1], "days": len(dates)},
            "today": self.today_stats(),
            "daily": daily,
            "heatmap": heatmap,
            "applications": applications,
            "sessions": sessions,
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
        summary = "；".join((result.get("judgments") or [])[:2])
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
        if stem.lower() in {"interactionrhythm", "typetracker"} or name == "交互节律":
            return "交互节律"
        return name

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
            app_text = "，前台应用主要是 " + "、".join(apps) if apps else ""
            if keyboard > mouse * 1.5:
                action = "也许是在写作、编码、整理笔记或进行较连续的输入。"
            elif mouse > keyboard * 1.5:
                action = "也许是在浏览资料、筛选页面、整理文件或处理零散操作。"
            else:
                action = "也许是在输入和浏览之间来回推进。"
            lines.append(
                f"{date} {self._hour_range_text(hour)} 响应较集中：键盘 {keyboard} 次，鼠标 {mouse} 次{app_text}，{action}"
            )
        return lines

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

        if responses == 0 and total_seconds == 0:
            conclusion = "结论：现在还没有足够的记录。节律助手只能确认记录通道已经准备好，暂时不能判断使用节律。"
            judgments = [
                "最近还没有记录到键盘、鼠标或应用使用数据。",
                "现在只能确认记录通道已经准备好，暂时不能判断使用习惯。",
            ]
            suggestions = [
                "先正常使用一段时间，再打开分析会更有意义。",
                "如果你明明一直在使用电脑，检查一下应用是否在后台运行。",
            ]
        elif responses < 500 or total_seconds < 20 * 60:
            conclusion = "结论：当前数据偏少，也许只能作为记录是否正常的检查，不适合直接判断稳定习惯。"
            judgments = [
                "当前数据还偏少，只能看出一个大概方向，不能当成稳定习惯。",
                "等记录覆盖几个完整工作时段后，高峰时间和应用集中度会更准。",
            ]
            if peak_hour is not None:
                judgments.append(f"目前少量记录里，响应主要出现在 {peak_hour:02d}:00 左右。")
            suggestions = [
                "先积累半天到一天的数据，再看分析结论。",
                "现在可以先用它确认记录是否连续、应用名称是否正确。",
            ]
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
            conclusion = f"结论：最近 {data['range']['days']} 天呈现{rhythm_type}节律，{app_phrase}，{hour_phrase}。这些数据不能证明产出质量，但能帮助回忆电脑前的工作形态。"
            judgments = []
            if avg_seconds >= 8 * 3600:
                judgments.append("最近每天盯屏幕的时间偏长，身体恢复的空间不够。")
            elif avg_seconds >= 5 * 3600:
                judgments.append("最近每天使用电脑的时间不低，最好把休息固定下来。")
            else:
                judgments.append("最近总时长还可以，重点看有没有集中在某一两个小时里。")

            if peak_hour is not None:
                if peak_hour >= 22 or peak_hour <= 5:
                    judgments.append(f"你的高峰在 {peak_hour:02d}:00 左右，说明夜间使用比较明显。")
                else:
                    judgments.append(f"你的高峰在 {peak_hour:02d}:00 左右，这段时间更适合放重要工作。")
            if top_app["app"]:
                judgments.append(f"时间最集中的应用是 {self._app_display_name(top_app['app'])}，大约占 {round(top_share * 100)}%。")
            if mouse > keyboard * 1.8 and mouse > 1000:
                judgments.append("鼠标操作明显更多，手腕和肩颈更容易累。")
            elif keyboard > mouse * 1.8 and keyboard > 1000:
                judgments.append("键盘输入明显更多，手指和前臂更容易疲劳。")

            suggestions = [
                "每用电脑 45-60 分钟，离开屏幕 3-5 分钟，看远处，转动肩颈。",
                "把需要专注的事情放到高峰小时，零碎切换的事情放到低峰小时。",
            ]
            if avg_seconds >= 5 * 3600:
                suggestions.append("每天留一段 20 分钟以上的不看屏幕时间，不要把休息切得太碎。")
            if peak_hour is not None and (peak_hour >= 22 or peak_hour <= 5):
                suggestions.append("如果晚上还在高强度输入，睡前 30 分钟尽量收尾。")
            if mouse > keyboard * 1.5 and mouse > 1000:
                suggestions.append("鼠标用得多时，把最常用的动作换成快捷键，少让手腕来回移动。")

        comparison = self._comparison_text(previous, responses, avg_seconds, top_app, peak_hour)
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
            "judgments": judgments,
            "comparison": comparison,
            "suggestions": suggestions[:5],
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
        if hourly_days and hourly_days > days:
            hourly_cutoff = (datetime.now() - timedelta(days=hourly_days)).strftime("%Y-%m-%d")
            self._conn.execute("DELETE FROM keystrokes WHERE substr(ts,1,10) < ?", (hourly_cutoff,))
            self._conn.execute("DELETE FROM mouse_events WHERE substr(ts,1,10) < ?", (hourly_cutoff,))
        self._conn.commit()
