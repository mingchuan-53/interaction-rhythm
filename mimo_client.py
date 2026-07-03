"""MiMo-backed handfeel replay generation."""
import json
import os
import re
import statistics
import urllib.error
import urllib.request
from datetime import datetime, timedelta


DEFAULT_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
DEFAULT_MODEL = "mimo-v2.5-pro"

# ── 文本净化 ──────────────────────────────────────────────
TEXT_REPLACEMENTS = (
    # 效率 → 观察
    ("以提升效率", "方便回看现场"),
    ("提升效率", "更容易回看现场"),
    ("提升生产力", "响应更密"),
    ("生产力", "响应强度"),
    ("时间管理", "时间分布"),
    ("时间分配", "时间分布"),
    ("考虑优化", "可以回看"),
    ("优化", "回看"),
    ("专注于", "回看"),
    ("高效", "密集"),
    ("低效", "稀疏"),
    ("效率很高", "响应很密"),
    ("效率很低", "响应很稀"),
    ("高效工作", "密集响应"),
    ("深度工作", "连续响应"),
    ("心流状态", "连续响应"),
    ("心流", "连续响应"),
    ("沉浸", "连续"),
    # 任务 → 时段
    ("工作任务", "响应时段"),
    ("浏览任务", "浏览时段"),
    ("完成任务", "响应"),
    ("完成工作", "响应"),
    ("任务切换", "应用切换"),
    ("多任务", "多应用切换"),
    ("单任务", "单应用"),
    ("工作节奏", "响应节奏"),
    ("工作状态", "响应状态"),
    ("工作模式", "响应模式"),
    # 键盘表述
    ("键盘敲击", "键盘响应"),
    ("高敲击", "高键盘响应"),
    ("敲击冲刺", "键盘冲刺"),
    ("连续敲击", "连续键盘"),
    ("敲击时段", "键盘时段"),
    ("敲击", "键盘"),
    ("打字速度", "键盘密度"),
    ("打字", "键盘"),
    ("输入速度", "键盘密度"),
    # 代码/文件推测
    ("点开相关代码文件", "回看那一段应用构成"),
    ("相关代码文件", "那一段应用构成"),
    ("代码文件", "应用构成"),
    ("编写代码", "连续键盘"),
    ("写代码", "连续键盘"),
    ("coding", "连续键盘"),
    ("编程", "连续键盘"),
    ("debug", "连续键盘"),
    ("调试", "连续键盘"),
    ("写文档", "连续键盘"),
    ("写文章", "连续键盘"),
    ("写作", "连续键盘"),
    ("阅读文档", "浏览时段"),
    ("浏览网页", "浏览时段"),
    ("看视频", "浏览时段"),
    ("开会", "浏览时段"),
    ("会议", "浏览时段"),
    ("聊天", "浏览时段"),
    # 评判性词汇
    ("浪费时间", "低响应时段"),
    ("浪费", "低响应"),
    ("拖延", "间隔"),
    ("分心", "切换"),
    ("分神", "切换"),
    ("走神", "切换"),
    ("懒惰", "轻量"),
    ("懈怠", "轻量"),
    ("摸鱼", "轻量"),
    ("划水", "轻量"),
    ("偷懒", "轻量"),
    ("无聊", "轻量"),
    ("疲惫", "轻量"),
    ("疲劳", "轻量"),
    ("累", "轻量"),
    ("困", "轻量"),
    # 建议性词汇
    ("你应该", "可以"),
    ("你需要", "可以"),
    ("建议你", "可以"),
    ("建议", "观察"),
    ("应该", "可以"),
    ("需要", "可以"),
    ("必须", "可以"),
    ("不妨", "可以"),
    ("最好", "可以"),
    ("尝试", "回看"),
    ("试试", "回看"),
    ("改进", "回看"),
    ("改善", "回看"),
    ("提升", "变化"),
    ("提高", "变化"),
    ("增强", "变化"),
    ("减少", "变化"),
    ("降低", "变化"),
    ("避免", "观察"),
    ("注意", "观察"),
    ("关注", "观察"),
    ("重视", "观察"),
    # 推测性词汇
    ("你可能在", "数据显示"),
    ("你似乎在", "数据显示"),
    ("你好像在", "数据显示"),
    ("你在", "数据显示"),
    ("可能", "数据显示"),
    ("也许", "数据显示"),
    ("大概", "数据显示"),
    ("似乎", "数据显示"),
    ("好像", "数据显示"),
    ("感觉", "数据显示"),
    ("猜测", "数据显示"),
    ("推测", "数据显示"),
    ("估计", "数据显示"),
    ("判断", "数据显示"),
    ("认为", "数据显示"),
    ("觉得", "数据显示"),
    # 目标/计划词汇
    ("目标", "方向"),
    ("计划", "记录"),
    ("规划", "记录"),
    ("安排", "分布"),
    ("优先级", "顺序"),
    ("习惯", "模式"),
    ("养成习惯", "形成模式"),
    ("自律", "规律"),
    ("坚持", "持续"),
    ("打卡", "记录"),
    ("完成率", "响应率"),
    # 过度修饰
    ("非常", ""),
    ("十分", ""),
    ("特别", ""),
    ("极其", ""),
    ("超级", ""),
    ("超级棒", ""),
    ("很棒", ""),
    ("很好", ""),
    ("太好了", ""),
    ("厉害", ""),
    ("优秀", ""),
    ("出色", ""),
    ("完美", ""),
    ("糟糕", ""),
    ("很差", ""),
    ("太差", ""),
    ("很烂", ""),
)


