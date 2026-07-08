"""
Fetch Aircall call records for a given PST calendar day.

Single source of truth: the Aircall API. No Supabase, no HubSpot.
"""
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

AIRCALL_API_ID = os.environ["AIRCALL_API_ID"]
AIRCALL_API_TOKEN = os.environ["AIRCALL_API_TOKEN"]
BASE_URL = "https://api.aircall.io/v1/calls"
PST = ZoneInfo("America/Los_Angeles")


def get_pst_day_bounds(target_date=None):
    """Return (from_ts, to_ts) unix timestamps for a full PST calendar day.
    Defaults to yesterday (PST), computed from PST wall-clock time -
    NOT the GitHub Actions runner's UTC clock."""
    now_pst = datetime.now(PST)
    if target_date is None:
        target_date = (now_pst - timedelta(days=1)).date()
    start = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=PST)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def fetch_calls_for_day(target_date=None):
    """Pull all Aircall calls for the given PST day, following pagination
    until meta.next_page_link is empty. Retries on 429 rate limits."""
    from_ts, to_ts = get_pst_day_bounds(target_date)
    calls = []
    page = 1

    while True:
        resp = requests.get(
            BASE_URL,
            auth=(AIRCALL_API_ID, AIRCALL_API_TOKEN),
            params={
                "from": from_ts,
                "to": to_ts,
                "per_page": 50,
                "page": page,
                "order": "asc",
            },
            timeout=30,
        )

        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 5))
            time.sleep(wait)
            continue

        resp.raise_for_status()
        data = resp.json()
        calls.extend(data.get("calls", []))

        next_link = (data.get("meta") or {}).get("next_page_link")
        if not next_link:
            break
        page += 1
        time.sleep(0.3)  # be polite to the API

    return calls


if __name__ == "__main__":
    result = fetch_calls_for_day()
    print(f"Fetched {len(result)} calls")
