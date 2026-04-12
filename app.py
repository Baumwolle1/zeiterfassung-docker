import calendar
import io
import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, redirect, render_template, request, send_file, url_for
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


APP_TITLE = "Zeiterfassung"
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

SHIFT_CONFIG = {
    "Fruehschicht": {"label": "Fruehschicht", "target": 460, "break": 20, "start": "07:00", "end": "15:00"},
    "Spaetschicht": {"label": "Spaetschicht", "target": 420, "break": 0, "start": "12:00", "end": "19:00"},
    "Freitag": {"label": "Freitag", "target": 360, "break": 0, "start": "07:00", "end": "13:00"},
    "Urlaub": {"label": "Urlaub", "target": 0, "break": 0, "start": "", "end": ""},
    "Feiertag": {"label": "Feiertag", "target": 0, "break": 0, "start": "", "end": ""},
    "Frei": {"label": "Frei", "target": 0, "break": 0, "start": "", "end": ""},
}
WORK_TYPES = ("Fruehschicht", "Spaetschicht", "Freitag")
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ["DATA_DIR"]) if os.environ.get("DATA_DIR") else BASE_DIR / "data"
DB_PATH = DATA_DIR / "zeiterfassung.db"


@dataclass
class Totals:
    target: int
    actual: int
    balance: int
    deducted_break: int


def create_app() -> Flask:
    app = Flask(__name__)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    init_db()

    @app.context_processor
    def inject_globals():
        return {
            "app_title": APP_TITLE,
            "month_names": MONTH_NAMES,
            "weekday_names": WEEKDAY_NAMES,
            "shift_config": SHIFT_CONFIG,
            "format_minutes": format_minutes,
            "balance_class": balance_class,
        }

    @app.get("/")
    def index():
        today = date.today()
        year = int(request.args.get("year", today.year))
        month = int(request.args.get("month", today.month))
        month = max(1, min(month, 12))
        _, days_in_month = calendar.monthrange(year, month)

        selected_day = int(request.args.get("day", min(today.day, days_in_month)))
        selected_day = max(1, min(selected_day, days_in_month))
        selected_date = date(year, month, selected_day)

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
                }
            )

        entry = fetch_entry(selected_date)
        form_data = (
            entry
            if entry
            else {
                "shift_type": default_type_for(selected_date),
                "start_time": SHIFT_CONFIG[default_type_for(selected_date)]["start"],
                "end_time": SHIFT_CONFIG[default_type_for(selected_date)]["end"],
                "notes": "",
            }
        )
        selected_totals = calculate_totals(form_data["shift_type"], form_data["start_time"], form_data["end_time"])
        week_target, week_actual, month_target, month_actual = calculate_ranges(selected_date, month_entries, form_data)

        return render_template(
            "index.html",
            year=year,
            month=month,
            selected_date=selected_date,
            selected_day=selected_day,
            days=days,
            form_data=form_data,
            selected_totals=selected_totals,
            week_target=format_minutes(week_target),
            week_actual=format_minutes(week_actual),
            week_balance=format_minutes(week_actual - week_target),
            month_target=format_minutes(month_target),
            month_actual=format_minutes(month_actual),
            month_balance=format_minutes(month_actual - month_target),
            prev_month=month_nav(year, month, -1),
            next_month=month_nav(year, month, 1),
        )

    @app.post("/save")
    def save():
        year = int(request.form["year"])
        month = int(request.form["month"])
        day = int(request.form["day"])
        selected_date = date(year, month, day)

        shift_type = request.form["shift_type"]
        start_time = normalize_time(request.form.get("start_time", ""))
        end_time = normalize_time(request.form.get("end_time", ""))
        notes = request.form.get("notes", "").strip()

        if shift_type not in SHIFT_CONFIG:
            shift_type = default_type_for(selected_date)

        if shift_type not in WORK_TYPES:
            start_time = ""
            end_time = ""
        save_entry(selected_date, shift_type, start_time, end_time, notes)
        return redirect(url_for("index", year=year, month=month, day=day))

    @app.get("/export/pdf")
    def export_pdf():
        year = int(request.args.get("year", date.today().year))
        month = int(request.args.get("month", date.today().month))
        pdf_bytes = build_month_pdf(year, month)
        filename = f"Zeiterfassung_{year}_{month:02d}.pdf"
        return send_file(pdf_bytes, mimetype="application/pdf", as_attachment=True, download_name=filename)

    return app


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


def fetch_entry(day_value: date) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT shift_type, start_time, end_time, notes FROM entries WHERE entry_date = ?",
            (day_value.isoformat(),),
        ).fetchone()
    if not row:
        return None
    return {"shift_type": row[0], "start_time": row[1] or "", "end_time": row[2] or "", "notes": row[3] or ""}


def fetch_month_entries(year: int, month: int) -> dict[str, dict]:
    start = date(year, month, 1)
    _, days_in_month = calendar.monthrange(year, month)
    end = date(year, month, days_in_month)
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT entry_date, shift_type, start_time, end_time, notes FROM entries WHERE entry_date BETWEEN ? AND ?",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    return {
        row[0]: {"shift_type": row[1], "start_time": row[2] or "", "end_time": row[3] or "", "notes": row[4] or ""}
        for row in rows
    }


