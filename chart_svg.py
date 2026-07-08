"""
Generates raw SVG markup for donut charts and the radial activity clock.
Pure SVG (no JS) so these render in Gmail, Apple Mail, and most webmail
clients. Note: classic Outlook desktop (Windows) does not render inline
SVG at all - flagged separately, not handled here.
"""
import math
from datetime import datetime
from zoneinfo import ZoneInfo

PST = ZoneInfo("America/Los_Angeles")


def _polar(cx, cy, r, angle_deg):
    rad = math.radians(angle_deg - 90)
    return cx + r * math.cos(rad), cy + r * math.sin(rad)


def _arc_path(cx, cy, r, start_angle, end_angle):
    start = _polar(cx, cy, r, start_angle)
    end = _polar(cx, cy, r, end_angle)
    large_arc = 1 if (end_angle - start_angle) > 180 else 0
    return (
        f"M {start[0]:.2f} {start[1]:.2f} "
        f"A {r:.2f} {r:.2f} 0 {large_arc} 1 {end[0]:.2f} {end[1]:.2f}"
    )


def donut_chart_svg(segments, size=150, thickness=20, center_value=None, center_label=None,
                     delta_text=None, delta_color=None):
    """segments: list of {"value": number, "color": "#hex"}. If delta_text
    is given, renders a small colored line below the label (e.g. "+10%")."""
    cx = cy = size / 2
    r = (size - thickness) / 2 - 2
    total = sum(s["value"] for s in segments) or 1
    non_zero = [s for s in segments if s["value"] > 0]
    gap = 2.0 if len(non_zero) > 1 else 0.0

    parts = [f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">']
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#F0F1F3" stroke-width="{thickness}"/>')

    cum_angle = 0.0
    for seg in segments:
        value = seg["value"]
        span = (value / total) * 360
        if value > 0:
            start_angle = cum_angle + gap / 2
            end_angle = cum_angle + span - gap / 2
            if end_angle > start_angle:
                d = _arc_path(cx, cy, r, start_angle, end_angle)
                parts.append(
                    f'<path d="{d}" fill="none" stroke="{seg["color"]}" '
                    f'stroke-width="{thickness}" stroke-linecap="butt"/>'
                )
        cum_angle += span

    # Vertical layout shifts up slightly when a delta badge is present,
    # to keep the whole 3-line stack centered rather than overflowing down.
    value_y = cy - (9 if delta_text else 3)
    label_y = cy + (11 if delta_text else 15)
    delta_y = cy + 27

    if center_value is not None:
        parts.append(
            f'<text x="{cx}" y="{value_y}" text-anchor="middle" font-family="Arial, sans-serif" '
            f'font-size="{size * 0.19:.0f}" font-weight="bold" fill="#111827">{center_value}</text>'
        )
    if center_label:
        parts.append(
            f'<text x="{cx}" y="{label_y}" text-anchor="middle" font-family="Arial, sans-serif" '
            f'font-size="{size * 0.08:.0f}" fill="#6B7280">{center_label}</text>'
        )
    if delta_text:
        parts.append(
            f'<text x="{cx}" y="{delta_y}" text-anchor="middle" font-family="Arial, sans-serif" '
            f'font-size="{size * 0.09:.0f}" font-weight="bold" fill="{delta_color or "#6B7280"}">{delta_text}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def _hour_angle(ts):
    """Angle in degrees on a 12-hour dial (0 = 12 o'clock, clockwise)."""
    dt = datetime.fromtimestamp(ts, tz=PST)
    hour_12 = (dt.hour % 12) + dt.minute / 60 + dt.second / 3600
    return hour_12 * 30  # 360 deg / 12 hr


def _fmt_time(ts):
    dt = datetime.fromtimestamp(ts, tz=PST)
    return dt.strftime("%-I:%M %p")


def clock_chart_svg(span_start, span_end, active_chunks, chunk_seconds=900, size=190):
    """12-hour analog clock face with an activity ring: green arcs for
    active 15-min chunks, orange for idle gaps, drawn only across the
    SDR's actual call span. Assumes a span of 12 hours or less (typical
    workday) - a longer span will visually wrap around the dial."""
    cx = cy = size / 2
    face_r = size / 2 - 4
    ring_r = face_r - 16
    thickness = 13

    parts = [f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">']

    # clock face
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{face_r}" fill="#FAFAFB" stroke="#E5E7EB" stroke-width="1"/>')

    # hour ticks + numbers
    for h in range(12):
        angle = h * 30
        x1, y1 = _polar(cx, cy, face_r - 3, angle)
        x2, y2 = _polar(cx, cy, face_r - 7, angle)
        parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#D1D5DB" stroke-width="1"/>')
        label = 12 if h == 0 else h
        lx, ly = _polar(cx, cy, ring_r - 12, angle)
        parts.append(
            f'<text x="{lx:.1f}" y="{ly + 3:.1f}" text-anchor="middle" '
            f'font-family="Arial, sans-serif" font-size="9" fill="#9CA3AF">{label}</text>'
        )

    # background ring
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{ring_r}" fill="none" stroke="#F0F1F3" stroke-width="{thickness}"/>')

    # activity arcs
    if span_start and span_end and active_chunks:
        for i, is_active in enumerate(active_chunks):
            chunk_start = span_start + i * chunk_seconds
            chunk_end = chunk_start + chunk_seconds
            a1 = _hour_angle(chunk_start)
            a2 = _hour_angle(chunk_end)
            if a2 <= a1:
                a2 += 360  # wrap safeguard
            color = "#059669" if is_active else "#D97706"
            d = _arc_path(cx, cy, ring_r, a1, a2)
            parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{thickness}" stroke-linecap="butt"/>')

        # start/end markers
        for ts in (span_start, span_end):
            angle = _hour_angle(ts)
            mx, my = _polar(cx, cy, ring_r, angle)
            parts.append(f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="3.2" fill="#111827"/>')

    parts.append("</svg>")
    return "".join(parts)
