"""
Pulls today's sample-request form submissions from the Sample Google Sheet.
This is now the single source of truth for "# Samples" and the business-name
reconciliation list in the SDR report - deliberately NOT derived from
Aircall's "Send Sample" tag, so a missed form shows up as a gap between
what the SDR remembers doing and what's actually logged here.

Reuses the same OAuth app/refresh token as email_to_sheets.py, which
already writes to Sheets - so it already carries Sheets scope.
"""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from sdr_config import SDR_NAMES, TERMINATED_SDRS

PST = ZoneInfo("America/Los_Angeles")

SHEET_ID = "1ehyBGdfJ2TVMVRo28ObskWACQbdr2D4ON9eC8QvEaY4"
# Tab name assumed from gid=0 in the sheet URL (usually "Sheet1") - confirm
# this matches the actual tab name before relying on it.
SHEET_RANGE = "Sheet1!A:AI"

COL_BUSINESS_NAME = "Business Name"
COL_SALES_OWNER = "Sales Owner"
COL_FORM_SUBMITTED_AT = "Form Submiited At"  # typo is in the actual sheet header

# Maps a Sheet "Sales Owner" value -> canonical SDR name from sdr_config.SDR_NAMES.
# Confirmed with Jason: Lorenzo Bamiano (sheet) == Lhoreto Bamiano (Aircall/roster).
SHEET_OWNER_MAP = {
    "Maria Palmares": "Maria Gladys Palmares",
    "Lorenzo Bamiano": "Lhoreto Bamiano",
    "Harhel Grace Manansala": "Harhel Grace Manansala",
    "Grace Manansala": "Harhel Grace Manansala",
    "Basilio Asuncion": "Basilio Asuncion",
    "Bash Asuncion": "Basilio Asuncion",
    "Stephanie Ong": "Stephanie Ong",
}


def _parse_sheet_date(raw_value):
    """The Sheets API returns dates formatted however that column happens
    to be configured (7/6/2026, 2026-07-06, Jul 6 2026, etc.) - NOT
    guaranteed to match any one string format. Parse flexibly rather than
    comparing strings directly; returns a date object or None if the cell
    is blank/unparseable."""
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return None
    try:
        return date_parser.parse(raw_value).date()
    except (ValueError, OverflowError):
        return None


def _get_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("sheets", "v4", credentials=creds)


def fetch_samples_by_sdr(target_date=None):
    """Returns {sdr_name: [{"business_name": ...}, ...], ...} for every
    row submitted on target_date (defaults to today, PST). SDRs with no
    submissions still get an empty list, not a missing key."""
    if target_date is None:
        target_date = datetime.now(PST).date()

    service = _get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=SHEET_RANGE
    ).execute()
    rows = result.get("values", [])

    by_sdr = {name: [] for name in SDR_NAMES if name not in TERMINATED_SDRS}
    if not rows:
        print("WARNING: Sample Sheet returned zero rows - check SHEET_RANGE/tab name.")
        return by_sdr

    header = rows[0]
    col_idx = {name: i for i, name in enumerate(header)}
    for required in (COL_BUSINESS_NAME, COL_SALES_OWNER, COL_FORM_SUBMITTED_AT):
        if required not in col_idx:
            print(f"WARNING: expected column '{required}' not found in sheet header: {header}")

    matched_count = 0
    unmatched_owners = set()

    for row in rows[1:]:
        def get(col):
            i = col_idx.get(col)
            return row[i] if i is not None and i < len(row) else ""

        row_date = _parse_sheet_date(get(COL_FORM_SUBMITTED_AT))
        if row_date != target_date:
            continue

        owner_raw = get(COL_SALES_OWNER).strip()
        owner = SHEET_OWNER_MAP.get(owner_raw)
        if owner is None:
            owner = f"Unassigned ({owner_raw})" if owner_raw else "Unassigned"
            unmatched_owners.add(owner_raw)
        elif owner in TERMINATED_SDRS:
            owner = f"Unassigned (misattributed to departed SDR: {owner})"

        business = get(COL_BUSINESS_NAME).strip() or "(business name missing)"
        by_sdr.setdefault(owner, []).append({"business_name": business})
        matched_count += 1

    print(f"Sample Sheet: {matched_count} row(s) matched {target_date.isoformat()}.")
    if unmatched_owners:
        print(f"WARNING: unrecognized Sales Owner value(s), add to SHEET_OWNER_MAP: {unmatched_owners}")

    return by_sdr
