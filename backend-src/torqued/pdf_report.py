"""Render a rich PDF report of a vehicle's full history.

Pure builder: callers assemble the data dicts (via the repositories) and pass
them in; this module owns only layout and returns the PDF as ``bytes``. Keeping
it side-effect free (apart from reading photo files off disk) makes it easy to
unit-test.
"""
import os
from datetime import date
from typing import Any

from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from torqued.units import PSI_PER_BAR, from_km

# Identity fields that fall back to the DVSA baseline when the column is unset,
# paired with the human label shown in the report.
_IDENTITY_FIELDS: list[tuple[str, str]] = [
    ("make", "Make"),
    ("model", "Model"),
    ("year", "Year"),
    ("registration", "Registration"),
    ("colour", "Colour"),
    ("fuel_type", "Fuel"),
    ("engine_size", "Engine size"),
]

_EMDASH = "—"
_ACCENT = colors.HexColor("#1f6feb")
_HEADER_BG = colors.HexColor("#f0f3f6")
_BORDER = colors.HexColor("#d0d7de")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "rt-title", parent=base["Title"], fontSize=22, spaceAfter=2, textColor=_ACCENT
        ),
        "subtitle": ParagraphStyle(
            "rt-subtitle", parent=base["Normal"], fontSize=10, textColor=colors.grey
        ),
        "h2": ParagraphStyle(
            "rt-h2", parent=base["Heading2"], fontSize=14, spaceBefore=14, spaceAfter=6
        ),
        "body": ParagraphStyle("rt-body", parent=base["Normal"], fontSize=9, leading=12),
        "small": ParagraphStyle(
            "rt-small", parent=base["Normal"], fontSize=8, leading=10, textColor=colors.grey
        ),
        "cell": ParagraphStyle("rt-cell", parent=base["Normal"], fontSize=8.5, leading=11),
    }
    return styles


def _fmt_distance(value_km: float | None, unit: str) -> str:
    """Format a stored km distance in the vehicle's display unit."""
    if value_km is None:
        return _EMDASH
    return f"{round(from_km(value_km, unit)):,} {unit}"


def _fmt_cost(value: Any) -> str:
    return f"£{float(value):,.2f}"


def _resolve(vehicle: dict[str, Any], baseline: dict[str, Any] | None, field: str) -> Any:
    """Apply the ``override ?? baseline`` rule used across the UI."""
    value = vehicle.get(field)
    if value is not None:
        return value
    return (baseline or {}).get(field)


def _section(styles: dict[str, ParagraphStyle], title: str) -> Paragraph:
    return Paragraph(title, styles["h2"])


