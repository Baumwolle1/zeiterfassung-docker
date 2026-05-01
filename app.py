import calendar
import io
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


APP_TITLE = "Zeiterfassung"
APP_PASSWORD = os.environ.get("APP_PASSWORD", "krause")
APP_SECRET_KEY = os.environ.get("APP_SECRET_KEY", "zeiterfassung-krause-login")
SESSION_DAYS = 30
YEAR_VACATION_DAYS = 30
MONTH_NAMES = [
    "Januar",
    "Februar",
    "Maerz",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]
WEEKDAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
WEEKDAY_SHORT = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]

SHIFT_CONFIG = {
    "Fruehschicht": {"label": "Frühschicht", "target": 465, "break": 30, "start": "06:45", "end": "15:00"},
    "Spaetschicht": {"label": "Spätschicht", "target": 420, "break": 0, "start": "12:00", "end": "19:00"},
    "Freitag": {"label": "Freitag", "target": 375, "break": 0, "start": "06:45", "end": "13:00"},
    "Notdienst": {"label": "Notdienst", "target": 0, "break": 0, "start": "", "end": ""},
    "Urlaub": {"label": "Urlaub", "target": 0, "break": 0, "start": "", "end": ""},
    "Krank": {"label": "Krank", "target": 0, "break": 0, "start": "", "end": ""},
    "Arztkrank": {"label": "Arztkrank", "target": 0, "break": 0, "start": "", "end": ""},
    "Feiertag": {"label": "Feiertag", "target": 0, "break": 0, "start": "", "end": ""},
    "Frei": {"label": "Frei", "target": 0, "break": 0, "start": "", "end": ""},
}
WORK_TYPES = ("Fruehschicht", "Spaetschicht", "Freitag", "Notdienst")
TIME_ENTRY_TYPES = WORK_TYPES + ("Arztkrank",)
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ["DATA_DIR"]) if os.environ.get("DATA_DIR") else BASE_DIR / "data"
DB_PATH = DATA_DIR / "zeiterfassung.db"


@dataclass
class Totals:
    target: int
    actual: int
    balance: int
    deducted_break: int


def default_segments_for_shift(shift_type: str, start_time: str = "", end_time: str = "") -> list[dict[str, str]]:
    if shift_type not in TIME_ENTRY_TYPES:
        return []
    start_value = start_time or SHIFT_CONFIG[shift_type]["start"]
    end_value = end_time or SHIFT_CONFIG[shift_type]["end"]
    if shift_type == "Notdienst":
        if start_time or end_time:
            return [{"start": start_time, "end": end_time}]
        return [{"start": "", "end": ""}]
    return [{"start": start_value, "end": end_value}]


def normalize_segments(raw_segments) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    if not isinstance(raw_segments, list):
        return normalized
    for segment in raw_segments:
        if not isinstance(segment, dict):
            continue
        start_time = normalize_time(str(segment.get("start", "")))
        end_time = normalize_time(str(segment.get("end", "")))
        if not start_time and not end_time:
            continue
        normalized.append({"start": start_time, "end": end_time})
    return normalized


def segments_for_entry(shift_type: str, start_time: str, end_time: str, segments_json: str | None = None) -> list[dict[str, str]]:
    segments: list[dict[str, str]] = []
    if segments_json:
        try:
            segments = normalize_segments(json.loads(segments_json))
        except json.JSONDecodeError:
            segments = []
    if segments:
        return segments
    return normalize_segments(default_segments_for_shift(shift_type, start_time, end_time))


