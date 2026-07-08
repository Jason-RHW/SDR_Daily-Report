"""
Test-phase delivery: generates the long, unpaginated PDF for each SDR and
for the manager rollup, then emails each as a plain-text message with the
PDF attached - no HTML email body for now.

Everything routes to TEST_RECIPIENT below regardless of the real SDR/
manager email addresses in sdrs.json. Swap TEST_RECIPIENT for the real
per-SDR/manager routing (see send_report.py's HTML version for that
pattern) once this has been validated against a few real days of data.
"""
import argparse
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader

from fetch_calls import fetch_calls_for_day
from fetch_samples_sheet import fetch_samples_by_sdr
from compute_kpis import compute_sdr_kpis, merge_samples, determine_active_roster
from chart_data import get_logo_data_uri, build_sdr_view, build_manager_view
from deltas import previous_business_day
from render_long_pdf import render_long_pdf
from gmail_send import send_email_with_attachment
from sdr_config import SDR_SHORT

PST = ZoneInfo("America/Los_Angeles")
BASE_DIR = Path(__file__).parent

# TEMPORARY: everything goes here during testing, regardless of sdrs.json.
TEST_RECIPIENT = "jason.rui@schneiderinnovations.com"

TMP_DIR = Path("/tmp/sdr_report_pdfs")


def default_report_date():
    return (datetime.now(PST) - timedelta(days=1)).date()


def parse_report_date(raw_date):
    try:
        return date.fromisoformat(raw_date)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be in YYYY-MM-DD format") from exc


def main(report_date=None):
    if report_date is None:
        report_date = default_report_date()
    date_str = report_date.isoformat()
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    calls = fetch_calls_for_day(target_date=report_date)
    aircall_kpis_by_sdr = compute_sdr_kpis(calls)
    samples_by_sdr = fetch_samples_by_sdr(target_date=report_date)
    kpis_by_sdr = merge_samples(aircall_kpis_by_sdr, samples_by_sdr)

    active_roster = determine_active_roster(aircall_kpis_by_sdr, samples_by_sdr)
    print(f"Active roster for {date_str}: {active_roster}")

    # Previous business day's data, for the day-over-day delta badges.
    # Monday's "previous" is the prior Friday, not Sunday.
    prev_date = previous_business_day(report_date)
    print(f"Comparing against previous business day: {prev_date.isoformat()}")
    prev_calls = fetch_calls_for_day(target_date=prev_date)
    prev_aircall_kpis_by_sdr = compute_sdr_kpis(prev_calls)
    prev_samples_by_sdr = fetch_samples_by_sdr(target_date=prev_date)
    prev_kpis_by_sdr = merge_samples(prev_aircall_kpis_by_sdr, prev_samples_by_sdr)

    env = Environment(loader=FileSystemLoader(BASE_DIR / "templates"))
    sdr_template = env.get_template("sdr_email.html")
    manager_template = env.get_template("manager_email.html")
    logo = get_logo_data_uri()

    # --- Per-SDR PDFs ---
    for name in active_roster:
        kpis = kpis_by_sdr[name]
        display_name = SDR_SHORT.get(name, name.split(" ")[0])
        sdr_view = build_sdr_view(kpis, previous_kpis=prev_kpis_by_sdr.get(name))
        html = sdr_template.render(sdr_name=display_name, date=date_str, kpis=sdr_view, logo_data_uri=logo)

        pdf_path = TMP_DIR / f"sdr_report_{name.replace(' ', '_')}_{date_str}.pdf"
        render_long_pdf(html, str(pdf_path), page_width_px=740)

        send_email_with_attachment(
            to=TEST_RECIPIENT,
            subject=f"[TEST] Daily Performance - {display_name} - {date_str}",
            text_body=f"Daily performance report for {display_name} ({date_str}) attached.",
            attachment_path=str(pdf_path),
            attachment_filename=f"{display_name}_Daily_Performance_{date_str}.pdf",
        )

    # --- Manager rollup PDF ---
    summary, rows, team_donut_svg, team_legend = build_manager_view(
        kpis_by_sdr, active_roster, previous_kpis_by_sdr=prev_kpis_by_sdr
    )
    manager_html = manager_template.render(
        date=date_str, summary=summary, leaderboard=rows,
        team_donut_svg=team_donut_svg, team_legend=team_legend, logo_data_uri=logo,
    )
    manager_pdf_path = TMP_DIR / f"manager_report_{date_str}.pdf"
    render_long_pdf(manager_html, str(manager_pdf_path), page_width_px=940)

    send_email_with_attachment(
        to=TEST_RECIPIENT,
        subject=f"[TEST] Team Daily Rollup - {date_str}",
        text_body=f"Team daily performance rollup for {date_str} attached.",
        attachment_path=str(manager_pdf_path),
        attachment_filename=f"Team_Daily_Rollup_{date_str}.pdf",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        type=parse_report_date,
        default=None,
        help="PST report date to run, in YYYY-MM-DD format. Defaults to yesterday.",
    )
    args = parser.parse_args()
    main(report_date=args.date)
