"""
Compute per-SDR daily KPIs from raw Aircall call records.

KPI definitions (confirmed with Jason):
  - total_calls:      all call records attributed to the SDR that day
  - connection_rate:  calls carrying any tag in CONNECTED_TAGS / total_calls
                       (tag-based, not answered_at)
  - call_types:       partitions total_calls into connected / voicemail / other
                       (voicemail = any tag containing "Voicemail", checked
                       before connected tags since it's a distinct outcome)
  - call_span_hrs:    hours between the SDR's first call start and last call end
  - active_hrs:       call_span broken into 15-min chunks; a chunk counts as
                       active if any call overlaps it; sum of active chunks
  - active_chunks:    the raw per-chunk active/idle mask (for the clock chart)

NOTE: "samples" / "sample_businesses" / "conversion_rate" are NOT computed
here. They come from the Sample Google Sheet (see fetch_samples_sheet.py),
deliberately independent of Aircall's "Send Sample" tag - see
merge_samples() for where the two data sources come together.
"""
from collections import defaultdict

from sdr_config import AIRCALL_USER_MAP, CONNECTED_TAGS, TERMINATED_SDRS

CHUNK_SECONDS = 15 * 60


def _call_tags(call):
    return {t.get("name") for t in (call.get("tags") or [])}


def _sdr_name(call):
    """Normalize Aircall's raw user name to the canonical SDR name.
    Anything not in AIRCALL_USER_MAP falls into 'Unassigned (...)' so
    it's visible instead of silently mis-bucketed. Calls attributed to
    a TERMINATED_SDR also get rerouted here - see sdr_config.py for why
    that's a safety net, not a real fix."""
    user = call.get("user") or {}
    raw_name = user.get("name")
    if not raw_name:
        return "Unassigned"
    canonical = AIRCALL_USER_MAP.get(raw_name, f"Unassigned ({raw_name})")
    if canonical in TERMINATED_SDRS:
        return f"Unassigned (misattributed to departed SDR: {canonical})"
    return canonical


def _call_type(call):
    """Partitions a call into exactly one of: connected / voicemail / other."""
    tags = _call_tags(call)
    if any("voicemail" in t.lower() for t in tags):
        return "voicemail"
    if tags & CONNECTED_TAGS:
        return "connected"
    return "other"


def compute_sdr_kpis(calls):
    """Returns {sdr_name: {kpi_name: value, ...}, ...}"""
    by_sdr = defaultdict(list)
    for call in calls:
        by_sdr[_sdr_name(call)].append(call)

    results = {}
    for sdr, sdr_calls in by_sdr.items():
        total = len(sdr_calls)

        type_counts = {"connected": 0, "voicemail": 0, "other": 0}
        for c in sdr_calls:
            type_counts[_call_type(c)] += 1

        starts = [c.get("started_at") for c in sdr_calls if c.get("started_at")]
        ends = [c.get("ended_at") for c in sdr_calls if c.get("ended_at")]

        if starts and ends:
            span_start = min(starts)
            span_end = max(ends)
            call_span_hrs = round((span_end - span_start) / 3600, 2)
            active_hrs, active_chunks = _compute_active_hours(sdr_calls, span_start, span_end)
        else:
            span_start = span_end = None
            call_span_hrs = 0.0
            active_hrs = 0.0
            active_chunks = []

        results[sdr] = {
            "total_calls": total,
            "connection_rate": round(type_counts["connected"] / total, 3) if total else 0.0,
            "call_types": type_counts,
            "call_span_hrs": call_span_hrs,
            "active_hrs": active_hrs,
            "span_start": span_start,
            "span_end": span_end,
            "active_chunks": active_chunks,
        }
    return results


def merge_samples(aircall_kpis_by_sdr, samples_by_sdr):
    """Merges Sheet-sourced sample data into the Aircall-derived KPI dict.
    samples_by_sdr comes from fetch_samples_sheet.fetch_samples_by_sdr():
    {sdr_name: [{"business_name": ...}, ...]}.

    Deliberately mixes sources for conversion_rate (Sheet samples / Aircall
    calls) - confirmed with Jason this is intentional, not an oversight."""
    merged = {}
    all_sdrs = set(aircall_kpis_by_sdr) | set(samples_by_sdr)
    for sdr in all_sdrs:
        kpis = dict(aircall_kpis_by_sdr.get(sdr, {
            "total_calls": 0, "connection_rate": 0.0,
            "call_types": {"connected": 0, "voicemail": 0, "other": 0},
            "call_span_hrs": 0.0, "active_hrs": 0.0,
            "span_start": None, "span_end": None, "active_chunks": [],
        }))
        businesses = samples_by_sdr.get(sdr, [])
        kpis["sample_businesses"] = businesses
        kpis["samples"] = len(businesses)
        kpis["conversion_rate"] = (
            round(kpis["samples"] / kpis["total_calls"], 3) if kpis["total_calls"] else 0.0
        )
        merged[sdr] = kpis
    return merged


def determine_active_roster(aircall_kpis_by_sdr, samples_by_sdr):
    """Who actually gets a report today: anyone with Aircall calls OR
    Sheet sample submissions, EXCLUDING the "Unassigned (...)" catch-all
    buckets (those are a data-quality signal to look into, not a person
    to email). Deliberately NOT the static SDR_NAMES list - so someone
    who's left the team stops appearing on their own once they have no
    activity, without anyone needing to remember to update a roster file.
    """
    all_names = set(aircall_kpis_by_sdr) | set(samples_by_sdr)
    active = sorted(
        n for n in all_names
        if not n.startswith("Unassigned") and n not in TERMINATED_SDRS
    )

    unassigned = [n for n in all_names if n.startswith("Unassigned")]
    if unassigned:
        print(f"WARNING: unmatched names present in today's data, not sent a report: {unassigned}")
        print("These likely need adding to AIRCALL_USER_MAP or SHEET_OWNER_MAP.")

    return active


def _compute_active_hours(calls, span_start, span_end):
    """Break [span_start, span_end] into 15-min chunks. A chunk is active if
    any call's occupied window (started_at/answered_at -> ended_at) overlaps
    it. Returns (active_hrs, active_chunks_mask)."""
    n_chunks = int((span_end - span_start) // CHUNK_SECONDS) + 1
    active = [False] * n_chunks

    for c in calls:
        c_start = c.get("started_at") or c.get("answered_at")
        c_end = c.get("ended_at") or c_start
        if not c_start:
            continue
        first_chunk = int((c_start - span_start) // CHUNK_SECONDS)
        last_chunk = int((c_end - span_start) // CHUNK_SECONDS)
        for i in range(max(0, first_chunk), min(n_chunks, last_chunk + 1)):
            active[i] = True

    active_hrs = round(sum(active) * CHUNK_SECONDS / 3600, 2)
    return active_hrs, active
