"""
Turns raw KPI numbers into render-ready values for the email templates:
SVG chart markup + legend data, precomputed here since Jinja can't do
the trig needed for donut/clock arcs.
"""
import base64
from pathlib import Path

from chart_svg import donut_chart_svg, clock_chart_svg, _fmt_time
from deltas import compute_kpi_deltas

BASE_DIR = Path(__file__).parent

NAVY = "#223B89"
RED = "#B62523"
GRAY = "#9CA3AF"
TEAL = "#0F9B8E"
AMBER = "#D97706"
PURPLE = "#6D28D9"

# Connected / Voicemail / Other - consistent across SDR + manager views
CALL_TYPE_COLORS = {"connected": NAVY, "voicemail": AMBER, "other": GRAY}
CALL_TYPE_LABELS = {"connected": "Connected", "voicemail": "Voicemail", "other": "Other"}

# Distinct per-SDR palette for the manager's team composition donut
SDR_PALETTE = [NAVY, RED, TEAL, AMBER, PURPLE]


def get_logo_data_uri():
    logo_path = BASE_DIR / "assets" / "logo.png"
    data = base64.b64encode(logo_path.read_bytes()).decode()
    return f"data:image/png;base64,{data}"


def _call_type_legend(type_counts, total):
    legend = []
    for key in ("connected", "voicemail", "other"):
        count = type_counts.get(key, 0)
        pct = round((count / total) * 100, 1) if total else 0.0
        legend.append({
            "label": CALL_TYPE_LABELS[key],
            "count": count,
            "pct": pct,
            "color": CALL_TYPE_COLORS[key],
        })
    return legend


def _build_clock_package(kpis, size=190):
    svg = clock_chart_svg(
        span_start=kpis["span_start"],
        span_end=kpis["span_end"],
        active_chunks=kpis["active_chunks"],
        size=size,
    )
    if kpis["span_start"] and kpis["span_end"]:
        start_str = _fmt_time(kpis["span_start"])
        end_str = _fmt_time(kpis["span_end"])
    else:
        start_str = end_str = "--"
    idle_hrs = round(kpis["call_span_hrs"] - kpis["active_hrs"], 2)
    return {"svg": svg, "start_time_str": start_str, "end_time_str": end_str, "idle_hrs": idle_hrs}


def compute_team_summary(kpis_by_sdr, sdr_order):
    """Team-level aggregate using the same canonical metric names as a
    per-SDR kpis dict (total_calls, connection_rate, samples,
    conversion_rate, active_hrs) - so compute_kpi_deltas() works
    unmodified on both SDR-level and team-level dicts."""
    rows = [kpis_by_sdr[name] for name in sdr_order if name in kpis_by_sdr]
    total_calls = sum(r["total_calls"] for r in rows)
    total_samples = sum(r["samples"] for r in rows)
    total_active_hrs = round(sum(r["active_hrs"] for r in rows), 1)
    avg_connection_rate = (
        round(sum(r["connection_rate"] for r in rows) / len(rows), 3) if rows else 0.0
    )
    avg_conversion_rate = (
        round(sum(r["conversion_rate"] for r in rows) / len(rows), 3) if rows else 0.0
    )
    return {
        "total_calls": total_calls,
        "connection_rate": avg_connection_rate,
        "samples": total_samples,
        "conversion_rate": avg_conversion_rate,
        "active_hrs": total_active_hrs,
    }


def build_sdr_view(kpis, previous_kpis=None):
    """Adds donut + clock SVGs, legends, and day-over-day deltas to a
    single SDR's KPI dict. previous_kpis is that same SDR's merged kpis
    dict from the prior business day, or None if they had no activity
    that day (shown as "New" rather than a misleading delta)."""
    view = dict(kpis)
    total = kpis["total_calls"]
    type_counts = kpis["call_types"]

    deltas = compute_kpi_deltas(kpis, previous_kpis)
    view["deltas"] = deltas

    view["donut_svg"] = donut_chart_svg(
        segments=[
            {"value": type_counts["connected"], "color": CALL_TYPE_COLORS["connected"]},
            {"value": type_counts["voicemail"], "color": CALL_TYPE_COLORS["voicemail"]},
            {"value": type_counts["other"], "color": CALL_TYPE_COLORS["other"]},
        ],
        size=150,
        thickness=20,
        center_value=total,
        center_label="Total Calls",
        delta_text=deltas["total_calls"]["label"],
        delta_color=deltas["total_calls"]["color"],
    )
    view["call_type_legend"] = _call_type_legend(type_counts, total)

    clock_pkg = _build_clock_package(kpis, size=190)
    view["clock_svg"] = clock_pkg["svg"]
    view["start_time_str"] = clock_pkg["start_time_str"]
    view["end_time_str"] = clock_pkg["end_time_str"]
    view["idle_hrs"] = clock_pkg["idle_hrs"]

    # Sourced from the Sample Sheet (fetch_samples_sheet.py), not Aircall -
    # just business names, no call-time data available from that source.
    view["sample_businesses"] = kpis.get("sample_businesses", [])

    return view


