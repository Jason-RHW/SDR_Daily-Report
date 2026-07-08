"""
Orchestrates the daily SDR report: fetch Aircall data -> compute KPIs ->
render HTML -> send via Gmail.

Usage:
  python send_report.py --dry-run   # sends everything to DRY_RUN_RECIPIENT
  python send_report.py             # sends to real SDRs + managers
"""
import argparse
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader

from fetch_calls import fetch_calls_for_day
from compute_kpis import compute_sdr_kpis, merge_samples
from fetch_samples_sheet import fetch_samples_by_sdr
from gmail_send import send_email
from sdr_config import SDR_SHORT, TERMINATED_SDRS

PST = ZoneInfo("America/Los_Angeles")
BASE_DIR = Path(__file__).parent
DRY_RUN_RECIPIENT = os.environ.get("DRY_RUN_RECIPIENT")

EMPTY_KPIS = {
    "total_calls": 0, "connection_rate": 0.0, "samples": 0,
    "conversion_rate": 0.0, "call_span_hrs": 0.0, "active_hrs": 0.0,
}


def load_sdr_config():
    with open(BASE_DIR / "sdrs.json") as f:
        return json.load(f)


def default_report_date():
    return (datetime.now(PST) - timedelta(days=1)).date()


def parse_report_date(raw_date):
    try:
        return date.fromisoformat(raw_date)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be in YYYY-MM-DD format") from exc


def main(dry_run: bool, report_date=None):
    if report_date is None:
        report_date = default_report_date()

    calls = fetch_calls_for_day(target_date=report_date)
    aircall_kpis_by_sdr = compute_sdr_kpis(calls)
    samples_by_sdr = fetch_samples_by_sdr(target_date=report_date)
    kpis_by_sdr = merge_samples(aircall_kpis_by_sdr, samples_by_sdr)

    env = Environment(loader=FileSystemLoader(BASE_DIR / "templates"))
    sdr_template = env.get_template("sdr_email.html")
    manager_template = env.get_template("manager_email.html")

    sdr_config = load_sdr_config()
    active_sdrs = [
        sdr for sdr in sdr_config["sdrs"]
        if sdr["name"] not in TERMINATED_SDRS
    ]

    # --- Per-SDR emails ---
    for sdr in active_sdrs:
        name = sdr["name"]
        kpis = kpis_by_sdr.get(name, EMPTY_KPIS)
        display_name = SDR_SHORT.get(name, name)
        html = sdr_template.render(sdr_name=display_name, date=report_date.isoformat(), kpis=kpis)
        recipient = DRY_RUN_RECIPIENT if dry_run else sdr["email"]
        send_email(recipient, f"Your Daily Performance — {report_date}", html)

    # --- Manager rollup ---
    leaderboard = [
        {"name": sdr["name"], **kpis_by_sdr.get(sdr["name"], EMPTY_KPIS)}
        for sdr in active_sdrs
    ]
    leaderboard.sort(key=lambda r: r["total_calls"], reverse=True)

    manager_html = manager_template.render(date=report_date.isoformat(), leaderboard=leaderboard)
    manager_recipients = [DRY_RUN_RECIPIENT] if dry_run else sdr_config["managers"]
    for recipient in manager_recipients:
        send_email(recipient, f"Team Daily Performance — {report_date}", manager_html)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                         help="Send everything to DRY_RUN_RECIPIENT instead of real recipients")
    parser.add_argument(
        "--date",
        type=parse_report_date,
        default=None,
        help="PST report date to run, in YYYY-MM-DD format. Defaults to yesterday.",
    )
    args = parser.parse_args()

    if args.dry_run and not DRY_RUN_RECIPIENT:
        raise SystemExit("DRY_RUN_RECIPIENT env var must be set for --dry-run")

    main(dry_run=args.dry_run, report_date=args.date)