def _kv_table(rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle]) -> Table:
    """A two-column label/value table."""
    data = [[Paragraph(f"<b>{label}</b>", styles["cell"]), Paragraph(value, styles["cell"])]
            for label, value in rows]
    table = Table(data, colWidths=[45 * mm, None])
    table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, _BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _grid_table(
    header: list[str], rows: list[list[str]], styles: dict[str, ParagraphStyle],
    col_widths: list[float | None] | None = None,
) -> Table:
    """A bordered table with a shaded header row."""
    head = [Paragraph(f"<b>{h}</b>", styles["cell"]) for h in header]
    body = [[Paragraph(c, styles["cell"]) for c in row] for row in rows]
    table = Table([head, *body], colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
                ("GRID", (0, 0), (-1, -1), 0.25, _BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _mileage_chart(mileage: list[dict[str, Any]], unit: str) -> Drawing:
    """A simple line plot of odometer readings over the timeline."""
    points = [(i, round(from_km(p["odometer_km"], unit))) for i, p in enumerate(mileage)]
    drawing = Drawing(440, 150)
    plot = LinePlot()
    plot.x, plot.y, plot.width, plot.height = 35, 25, 380, 110
    plot.data = [points]
    plot.lines[0].strokeColor = _ACCENT
    plot.lines[0].strokeWidth = 1.5
    plot.xValueAxis.valueMin = 0
    plot.xValueAxis.valueMax = len(points) - 1
    plot.xValueAxis.visible = False
    plot.yValueAxis.labelTextFormat = "%d"
    drawing.add(plot)
    return drawing


def _identity_section(
    story: list[Any], vehicle: dict[str, Any], baseline: dict[str, Any] | None,
    styles: dict[str, ParagraphStyle],
) -> None:
    rows = [(label, str(_resolve(vehicle, baseline, field) or _EMDASH))
            for field, label in _IDENTITY_FIELDS]
    rows.append(("VIN", str(vehicle.get("vin") or _EMDASH)))
    rows.append(("Purchase date", str(vehicle.get("purchase_date") or _EMDASH)))
    rows.append(("Odometer unit", vehicle.get("odometer_unit") or "mi"))
    if vehicle.get("notes"):
        rows.append(("Notes", str(vehicle["notes"])))
    story.append(_section(styles, "Vehicle details"))
    story.append(_kv_table(rows, styles))


def _tyres_section(
    story: list[Any], vehicle: dict[str, Any], styles: dict[str, ParagraphStyle]
) -> None:
    keys = (
        "tyre_size_front", "tyre_size_rear",
        "tyre_pressure_front_psi", "tyre_pressure_rear_psi",
    )
    if not any(vehicle.get(k) is not None for k in keys):
        return

    def pressure(psi: Any) -> str:
        if psi is None:
            return _EMDASH
        return f"{float(psi):g} psi / {float(psi) / PSI_PER_BAR:.1f} bar"

    rows = [
        ("Front size", str(vehicle.get("tyre_size_front") or _EMDASH)),
        ("Rear size", str(vehicle.get("tyre_size_rear") or _EMDASH)),
        ("Front pressure", pressure(vehicle.get("tyre_pressure_front_psi"))),
        ("Rear pressure", pressure(vehicle.get("tyre_pressure_rear_psi"))),
    ]
    story.append(_section(styles, "Tyres"))
    story.append(_kv_table(rows, styles))


def _specs_section(
    story: list[Any], vehicle: dict[str, Any], styles: dict[str, ParagraphStyle]
) -> None:
    specs = vehicle.get("specs") or []
    if not specs:
        return
    story.append(_section(styles, "Specifications"))
    story.append(_kv_table([(s["name"], str(s["value"])) for s in specs], styles))


_REMINDER_LABELS = {"overdue": "Overdue", "due_soon": "Due soon", "upcoming": "Upcoming"}


def _reminders_section(
    story: list[Any], reminders: list[dict[str, Any]], unit: str,
    styles: dict[str, ParagraphStyle],
) -> None:
    if not reminders:
        return
    rows = [
        [
            r.get("title") or _EMDASH,
            r.get("category") or _EMDASH,
            _REMINDER_LABELS.get(r["status"], r["status"]),
            r.get("next_due_date") or _EMDASH,
            _fmt_distance(r.get("next_due_km"), unit),
        ]
        for r in reminders
    ]
    story.append(_section(styles, "Open reminders"))
    story.append(_grid_table(["Title", "Category", "Status", "Due date", "Due at"], rows, styles))


def _mileage_section(
    story: list[Any], mileage: list[dict[str, Any]], unit: str,
    styles: dict[str, ParagraphStyle],
) -> None:
    if not mileage:
        return
    story.append(_section(styles, "Mileage timeline"))
    if len(mileage) >= 2:
        story.append(_mileage_chart(mileage, unit))
        story.append(Spacer(1, 4))
    rows = [
        [p.get("date") or _EMDASH, _fmt_distance(p.get("odometer_km"), unit),
         p.get("source") or _EMDASH, p.get("note") or ""]
        for p in mileage
    ]
    story.append(
        _grid_table(["Date", "Reading", "Source", "Note"], rows, styles,
                    col_widths=[28 * mm, 28 * mm, 22 * mm, None])
    )


def _services_section(
    story: list[Any], services: list[dict[str, Any]], unit: str,
    styles: dict[str, ParagraphStyle],
) -> None:
    story.append(_section(styles, f"Service history ({len(services)})"))
    if not services:
        story.append(Paragraph("No service records.", styles["small"]))
        return
    for log in services:
        title = f"<b>{log.get('date') or ''} — {log.get('title') or 'Service'}</b>"
        story.append(Paragraph(title, styles["body"]))
        meta = [
            log.get("category") or "uncategorised",
            f"by {log['performed_by']}" if log.get("performed_by") else None,
            _fmt_cost(log["cost"]) if log.get("cost") is not None else None,
            _fmt_distance(log["odometer_km"], unit) if log.get("odometer_km") is not None else None,
        ]
        story.append(Paragraph(" · ".join(m for m in meta if m), styles["small"]))
        if log.get("description"):
            story.append(Paragraph(str(log["description"]), styles["cell"]))
        for code in log.get("fault_codes") or []:
            if code.get("description"):
                text = f"<b>{code['code']}</b> — {code['description']} ({code['system']})"
            else:
                text = f"<b>{code['code']}</b>"
            story.append(Paragraph(text, styles["small"]))
        story.append(Spacer(1, 6))


def _mot_section(
    story: list[Any], mot: dict[str, Any] | None, styles: dict[str, ParagraphStyle]
) -> None:
    if not mot:
        return
    story.append(_section(styles, "MOT history (DVSA)"))
    summary = [
        ("Recall outstanding", str(mot.get("has_outstanding_recall") or _EMDASH)),
        ("MOT due", str(mot.get("mot_test_due_date") or _EMDASH)),
    ]
    story.append(_kv_table(summary, styles))
    story.append(Spacer(1, 6))
    for test in mot.get("tests") or []:
        odo = test.get("odometer_value")
        odo_text = f"{int(odo):,} {test.get('odometer_unit') or ''}".strip() if odo is not None \
            else _EMDASH
        head = (
            f"<b>{(test.get('completed_date') or '')[:10]} — "
            f"{test.get('test_result') or ''}</b>"
        )
        story.append(Paragraph(head, styles["body"]))
        story.append(
            Paragraph(
                f"Expiry {test.get('expiry_date') or _EMDASH} · Odometer {odo_text}",
                styles["small"],
            )
        )
        for defect in test.get("defects") or []:
            dtype = defect.get("type") or "DEFECT"
            danger = " ⚠ dangerous" if defect.get("dangerous") else ""
            story.append(
                Paragraph(f"[{dtype}] {defect.get('text') or ''}{danger}", styles["small"])
            )
        story.append(Spacer(1, 6))


def _photos_section(
    story: list[Any], photos: list[dict[str, Any]], photo_dir: str,
    styles: dict[str, ParagraphStyle],
) -> None:
    story.append(_section(styles, "Photos"))
    shown = 0
    max_w = 150 * mm
    for photo in photos:
        path = os.path.join(photo_dir, photo["filename"])
        try:
            # Decode eagerly so a missing/corrupt upload is skipped here rather
            # than blowing up later during doc.build().
            width, height = ImageReader(path).getSize()
        except Exception:
            continue
        if width > max_w:
            height = height * max_w / width
            width = max_w
        story.append(Image(path, width=width, height=height))
        caption = photo.get("caption") or photo.get("original_name") or ""
        if caption:
            story.append(Paragraph(caption, styles["small"]))
        story.append(Spacer(1, 8))
        shown += 1
    if shown == 0:
        story.append(Paragraph("No photos available.", styles["small"]))


def build_vehicle_report(
    vehicle: dict[str, Any],
    services: list[dict[str, Any]],
    mileage: list[dict[str, Any]],
    reminders: list[dict[str, Any]],
    mot: dict[str, Any] | None,
    *,
    include_photos: bool,
    photo_dir: str,
) -> bytes:
    """Assemble a vehicle's full history into a PDF and return the raw bytes."""
    from io import BytesIO

    styles = _styles()
    baseline = vehicle.get("mot_baseline")
    unit = vehicle.get("odometer_unit") or "mi"
    reg = _resolve(vehicle, baseline, "registration")

    story: list[Any] = []
    story.append(Paragraph(vehicle.get("name") or "Vehicle", styles["title"]))
    subtitle = " · ".join(
        part for part in [
            (vehicle.get("kind") or "").capitalize() or None,
            str(reg) if reg else None,
            vehicle.get("garage_name"),
            f"Generated {date.today().isoformat()}",
        ] if part
    )
    story.append(Paragraph(subtitle, styles["subtitle"]))

    _identity_section(story, vehicle, baseline, styles)
    _tyres_section(story, vehicle, styles)
    _specs_section(story, vehicle, styles)
    _reminders_section(story, reminders, unit, styles)
    _mileage_section(story, mileage, unit, styles)
    _services_section(story, services, unit, styles)
    _mot_section(story, mot, styles)
    if include_photos:
        _photos_section(story, vehicle.get("photos") or [], photo_dir, styles)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"{vehicle.get('name') or 'Vehicle'} report",
    )
    doc.build(story)
    return buffer.getvalue()