def _clean_url(base_url: str) -> str:
    base = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _headers(api_key: str) -> dict:
    header_mode = os.getenv("MIMO_AUTH_HEADER", "").strip().lower()
    headers = {"Content-Type": "application/json"}
    if header_mode == "api-key":
        headers["api-key"] = api_key
    elif header_mode == "authorization":
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["api-key"] = api_key
    return headers


def _app_name(db, app: str) -> str:
    try:
        return db._app_display_name(app)
    except Exception:
        name = (app or "").strip()
        return name[:-4] if name.lower().endswith(".exe") else name


def _hour_range(hour: int | None) -> str:
    if hour is None:
        return ""
    return f"{hour:02d}:00-{(hour + 1) % 24:02d}:00"


def _segment_density(responses: int, active_seconds: int) -> str:
    """判断一个时段的响应密度等级"""
    if responses == 0:
        return "静默"
    rpm = responses / max(1, active_seconds / 60)
    if rpm >= 8:
        return "密集"
    if rpm >= 3:
        return "稳定"
    return "零星"


def _build_timeline_segments(db, date: str) -> list[dict]:
    """把一天切成6个4小时段，给AI时序感"""
    segments = []
    for start in range(0, 24, 4):
        total_r = 0
        top_app = ""
        top_r = 0
        for h in range(start, start + 4):
            detail = db.hour_detail(date, h)
            total_r += detail.get("responses", 0)
            for app in detail.get("apps", []):
                if app.get("responses", 0) > top_r:
                    top_r = app["responses"]
                    top_app = _app_name(db, app.get("app", ""))
        active_s = sum(
            db.hour_detail(date, h).get("responses", 0) > 0
            for h in range(start, start + 4)
        ) * 3600  # 粗估
        segments.append({
            "range": f"{start:02d}:00-{(start + 4) % 24:02d}:00",
            "responses": total_r,
            "density": _segment_density(total_r, active_s),
            "top_app": top_app if total_r > 0 else "",
        })
    return segments


def _median(values: list[int]) -> float:
    """计算中位数，空列表返回0"""
    if not values:
        return 0
    return statistics.median(values)


def _active_minutes(db, date: str) -> int:
    """统计有键盘/鼠标响应的分钟数（排除纯前台停留无操作的时间）"""
    try:
        rows = db._conn.execute(
            "SELECT DISTINCT substr(ts, 1, 16) FROM app_interactions "
            "WHERE substr(ts, 1, 10) = ? AND (keyboard > 0 OR mouse > 0)",
            (date,),
        ).fetchall()
        return len(rows)
    except Exception:
        return 0