def build_manager_view(kpis_by_sdr, sdr_order, previous_kpis_by_sdr=None):
    """Builds the team summary strip, team composition donut, and
    per-SDR mini donut cards, in a fixed SDR display order.
    previous_kpis_by_sdr is the same shape as kpis_by_sdr but for the
    prior business day - used for the team-level delta badges."""
    rows = []
    for name in sdr_order:
        k = kpis_by_sdr.get(name)
        if not k:
            continue
        rows.append({"name": name, **k})

    rows.sort(key=lambda r: r["total_calls"], reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
        r["accent_color"] = SDR_PALETTE[i % len(SDR_PALETTE)]

    summary = compute_team_summary(kpis_by_sdr, sdr_order)

    previous_summary = None
    if previous_kpis_by_sdr is not None:
        # Use the same day's active SDR order for the previous summary too,
        # falling back gracefully via compute_team_summary's own filtering
        # of names present in previous_kpis_by_sdr.
        previous_summary = compute_team_summary(previous_kpis_by_sdr, list(previous_kpis_by_sdr.keys()))

    summary["deltas"] = compute_kpi_deltas(summary, previous_summary)

    # Team composition donut: one segment per SDR, sized by total_calls
    team_segments = [
        {"value": r["total_calls"], "color": r["accent_color"]}
        for r in rows
    ]
    team_donut_svg = donut_chart_svg(
        segments=team_segments,
        size=170,
        thickness=24,
        center_value=summary["total_calls"],
        center_label="Team Calls",
        delta_text=summary["deltas"]["total_calls"]["label"],
        delta_color=summary["deltas"]["total_calls"]["color"],
    )
    total_calls = summary["total_calls"]
    team_legend = [
        {
            "name": r["name"],
            "count": r["total_calls"],
            "pct": round((r["total_calls"] / total_calls) * 100, 1) if total_calls else 0.0,
            "color": r["accent_color"],
        }
        for r in rows
    ]

    # Per-SDR mini donuts + clocks: connected/voicemail/other breakdown
    # and call-span activity, same info as the individual email - plus
    # day-over-day deltas for each SDR's own row.
    for r in rows:
        type_counts = r["call_types"]
        previous_row = previous_kpis_by_sdr.get(r["name"]) if previous_kpis_by_sdr is not None else None
        r["deltas"] = compute_kpi_deltas(r, previous_row)

        r["mini_donut_svg"] = donut_chart_svg(
            segments=[
                {"value": type_counts["connected"], "color": CALL_TYPE_COLORS["connected"]},
                {"value": type_counts["voicemail"], "color": CALL_TYPE_COLORS["voicemail"]},
                {"value": type_counts["other"], "color": CALL_TYPE_COLORS["other"]},
            ],
            size=110,
            thickness=15,
            center_value=r["total_calls"],
            center_label="Total Calls",
            delta_text=r["deltas"]["total_calls"]["label"],
            delta_color=r["deltas"]["total_calls"]["color"],
        )
        r["call_type_legend"] = _call_type_legend(type_counts, r["total_calls"])

        clock_pkg = _build_clock_package(r, size=120)
        r["clock_svg"] = clock_pkg["svg"]
        r["start_time_str"] = clock_pkg["start_time_str"]
        r["end_time_str"] = clock_pkg["end_time_str"]
        r["idle_hrs"] = clock_pkg["idle_hrs"]

    return summary, rows, team_donut_svg, team_legend