def entry_payload(shift_type: str, start_time: str, end_time: str, notes: str, segments: list[dict[str, str]] | None = None) -> dict:
    resolved_segments = normalize_segments(segments if segments is not None else default_segments_for_shift(shift_type, start_time, end_time))
    primary = resolved_segments[0] if resolved_segments else {"start": "", "end": ""}
    if shift_type not in TIME_ENTRY_TYPES:
        primary = {"start": "", "end": ""}
        resolved_segments = []
    return {
        "shift_type": shift_type,
        "start_time": primary["start"],
        "end_time": primary["end"],
        "notes": notes or "",
        "segments": resolved_segments,
    }


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = APP_SECRET_KEY
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=SESSION_DAYS)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    init_db()

    def is_authenticated() -> bool:
        return bool(session.get("authenticated"))

    def login_required(view_func):
        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            if is_authenticated():
                return view_func(*args, **kwargs)
            next_url = request.full_path if request.query_string else request.path
            if next_url.endswith("?"):
                next_url = next_url[:-1]
            return redirect(url_for("login", next=next_url))

        return wrapped_view

    @app.context_processor
    def inject_globals():
        return {
            "app_title": APP_TITLE,
            "month_names": MONTH_NAMES,
            "weekday_names": WEEKDAY_NAMES,
            "shift_config": SHIFT_CONFIG,
            "format_minutes": format_minutes,
            "balance_class": balance_class,
            "is_authenticated": is_authenticated(),
        }

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if is_authenticated():
            return redirect(request.args.get("next") or url_for("index"))

        error = ""
        next_url = request.values.get("next") or url_for("index")
        if request.method == "POST":
            password = request.form.get("password", "")
            remember_me = request.form.get("remember_me") == "on"
            if password == APP_PASSWORD:
                session.clear()
                session["authenticated"] = True
                session.permanent = remember_me
                return redirect(next_url)
            error = "Passwort falsch."

        return render_template("login.html", error=error, next_url=next_url)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def index():
        today = client_today_from_request() or date.today()
        if not request.args:
            return redirect(url_for("index", year=today.year, month=today.month, day=today.day, view="week"))

        year = int(request.args.get("year", today.year))
        month = int(request.args.get("month", today.month))
        month = max(1, min(month, 12))
        view_mode = request.args.get("view", "week")
        if view_mode not in {"week", "month"}:
            view_mode = "week"
        _, days_in_month = calendar.monthrange(year, month)

        selected_day = int(request.args.get("day", min(today.day, days_in_month)))
        selected_day = max(1, min(selected_day, days_in_month))
        selected_date = date(year, month, selected_day)
        week_start = selected_date - timedelta(days=selected_date.weekday())
        week_end = week_start + timedelta(days=6)

        month_entries = fetch_month_entries(year, month)
        days = []
        for day_number in range(1, days_in_month + 1):
            current_date = date(year, month, day_number)
            entry = month_entries.get(current_date.isoformat())
            shift_type = entry["shift_type"] if entry else default_type_for(current_date)
            totals = calculate_totals(
                shift_type,
                (entry["start_time"] if entry else "") or "",
                (entry["end_time"] if entry else "") or "",
                (entry["segments"] if entry else []) or [],
            )
            days.append(
                {
                    "date": current_date,
                    "is_selected": current_date == selected_date,
                    "shift_type": shift_type,
                    "weekday": WEEKDAY_NAMES[current_date.weekday()],
                    "target_text": format_minutes(totals.target),
                    "actual_text": format_minutes(totals.actual),
                    "balance_text": format_minutes(totals.balance),
                    "balance_class": balance_class(totals.balance),
                    "is_today": current_date == today,
                    "holiday_name": holiday_name_for(current_date),
                }
            )

        entry = fetch_entry(selected_date)
        form_data = (
            entry
            if entry
            else entry_payload(default_type_for(selected_date), "", "", "")
        )
        selected_totals = calculate_totals(
            form_data["shift_type"],
            form_data["start_time"],
            form_data["end_time"],
            form_data["segments"],
        )
        week_target, week_actual, month_target, month_actual = calculate_ranges(selected_date, month_entries, form_data)
        week_balance_total = week_actual - week_target
        month_progress = calculate_month_progress(year, month, month_entries, selected_date, form_data, today)
        month_balance_total = calculate_month_balance(year, month, month_entries, selected_date, form_data, today)
        week_summaries = build_week_summaries(year, month, month_entries, selected_date, form_data)
        vacation_taken, sick_days = count_special_days(year)
        visible_days = [
            item for item in days
            if view_mode == "month" or week_start <= item["date"] <= week_end
        ]

        return render_template(
            "index.html",
            year=year,
            month=month,
            view_mode=view_mode,
            selected_date=selected_date,
            selected_day=selected_day,
            days=days,
            visible_days=visible_days,
            form_data=form_data,
            selected_totals=selected_totals,
            today=today,
            week_target=format_minutes(week_target),
            week_actual=format_minutes(week_actual),
            week_balance=format_minutes(week_balance_total),
            week_balance_class=balance_class(week_balance_total),
            month_target=format_minutes(month_target),
            month_actual=format_minutes(month_actual),
            month_progress=format_minutes(month_progress),
            month_balance=format_minutes(month_balance_total),
            month_balance_class=balance_class(month_balance_total),
            week_summaries=serialize_week_summaries(week_summaries),
            vacation_total=YEAR_VACATION_DAYS,
            vacation_taken=vacation_taken,
            vacation_remaining=max(YEAR_VACATION_DAYS - vacation_taken, 0),
            sick_days=sick_days,
            week_start=week_start,
            week_end=week_end,
            week_label=f"KW {selected_date.isocalendar().week:02d}",
            prev_period=period_nav(selected_date, view_mode, -1),
            next_period=period_nav(selected_date, view_mode, 1),
        )

    @app.post("/save")
    @login_required
    def save():
        year = int(request.form["year"])
        month = int(request.form["month"])
        day = int(request.form["day"])
        view_mode = request.form.get("view", "week")
        selected_date = date(year, month, day)

        shift_type = request.form["shift_type"]
        submitted_segments = [
            {"start": start_value, "end": end_value}
            for start_value, end_value in zip(
                request.form.getlist("segment_start[]"),
                request.form.getlist("segment_end[]"),
            )
        ]
        segments = normalize_segments(submitted_segments)
        start_time = normalize_time(request.form.get("start_time", ""))
        end_time = normalize_time(request.form.get("end_time", ""))
        notes = request.form.get("notes", "")

        if shift_type not in SHIFT_CONFIG:
            shift_type = default_type_for(selected_date)

        if shift_type not in TIME_ENTRY_TYPES:
            start_time = ""
            end_time = ""
            segments = []
        elif not segments:
            segments = normalize_segments(default_segments_for_shift(shift_type, start_time, end_time))

        payload = entry_payload(shift_type, start_time, end_time, notes, segments)
        save_entry(selected_date, payload["shift_type"], payload["start_time"], payload["end_time"], payload["notes"], payload["segments"])
        return redirect(url_for("index", year=year, month=month, day=day, view=view_mode))

    @app.post("/save-json")
    @login_required
    def save_json():
        payload = request.get_json(force=True)
        year = int(payload["year"])
        month = int(payload["month"])
        day = int(payload["day"])
        view_mode = payload.get("view", "week")
        selected_date = date(year, month, day)

        shift_type = payload.get("shift_type", default_type_for(selected_date))
        submitted_segments = payload.get("segments", [])
        segments = normalize_segments(submitted_segments)
        start_time = normalize_time(payload.get("start_time", ""))
        end_time = normalize_time(payload.get("end_time", ""))
        notes = payload.get("notes", "") or ""

        if shift_type not in SHIFT_CONFIG:
            shift_type = default_type_for(selected_date)

        if shift_type not in TIME_ENTRY_TYPES:
            start_time = ""
            end_time = ""
            segments = []
        elif not segments:
            segments = normalize_segments(default_segments_for_shift(shift_type, start_time, end_time))

        entry = entry_payload(shift_type, start_time, end_time, notes, segments)
        save_entry(selected_date, entry["shift_type"], entry["start_time"], entry["end_time"], entry["notes"], entry["segments"])
        totals = calculate_totals(entry["shift_type"], entry["start_time"], entry["end_time"], entry["segments"])
        month_entries = fetch_month_entries(year, month)
        week_target, week_actual, month_target, month_actual = calculate_ranges(selected_date, month_entries, entry)
        week_balance_total = week_actual - week_target
        today = client_today_from_request() or date.today()
        month_progress = calculate_month_progress(year, month, month_entries, selected_date, entry, today)
        month_balance_total = calculate_month_balance(year, month, month_entries, selected_date, entry, today)
        week_summaries = build_week_summaries(year, month, month_entries, selected_date, entry)
        vacation_taken, sick_days = count_special_days(year)
        return jsonify(
            {
                "ok": True,
                "shift_type": shift_type,
                "start_time": entry["start_time"],
                "end_time": entry["end_time"],
                "notes": entry["notes"],
                "segments": entry["segments"],
                "target": format_minutes(totals.target),
                "actual": format_minutes(totals.actual),
                "balance": format_minutes(totals.balance),
                "break": format_minutes(totals.deducted_break),
                "balance_class": balance_class(totals.balance),
                "week_balance": format_minutes(week_balance_total),
                "week_balance_class": balance_class(week_balance_total),
                "month_progress": format_minutes(month_progress),
                "month_target": format_minutes(month_target),
                "month_actual": format_minutes(month_actual),
                "month_balance": format_minutes(month_balance_total),
                "month_balance_class": balance_class(month_balance_total),
                "week_summaries": serialize_week_summaries(week_summaries),
                "vacation_taken": vacation_taken,
                "vacation_remaining": max(YEAR_VACATION_DAYS - vacation_taken, 0),
                "sick_days": sick_days,
                "day_href": url_for("index", year=year, month=month, day=day, view=view_mode),
                "day_target": format_minutes(totals.target),
                "day_actual": format_minutes(totals.actual),
                "day_balance": format_minutes(totals.balance),
            }
        )

    @app.post("/apply-week-template")
    @login_required
    def apply_week_template():
        year = int(request.form["year"])
        month = int(request.form["month"])
        day = int(request.form["day"])
        template_type = request.form["template_type"]
        selected_date = date(year, month, day)

        if template_type not in {"Fruehschicht", "Spaetschicht"}:
            return redirect(url_for("index", year=year, month=month, day=day, view="week"))

        week_start = selected_date - timedelta(days=selected_date.weekday())
        for offset in range(7):
            current = week_start + timedelta(days=offset)
            if current.month != month or current.year != year:
                continue
            existing_entry = fetch_entry(current)
            if holiday_name_for(current):
                notes = existing_entry["notes"] if existing_entry else ""
                save_entry(current, "Feiertag", "", "", notes, [])
                continue
            if current.weekday() == 4:
                notes = existing_entry["notes"] if existing_entry else ""
                save_entry(
                    current,
                    "Freitag",
                    SHIFT_CONFIG["Freitag"]["start"],
                    SHIFT_CONFIG["Freitag"]["end"],
                    notes,
                    None,
                )
                continue
            if current.weekday() >= 5:
                notes = existing_entry["notes"] if existing_entry else ""
                save_entry(current, "Frei", "", "", notes, [])
                continue
            defaults = SHIFT_CONFIG[template_type]
            notes = existing_entry["notes"] if existing_entry else ""
            save_entry(
                current,
                template_type,
                defaults["start"],
                defaults["end"],
                notes,
                None,
            )

        return redirect(url_for("index", year=year, month=month, day=day, view="week"))

    @app.get("/export/pdf")
    @login_required
    def export_pdf():
        year = int(request.args.get("year", date.today().year))
        month = int(request.args.get("month", date.today().month))
        pdf_bytes = build_month_pdf(year, month)
        filename = f"Zeiterfassung_{year}_{month:02d}.pdf"
        return send_file(pdf_bytes, mimetype="application/pdf", as_attachment=True, download_name=filename)

    @app.post("/quick-stamp")
    @login_required
    def quick_stamp():
        payload = request.get_json(force=True)
        year = int(payload["year"])
        month = int(payload["month"])
        day = int(payload["day"])
        field = payload["field"]
        value = normalize_time(payload["value"])
        selected_date = date(year, month, day)

        entry = fetch_entry(selected_date)
        if entry:
            shift_type = entry["shift_type"]
            start_time = entry["start_time"]
            end_time = entry["end_time"]
            notes = entry["notes"]
        else:
            shift_type = default_type_for(selected_date)
            start_time = SHIFT_CONFIG[shift_type]["start"]
            end_time = SHIFT_CONFIG[shift_type]["end"]
            notes = ""

        if field == "start":
            start_time = value
        elif field == "end":
            end_time = value
        else:
            return jsonify({"ok": False}), 400

        if shift_type not in TIME_ENTRY_TYPES:
            shift_type = default_type_for(selected_date)
            if shift_type not in TIME_ENTRY_TYPES:
                shift_type = "Fruehschicht"
            if not start_time:
                start_time = SHIFT_CONFIG[shift_type]["start"]
            if not end_time:
                end_time = SHIFT_CONFIG[shift_type]["end"]

        segments = entry["segments"] if entry else normalize_segments(default_segments_for_shift(shift_type, start_time, end_time))
        if not segments:
            segments = normalize_segments(default_segments_for_shift(shift_type, start_time, end_time))
        if segments:
            segments[0][field] = value

        payload = entry_payload(shift_type, start_time, end_time, notes, segments)
        save_entry(selected_date, payload["shift_type"], payload["start_time"], payload["end_time"], payload["notes"], payload["segments"])
        totals = calculate_totals(payload["shift_type"], payload["start_time"], payload["end_time"], payload["segments"])
        return jsonify(
            {
                "ok": True,
                "start_time": payload["start_time"],
                "end_time": payload["end_time"],
                "segments": payload["segments"],
                "target": format_minutes(totals.target),
                "actual": format_minutes(totals.actual),
                "balance": format_minutes(totals.balance),
                "break": format_minutes(totals.deducted_break),
                "balance_class": balance_class(totals.balance),
            }
        )

    return app


