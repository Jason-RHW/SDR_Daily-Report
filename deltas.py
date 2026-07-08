"""
Day-over-day KPI deltas, compared to the previous BUSINESS day - if
report_date is a Monday, "previous" means the prior Friday, not Sunday.
"""
from datetime import timedelta

METRICS = ["total_calls", "connection_rate", "samples", "conversion_rate", "active_hrs"]

UP_COLOR = "#059669"     # green - improvement (higher is better for all 5 of these metrics)
DOWN_COLOR = "#DC2626"   # red - decline
FLAT_COLOR = "#9CA3AF"   # gray - no change
NEW_COLOR = "#6B7280"    # gray - no baseline to compare against


def previous_business_day(d):
    """Walks back one day at a time until hitting a weekday (Mon-Fri)."""
    prev = d - timedelta(days=1)
    while prev.weekday() >= 5:  # 5=Saturday, 6=Sunday
        prev -= timedelta(days=1)
    return prev


def _delta_for_metric(current, previous):
    """NOTE: this is a relative percent change of the metric's own value
    (e.g. connection rate 40% -> 44% shows as "+10%", not "+4pp"). Flag
    if you actually want percentage-point change for the two rate
    metrics instead - easy to switch, just a different formula."""
    current = current or 0
    previous = previous or 0

    if previous == 0:
        if current == 0:
            return {"label": "0%", "pct": 0.0, "color": FLAT_COLOR, "direction": "flat"}
        return {"label": "New", "pct": None, "color": NEW_COLOR, "direction": "new"}

    pct = round(((current - previous) / previous) * 100, 1)
    if pct > 0:
        return {"label": f"+{pct}%", "pct": pct, "color": UP_COLOR, "direction": "up"}
    if pct < 0:
        return {"label": f"{pct}%", "pct": pct, "color": DOWN_COLOR, "direction": "down"}
    return {"label": "0%", "pct": 0.0, "color": FLAT_COLOR, "direction": "flat"}


def compute_kpi_deltas(current_kpis, previous_kpis):
    """Returns {metric_name: {"label", "pct", "color", "direction"}, ...}
    for each of the 5 tracked KPIs. previous_kpis=None means no baseline
    exists (e.g. the SDR wasn't active the prior business day) - shown
    as "New" rather than a misleading +/-100%."""
    if previous_kpis is None:
        return {m: {"label": "New", "pct": None, "color": NEW_COLOR, "direction": "new"} for m in METRICS}
    return {
        m: _delta_for_metric(current_kpis.get(m), previous_kpis.get(m))
        for m in METRICS
    }