def save_entry(day_value: date, shift_type: str, start_time: str, end_time: str, notes: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO entries (entry_date, shift_type, start_time, end_time, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(entry_date) DO UPDATE SET
                shift_type = excluded.shift_type,
                start_time = excluded.start_time,
                end_time = excluded.end_time,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (day_value.isoformat(), shift_type, start_time, end_time, notes, datetime.now().isoformat(timespec="seconds")),
        )


def default_type_for(day_value: date) -> str:
    if day_value.weekday() == 4:
        return "Freitag"
    if day_value.weekday() >= 5:
        return "Frei"
    return "Fruehschicht"


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


def calculate_totals(shift_type: str, start_time: str, end_time: str) -> Totals:
    config = SHIFT_CONFIG[shift_type]
    if shift_type not in WORK_TYPES:
        return Totals(target=config["target"], actual=0, balance=0, deducted_break=0)

    start_minutes = parse_time(start_time)
    end_minutes = parse_time(end_time)
    if start_minutes is None or end_minutes is None or end_minutes < start_minutes:
        return Totals(target=config["target"], actual=0, balance=-config["target"], deducted_break=config["break"])

    worked = end_minutes - start_minutes
    actual = max(worked - config["break"], 0)
    return Totals(target=config["target"], actual=actual, balance=actual - config["target"], deducted_break=config["break"])


def calculate_ranges(selected_date: date, month_entries: dict[str, dict], selected_form: dict) -> tuple[int, int, int, int]:
    week_start = selected_date - timedelta(days=selected_date.weekday())
    week_end = week_start + timedelta(days=6)
    week_target = 0
    week_actual = 0
    cursor = week_start
    while cursor <= week_end:
        totals = totals_for_day(cursor, month_entries, selected_date, selected_form)
        week_target += totals.target
        week_actual += totals.actual
        cursor += timedelta(days=1)

    _, days_in_month = calendar.monthrange(selected_date.year, selected_date.month)
    month_target = 0
    month_actual = 0
    for day_number in range(1, days_in_month + 1):
        current = date(selected_date.year, selected_date.month, day_number)
        totals = totals_for_day(current, month_entries, selected_date, selected_form)
        month_target += totals.target
        month_actual += totals.actual
    return week_target, week_actual, month_target, month_actual


def totals_for_day(day_value: date, month_entries: dict[str, dict], selected_date: date, selected_form: dict) -> Totals:
    if day_value == selected_date:
        return calculate_totals(selected_form["shift_type"], selected_form["start_time"], selected_form["end_time"])
    entry = month_entries.get(day_value.isoformat())
    shift_type = entry["shift_type"] if entry else default_type_for(day_value)
    return calculate_totals(shift_type, (entry["start_time"] if entry else "") or "", (entry["end_time"] if entry else "") or "")


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


def build_month_pdf(year: int, month: int):
    month_entries = fetch_month_entries(year, month)
    _, days_in_month = calendar.monthrange(year, month)
    data = [["Datum", "Tag", "Typ", "Beginn", "Ende", "Soll", "Ist", "Saldo", "Notiz"]]
    month_target = 0
    month_actual = 0

    for day_number in range(1, days_in_month + 1):
        current = date(year, month, day_number)
        entry = month_entries.get(current.isoformat())
        shift_type = entry["shift_type"] if entry else default_type_for(current)
        totals = calculate_totals(shift_type, (entry["start_time"] if entry else "") or "", (entry["end_time"] if entry else "") or "")
        month_target += totals.target
        month_actual += totals.actual
        data.append(
            [
                current.strftime("%d.%m.%Y"),
                WEEKDAY_NAMES[current.weekday()],
                SHIFT_CONFIG[shift_type]["label"],
                (entry["start_time"] if entry else "") or "-",
                (entry["end_time"] if entry else "") or "-",
                format_minutes(totals.target),
                format_minutes(totals.actual),
                format_minutes(totals.balance),
                (entry["notes"] if entry else "") or "-",
            ]
        )

    data.append(["", "", "Monat gesamt", "", "", format_minutes(month_target), format_minutes(month_actual), format_minutes(month_actual - month_target), ""])

    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=12 * mm, leftMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"Zeiterfassung {MONTH_NAMES[month - 1]} {year}", styles["Title"]),
        Spacer(1, 8),
        Paragraph("Monatsuebersicht mit Soll-Ist-Auswertung.", styles["BodyText"]),
        Spacer(1, 10),
    ]
    table = Table(data, repeatRows=1, colWidths=[24 * mm, 25 * mm, 28 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm, 78 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE8FF")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EEF4FF")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BAC8D9")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.whitesmoke, colors.HexColor("#F8FAFD")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-2, -1), "CENTER"),
                ("ALIGN", (-1, 1), (-1, -1), "LEFT"),
            ]
        )
    )
    story.append(table)
    document.build(story)
    buffer.seek(0)
    return buffer


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