def client_today_from_request() -> date | None:
    value = request.cookies.get("client_today", "").strip()
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
    return parsed


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                entry_date TEXT PRIMARY KEY,
                shift_type TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                notes TEXT DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(entries)").fetchall()}
        if "segments_json" not in columns:
            conn.execute("ALTER TABLE entries ADD COLUMN segments_json TEXT DEFAULT '[]'")


def fetch_entry(day_value: date) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT shift_type, start_time, end_time, notes, segments_json FROM entries WHERE entry_date = ?",
            (day_value.isoformat(),),
        ).fetchone()
    if not row:
        return None
    return entry_payload(row[0], row[1] or "", row[2] or "", row[3] or "", segments_for_entry(row[0], row[1] or "", row[2] or "", row[4] or "[]"))


def fetch_month_entries(year: int, month: int) -> dict[str, dict]:
    start = date(year, month, 1)
    _, days_in_month = calendar.monthrange(year, month)
    end = date(year, month, days_in_month)
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT entry_date, shift_type, start_time, end_time, notes, segments_json FROM entries WHERE entry_date BETWEEN ? AND ?",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    return {
        row[0]: entry_payload(
            row[1],
            row[2] or "",
            row[3] or "",
            row[4] or "",
            segments_for_entry(row[1], row[2] or "", row[3] or "", row[5] or "[]"),
        )
        for row in rows
    }