def _build_7d_comparison(db, date: str) -> dict:
    """对比今天和过去7天中位数（按有响应的分钟归一化）"""
    try:
        today = db.day_stats(date)
        today_r = int(today.get("keystrokes", 0)) + int(today.get("mouse_events", 0))
    except Exception:
        return {}

    today_mins = _active_minutes(db, date)
    if today_mins < 5:
        return {}

    past_rpm = []
    past_responses = []
    d = datetime.strptime(date, "%Y-%m-%d")
    for i in range(1, 8):
        prev = (d - timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            s = db.day_stats(prev)
            r = int(s.get("keystrokes", 0)) + int(s.get("mouse_events", 0))
            mins = _active_minutes(db, prev)
            if r > 0 and mins >= 5:
                past_responses.append(r)
                past_rpm.append(round(r / mins, 2))
        except Exception:
            pass

    if not past_rpm:
        return {}

    today_rpm = round(today_r / today_mins, 2)
    median_rpm = _median(past_rpm)
    diff_pct = round((today_rpm - median_rpm) / max(0.01, median_rpm) * 100)

    if len(past_rpm) >= 3:
        sorted_rpm = sorted(past_rpm)
        q1 = sorted_rpm[len(sorted_rpm) // 4]
        q3 = sorted_rpm[len(sorted_rpm) * 3 // 4]
        iqr = q3 - q1
        volatility = "波动大" if iqr > median_rpm * 0.5 else "波动小"
    else:
        volatility = "数据少"

    return {
        "today_responses": today_r,
        "today_rpm": today_rpm,
        "today_active_mins": today_mins,
        "median_7d_rpm": round(median_rpm, 2),
        "diff_percent": diff_pct,
        "trend": "比平时更密" if diff_pct > 15 else ("比平时更疏" if diff_pct < -15 else "和平时持平"),
        "volatility": volatility,
        "sample_days": len(past_rpm),
    }


def _compact_day_context(db, date: str) -> dict:
    """组装给AI的完整上下文：当天数据 + 时间分段 + 7天对比"""
    stats = db.day_stats(date)
    apps = db.app_chart(date)
    hourly = db.hourly_chart(date)
    keyboard = int(stats.get("keystrokes") or 0)
    mouse = int(stats.get("mouse_events") or 0)
    responses = keyboard + mouse
    peak_hour = max(range(24), key=lambda h: hourly[h]) if responses else None
    top_hours = sorted(
        ({"hour": h, "range": _hour_range(h), "responses": int(v)} for h, v in enumerate(hourly) if v),
        key=lambda item: item["responses"],
        reverse=True,
    )[:5]
    top_apps = []
    for app in apps[:6]:
        top_apps.append({
            "name": _app_name(db, app.get("app", "")),
            "minutes": round(int(app.get("seconds") or 0) / 60),
            "responses": int(app.get("responses") or 0),
            "share": round((app.get("response_share") or 0) * 100),
            "density": app.get("response_density") or 0,
        })

    segments = _build_timeline_segments(db, date)
    comparison = _build_7d_comparison(db, date)

    kb_ratio = round(keyboard / max(1, responses) * 100)
    mouse_ratio = 100 - kb_ratio
    if kb_ratio >= 70:
        input_type = "键盘主导"
    elif mouse_ratio >= 70:
        input_type = "鼠标主导"
    else:
        input_type = "混合输入"

    return {
        "date": date,
        "keyboard": keyboard,
        "mouse": mouse,
        "responses": responses,
        "input_type": input_type,
        "kb_ratio": kb_ratio,
        "active_minutes": round(int(stats.get("total_seconds") or 0) / 60),
        "peak_hour": peak_hour,
        "peak_range": _hour_range(peak_hour),
        "top_hours": top_hours,
        "top_apps": top_apps,
        "segments": segments,
        "comparison": comparison,
    }


def _extract_json(text: str) -> dict | None:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _normalize_list(value) -> list[str]:
    if isinstance(value, list):
        return [_clean_text(str(item).strip()) for item in value if str(item).strip()]
    if isinstance(value, str):
        lines = [line.strip(" -\t0123456789.、") for line in value.splitlines()]
        return [_clean_text(line) for line in lines if line]
    return []


def _clean_text(text: str) -> str:
    cleaned = str(text or "")
    for old, new in TEXT_REPLACEMENTS:
        cleaned = cleaned.replace(old, new)
    cleaned = cleaned.strip().strip('"').strip("'")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _parse_natural_output(text: str) -> tuple[str, list[str]]:
    """解析自然语言输出：第一句=结论，其余=线索"""
    cleaned = _clean_text(text or "")
    if not cleaned:
        return "", []

    # 按句号/换行拆分
    sentences = re.split(r'[。\n]+', cleaned)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 4]

    if not sentences:
        return "", []

    conclusion = sentences[0]
    findings = sentences[1:4]  # 最多3条线索

    return conclusion, findings


def _fallback_parse(text: str) -> tuple[str, list[str]]:
    """解析自然语言输出：按行拆分"""
    lines = [line.strip(" -\t0123456789.、") for line in (text or "").splitlines()]
    lines = [_clean_text(line) for line in lines if line and len(line) > 4]
    if not lines:
        return "今天的数据形状还比较轻。", []
    conclusion = lines[0]
    findings = lines[1:4]
    return conclusion, findings


def _call_mimo(messages: list[dict]) -> str:
    api_key = os.getenv("MIMO_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("未配置 MIMO_API_KEY")
    model = os.getenv("MIMO_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    url = _clean_url(os.getenv("MIMO_BASE_URL", DEFAULT_BASE_URL))
    timeout = int(os.getenv("MIMO_TIMEOUT", "60"))
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.5,
        "stream": False,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=_headers(api_key), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MiMo API {exc.code}: {error_body[:240]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"MiMo 连接失败：{exc.reason}") from exc

    data = json.loads(raw)
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("MiMo 返回格式无法识别") from exc


def mimo_day_replay(db, date: str | None = None) -> dict:
    """Generate a day replay with MiMo using only aggregate local activity data."""
    try:
        date = datetime.fromisoformat(date or "").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        date = datetime.now().strftime("%Y-%m-%d")

    context = _compact_day_context(db, date)

    system = (
        "你是扣舷的手感回放写作者。"
        "只能根据数据写回放。不猜测输入内容、窗口内容、真实意图。"
        "不评分，不评价好坏，不给建议，不写下一步。"
        "中文输出。每句话不超过20个字。总共5-8句。"
        "克制、有画面感、绑定具体数据。"
        "用比喻描述节奏，比如雨点、潮水、独奏、穿梭、钟摆、爵士。"
        "禁用词：效率、优化、提升、专注、生产力、任务、敲击、建议、目标、计划、应该、需要。"
        "用'键盘'代替'敲击'，用'时段'代替'任务'，用'回看'代替'优化'。"
        "只描述，不建议。只观察，不引导。"
        "【重要】输出格式是纯文本段落，不是JSON，不是列表，不是Markdown。"
        "【重要】不要输出任何花括号、方括号、引号、冒号、逗号分隔的结构化数据。"
        "【重要】像写散文一样写，句号分隔句子。"
        "示例输出：\n"
        "今天的数字手感像连绵的雨。键盘是主力，鼠标偶尔点缀。"
        "14点到16点是重心，响应最密集。VSCode占了四成，像独奏。"
        "相比平时更密，节奏更紧。"
    )

    user = (
        f"今天是{context['date']}。数据如下：\n"
        f"键盘{context['keyboard']}次，鼠标{context['mouse']}次，共{context['responses']}次响应。"
        f"输入方式：{context['input_type']}（键盘{context['kb_ratio']}%）。"
        f"活跃{context['active_minutes']}分钟。"
    )

    if context.get("peak_hour") is not None:
        user += f"高峰在{context['peak_range']}。"

    if context["top_apps"]:
        app_parts = []
        for a in context["top_apps"][:4]:
            app_parts.append(f"{a['name']}占{a['share']}%、{a['minutes']}分钟")
        user += "主要应用：" + "；".join(app_parts) + "。"

    active_segments = [s for s in context["segments"] if s["responses"] > 0]
    if active_segments:
        seg_parts = []
        for s in active_segments:
            app_note = f"（{s['top_app']}主导）" if s["top_app"] else ""
            seg_parts.append(f"{s['range']}{s['density']}{app_note}")
        user += "时段分布：" + "；".join(seg_parts) + "。"

    comp = context.get("comparison", {})
    if comp:
        user += (
            f"有响应的分钟数：{comp.get('today_active_mins', '?')}分钟。"
            f"每分钟响应：今天{comp['today_rpm']}次，"
            f"过去7天中位数{comp['median_7d_rpm']}次，{comp['trend']}。"
            f"{comp['volatility']}。"
        )

    user += "\n请写今天的数字手感回放。5-8句，每句不超过20字。只描述，不建议。"

    raw_text = _call_mimo([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])

    # 优先按纯文本解析
    conclusion, findings = _parse_natural_output(raw_text)
    if not conclusion:
        # 降级：尝试JSON兼容旧格式
        parsed = _extract_json(raw_text)
        if parsed:
            conclusion = _clean_text(parsed.get("conclusion") or "")
            findings = _normalize_list(parsed.get("findings"))
    if not conclusion:
        conclusion, findings = _fallback_parse(raw_text)

    if not conclusion:
        conclusion = "今天的数据形状还比较轻，先保留为轻量记录。"
    if not findings:
        findings = ["有效线索还不够集中。"]

    model = os.getenv("MIMO_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    return {
        "ok": True,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "assistant": "MiMo 手感回放",
        "model": model,
        "model_note": "由 MiMo 根据本机聚合数据生成，不包含输入内容或窗口正文。",
        "provider": "mimo",
        "interface": "GET /api/mimo-replay?date=YYYY-MM-DD",
        "scope": "day",
        "date": date,
        "days": 1,
        "conclusion": conclusion,
        "summary": context,
        "findings": findings[:3],
        "judgments": findings[:3],
        "suggestions": findings[:2],  # 向后兼容：用findings填充
        "raw_text": raw_text,
    }