def save_entry(day_value: date, shift_type: str, start_time: str, end_time: str, notes: str, segments: list[dict[str, str]] | None = None) -> None:
    payload = entry_payload(shift_type, start_time, end_time, notes, segments)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO entries (entry_date, shift_type, start_time, end_time, notes, updated_at, segments_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entry_date) DO UPDATE SET
                shift_type = excluded.shift_type,
                start_time = excluded.start_time,
                end_time = excluded.end_time,
                notes = excluded.notes,
                updated_at = excluded.updated_at,
                segments_json = excluded.segments_json
            """,
            (
                day_value.isoformat(),
                payload["shift_type"],
                payload["start_time"],
                payload["end_time"],
                payload["notes"],
                datetime.now().isoformat(timespec="seconds"),
                json.dumps(payload["segments"], ensure_ascii=True),
            ),
        )


def count_special_days(year: int) -> tuple[int, int]:
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT shift_type, COUNT(*)
            FROM entries
            WHERE entry_date BETWEEN ? AND ?
            AND shift_type IN ('Urlaub', 'Krank')
            GROUP BY shift_type
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    counts = {row[0]: row[1] for row in rows}
    return counts.get("Urlaub", 0), counts.get("Krank", 0)


def default_type_for(day_value: date) -> str:
    if holiday_name_for(day_value):
        return "Feiertag"
    if day_value.weekday() == 4:
        return "Freitag"
    if day_value.weekday() >= 5:
        return "Frei"
    return "Fruehschicht"


def holiday_name_for(day_value: date) -> str | None:
    easter = easter_sunday(day_value.year)
    holidays = {
        date(day_value.year, 1, 1): "Neujahr",
        date(day_value.year, 5, 1): "Tag der Arbeit",
        date(day_value.year, 10, 3): "Tag der Deutschen Einheit",
        date(day_value.year, 12, 25): "1. Weihnachtstag",
        date(day_value.year, 12, 26): "2. Weihnachtstag",
        easter - timedelta(days=2): "Karfreitag",
        easter + timedelta(days=1): "Ostermontag",
        easter + timedelta(days=39): "Christi Himmelfahrt",
        easter + timedelta(days=50): "Pfingstmontag",
    }
    return holidays.get(day_value)


def easter_sunday(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def parse_time(value: str) -> int | None:
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.strptime(text, "%H:%M")
    except ValueError:
        return None
    return parsed.hour * 60 + parsed.minute


def normalize_time(value: str) -> str:
    digits = "".join(char for char in value if char.isdigit())[:4]
    if len(digits) <= 2:
        return digits
    return f"{digits[:2]}:{digits[2:]}"


def calculate_totals(shift_type: str, start_time: str, end_time: str, segments: list[dict[str, str]] | None = None) -> Totals:
    config = SHIFT_CONFIG[shift_type]
    if shift_type not in WORK_TYPES:
        return Totals(target=config["target"], actual=0, balance=0, deducted_break=0)

    resolved_segments = normalize_segments(segments if segments is not None else default_segments_for_shift(shift_type, start_time, end_time))
    if shift_type == "Notdienst":
        actual = 0
        for segment in resolved_segments:
            start_minutes = parse_time(segment["start"])
            end_minutes = parse_time(segment["end"])
            if start_minutes is None or end_minutes is None or end_minutes < start_minutes:
                continue
            actual += end_minutes - start_minutes
        return Totals(target=config["target"], actual=actual, balance=actual - config["target"], deducted_break=0)

    primary = resolved_segments[0] if resolved_segments else {"start": start_time, "end": end_time}
    start_minutes = parse_time(primary["start"])
    end_minutes = parse_time(primary["end"])
    if start_minutes is None or end_minutes is None or end_minutes < start_minutes:
        return Totals(target=config["target"], actual=0, balance=-config["target"], deducted_break=0)

    worked = end_minutes - start_minutes
    deducted_break = config["break"] if worked > 360 else 0
    actual = max(worked - deducted_break, 0)
    return Totals(target=config["target"], actual=actual, balance=actual - config["target"], deducted_break=deducted_break)


def calculate_ranges(selected_date: date, month_entries: dict[str, dict], selected_form: dict) -> tuple[int, int, int, int]:
    week_start = selected_date - timedelta(days=selected_date.weekday())
    week_end = week_start + timedelta(days=6)
    week_target = 0
    week_actual = 0
    cursor = week_start
    while cursor <= week_end:
        if cursor.month != selected_date.month or cursor.year != selected_date.year:
            cursor += timedelta(days=1)
            continue
        totals = totals_for_aggregate_day(cursor, month_entries, selected_date, selected_form)
        week_target += totals.target
        week_actual += totals.actual
        cursor += timedelta(days=1)

    _, days_in_month = calendar.monthrange(selected_date.year, selected_date.month)
    month_target = 0
    month_actual = 0
    for day_number in range(1, days_in_month + 1):
        current = date(selected_date.year, selected_date.month, day_number)
        totals = totals_for_aggregate_day(current, month_entries, selected_date, selected_form)
        month_target += totals.target
        month_actual += totals.actual
    return week_target, week_actual, month_target, month_actual


def calculate_month_progress(
    year: int,
    month: int,
    month_entries: dict[str, dict],
    selected_date: date,
    selected_form: dict,
    today: date,
) -> int:
    month_start = date(year, month, 1)
    _, days_in_month = calendar.monthrange(year, month)
    month_end = date(year, month, days_in_month)

    if (year, month) > (today.year, today.month):
        return 0

    cutoff = today if (year, month) == (today.year, today.month) else month_end
    cutoff = min(cutoff, month_end)

    progress = 0
    current = month_start
    while current <= cutoff:
        totals = totals_for_day(current, month_entries, selected_date, selected_form)
        progress += totals.actual
        current += timedelta(days=1)
    return progress


def calculate_month_balance(
    year: int,
    month: int,
    month_entries: dict[str, dict],
    selected_date: date,
    selected_form: dict,
    today: date,
) -> int:
    month_start = date(year, month, 1)
    _, days_in_month = calendar.monthrange(year, month)
    month_end = date(year, month, days_in_month)

    if (year, month) > (today.year, today.month):
        return 0

    cutoff = today if (year, month) == (today.year, today.month) else month_end
    cutoff = min(cutoff, month_end)

    balance_total = 0
    current = month_start
    while current <= cutoff:
        totals = totals_for_aggregate_day(current, month_entries, selected_date, selected_form)
        balance_total += totals.balance
        current += timedelta(days=1)
    return balance_total


def build_week_summaries(year: int, month: int, month_entries: dict[str, dict], selected_date: date, selected_form: dict) -> list[dict]:
    _, days_in_month = calendar.monthrange(year, month)
    summaries: list[dict] = []
    current_summary: dict | None = None

    for day_number in range(1, days_in_month + 1):
        current = date(year, month, day_number)
        iso_year, iso_week, _ = current.isocalendar()
        if not current_summary or current_summary["iso_year"] != iso_year or current_summary["iso_week"] != iso_week:
            if current_summary:
                summaries.append(current_summary)
            current_summary = {
                "iso_year": iso_year,
                "iso_week": iso_week,
                "start": current,
                "end": current,
                "target": 0,
                "actual": 0,
            }

        totals = totals_for_aggregate_day(current, month_entries, selected_date, selected_form)
        current_summary["end"] = current
        current_summary["target"] += totals.target
        current_summary["actual"] += totals.actual

    if current_summary:
        summaries.append(current_summary)

    for summary in summaries:
        summary["balance"] = summary["actual"] - summary["target"]

    return summaries


def serialize_week_summaries(week_summaries: list[dict]) -> list[dict]:
    return [
        {
            "label": f"KW {summary['iso_week']:02d}",
            "range": f"{summary['start'].strftime('%d.%m.')} - {summary['end'].strftime('%d.%m.')}",
            "target": format_minutes(summary["target"]),
            "actual": format_minutes(summary["actual"]),
            "balance": format_minutes(summary["balance"]),
            "balance_class": balance_class(summary["balance"]),
        }
        for summary in week_summaries
    ]


def totals_for_day(day_value: date, month_entries: dict[str, dict], selected_date: date, selected_form: dict) -> Totals:
    if day_value == selected_date:
        return calculate_totals(selected_form["shift_type"], selected_form["start_time"], selected_form["end_time"], selected_form["segments"])
    entry = month_entries.get(day_value.isoformat())
    shift_type = entry["shift_type"] if entry else default_type_for(day_value)
    return calculate_totals(
        shift_type,
        (entry["start_time"] if entry else "") or "",
        (entry["end_time"] if entry else "") or "",
        (entry["segments"] if entry else []) or [],
    )


def totals_for_aggregate_day(day_value: date, month_entries: dict[str, dict], selected_date: date, selected_form: dict) -> Totals:
    if day_value == selected_date:
        shift_type = selected_form["shift_type"]
        totals = calculate_totals(shift_type, selected_form["start_time"], selected_form["end_time"], selected_form["segments"])
    else:
        entry = month_entries.get(day_value.isoformat())
        shift_type = entry["shift_type"] if entry else default_type_for(day_value)
        totals = calculate_totals(
            shift_type,
            (entry["start_time"] if entry else "") or "",
            (entry["end_time"] if entry else "") or "",
            (entry["segments"] if entry else []) or [],
        )

    if shift_type == "Notdienst" and day_value.weekday() >= 5:
        return Totals(target=totals.target, actual=0, balance=0, deducted_break=0)
    return totals


def format_minutes(value: int) -> str:
    sign = "-" if value < 0 else ""
    absolute = abs(value)
    return f"{sign}{absolute // 60:02d}:{absolute % 60:02d}"


def balance_class(value: int) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def month_nav(year: int, month: int, delta: int) -> dict:
    new_month = month + delta
    new_year = year
    if new_month < 1:
        new_month = 12
        new_year -= 1
    elif new_month > 12:
        new_month = 1
        new_year += 1
    return {"year": new_year, "month": new_month}


def period_nav(selected_date: date, view_mode: str, delta: int) -> dict:
    if view_mode == "month":
        target = date(selected_date.year, selected_date.month, 15)
        shifted = shift_month(target, delta)
        day = min(selected_date.day, calendar.monthrange(shifted.year, shifted.month)[1])
        target_date = date(shifted.year, shifted.month, day)
    else:
        target_date = selected_date + timedelta(days=7 * delta)
    return {
        "year": target_date.year,
        "month": target_date.month,
        "day": target_date.day,
        "view": view_mode,
    }


def shift_month(base: date, delta: int) -> date:
    month = base.month + delta
    year = base.year
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def build_month_pdf(year: int, month: int):
    month_entries = fetch_month_entries(year, month)
    _, days_in_month = calendar.monthrange(year, month)
    month_actual = 0
    month_balance = 0
    week_sections: list[dict] = []
    current_week_key: tuple[int, int] | None = None
    current_week_actual = 0
    current_week_balance = 0
    current_week_rows: list[list[str]] = []
    current_week_highlights: list[tuple[int, str]] = []
    current_week_range = ""

    def start_week(week_number: int, week_start: date) -> None:
        nonlocal current_week_rows, current_week_highlights, current_week_range
        week_end = min(week_start + timedelta(days=6), date(year, month, days_in_month))
        current_week_rows = []
        current_week_highlights = []
        current_week_range = f"{week_start.strftime('%d.%m.')} - {week_end.strftime('%d.%m.%Y')}"

    def finish_week(week_number: int) -> None:
        week_sections.append(
            {
                "label": f"KW {week_number:02d}",
                "range": current_week_range,
                "rows": list(current_week_rows),
                "highlights": list(current_week_highlights),
                "actual": format_minutes(current_week_actual),
                "balance": format_minutes(current_week_balance),
            }
        )

    for day_number in range(1, days_in_month + 1):
        current = date(year, month, day_number)
        week_key = (current.isocalendar().year, current.isocalendar().week)
        if current_week_key is None:
            start_week(week_key[1], current)
        elif week_key != current_week_key:
            finish_week(current_week_key[1])
            current_week_actual = 0
            current_week_balance = 0
            start_week(week_key[1], current)

        entry = month_entries.get(current.isoformat())
        shift_type = entry["shift_type"] if entry else default_type_for(current)
        segments = (entry["segments"] if entry else []) or []
        totals = calculate_totals(
            shift_type,
            (entry["start_time"] if entry else "") or "",
            (entry["end_time"] if entry else "") or "",
            segments,
        )
        aggregate_balance = 0 if shift_type == "Notdienst" and current.weekday() >= 5 else totals.balance
        month_actual += totals.actual
        month_balance += aggregate_balance
        current_week_actual += totals.actual
        current_week_balance += aggregate_balance
        current_week_key = week_key
        day_segments = segments if shift_type == "Notdienst" and segments else [{"start": (entry["start_time"] if entry else "") or "-", "end": (entry["end_time"] if entry else "") or "-"}]
        notes_value = (entry["notes"] if entry else "") or "-"
        for segment_index, segment in enumerate(day_segments):
            segment_actual = totals.actual
            segment_balance = totals.balance
            if shift_type == "Notdienst":
                start_minutes = parse_time(segment.get("start") or "")
                end_minutes = parse_time(segment.get("end") or "")
                if start_minutes is None or end_minutes is None or end_minutes < start_minutes:
                    segment_actual = 0
                    segment_balance = 0
                else:
                    segment_actual = end_minutes - start_minutes
                    segment_balance = segment_actual
            current_week_rows.append(
                [
                    f"{WEEKDAY_SHORT[current.weekday()]} {current.strftime('%d.%m.%Y')}" if segment_index == 0 else "",
                    segment.get("start") or "-",
                    segment.get("end") or "-",
                    format_minutes(segment_actual) if shift_type == "Notdienst" or segment_index == 0 else "",
                    format_minutes(segment_balance) if shift_type == "Notdienst" or segment_index == 0 else "",
                    notes_value if segment_index == 0 else "",
                ]
            )
            if shift_type in {"Urlaub", "Krank", "Arztkrank", "Feiertag", "Notdienst"}:
                current_week_highlights.append((len(current_week_rows) - 1, shift_type))

    if current_week_key is not None:
        finish_week(current_week_key[1])

    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=12 * mm, leftMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    styles = getSampleStyleSheet()
    styles["Title"].fontName = "Helvetica-Bold"
    styles["Heading3"].fontName = "Helvetica-Bold"
    story = [
        Paragraph(f"Zeiterfassung {MONTH_NAMES[month - 1]} {year}", styles["Title"]),
        Spacer(1, 6),
        Paragraph("Monatsuebersicht im Hochformat mit klar getrennten Kalenderwochen.", styles["BodyText"]),
        Spacer(1, 14),
    ]
    highlight_colors = {
        "Notdienst": colors.HexColor("#E9D8FF"),
        "Urlaub": colors.HexColor("#E3F5D8"),
        "Krank": colors.HexColor("#FFF2B8"),
        "Arztkrank": colors.HexColor("#FFD8AE"),
        "Feiertag": colors.HexColor("#FFD9D6"),
    }

    def make_week_table(section: dict) -> Table:
        week_data = [["Datum", "Beginn", "Ende", "Ist", "Saldo", "Notiz"]] + section["rows"] + [["Wochensumme", "", "", section["actual"], section["balance"], ""]]
        table = Table(week_data, colWidths=[33 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm, 71 * mm])
        commands = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#CFE0FF")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#16325C")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C9D7E6")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.3),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
            ("TOPPADDING", (0, 1), (-1, -1), 5),
            ("ALIGN", (1, 0), (-2, -1), "CENTER"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ALIGN", (-1, 1), (-1, -1), "LEFT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.HexColor("#FFFFFF"), colors.HexColor("#F9FBFE")]),
        ]
        week_summary_row = len(week_data) - 1
        commands.extend(
            [
                ("BACKGROUND", (0, week_summary_row), (-1, week_summary_row), colors.HexColor("#EEF4FF")),
                ("FONTNAME", (0, week_summary_row), (-1, week_summary_row), "Helvetica-Bold"),
                ("LINEABOVE", (0, week_summary_row), (-1, week_summary_row), 0.45, colors.HexColor("#B8CBE3")),
                ("BOTTOMPADDING", (0, week_summary_row), (-1, week_summary_row), 6),
                ("TOPPADDING", (0, week_summary_row), (-1, week_summary_row), 6),
            ]
        )
        for row_index, shift_type in section["highlights"]:
            commands.append(("BACKGROUND", (0, row_index + 1), (-1, row_index + 1), highlight_colors[shift_type]))
        table.setStyle(TableStyle(commands))
        return table

    def make_summary_table() -> Table:
        summary = [
            ["Monat gesamt", format_minutes(month_actual), format_minutes(month_balance)],
            ["", "", ""],
            ["Legende", "", ""],
            ["", "Notdienst", ""],
            ["", "Urlaub", ""],
            ["", "Krank", ""],
            ["", "Arztkrank", ""],
            ["", "Feiertag", ""],
        ]
        table = Table(summary, colWidths=[22 * mm, 42 * mm, 92 * mm])
        commands = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF3FF")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#F4F8FD")),
            ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
            ("SPAN", (0, 2), (-1, 2)),
            ("FONTSIZE", (0, 0), (-1, -1), 8.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (-1, 0), "LEFT"),
        ]
        legend_rows = {3: "Notdienst", 4: "Urlaub", 5: "Krank", 6: "Arztkrank", 7: "Feiertag"}
        for row_index, shift_type in legend_rows.items():
            commands.extend(
                [
                    ("BACKGROUND", (0, row_index), (0, row_index), highlight_colors[shift_type]),
                    ("BOX", (0, row_index), (0, row_index), 0.3, colors.HexColor("#B7C6D9")),
                    ("SPAN", (1, row_index), (2, row_index)),
                ]
            )
        table.setStyle(TableStyle(commands))
        return table

    for section in week_sections:
        story.append(KeepTogether([
            Paragraph(section["label"], styles["Heading3"]),
            Spacer(1, 2),
            Paragraph(section["range"], styles["BodyText"]),
            Spacer(1, 6),
            make_week_table(section),
            Spacer(1, 12),
        ]))

    story.append(Spacer(1, 6))
    story.append(make_summary_table())
    document.build(story)
    buffer.seek(0)
    return buffer


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
