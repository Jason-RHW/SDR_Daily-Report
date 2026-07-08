"""
Generates the long, unpaginated PDF for each SDR and for the manager rollup,
then emails each as a plain-text message with the PDF attached. Recipients come
from sdrs.json unless --test-recipient is provided.
"""
import argparse
import json
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

TMP_DIR = Path("/tmp/sdr_report_pdfs")


def default_report_date():
    return (datetime.now(PST) - timedelta(days=1)).date()


def parse_report_date(raw_date):
    try:
        return date.fromisoformat(raw_date)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be in YYYY-MM-DD format") from exc


def load_sdr_config():
    with open(BASE_DIR / "sdrs.json", encoding="utf-8") as f:
        return json.load(f)


def _valid_recipients(recipients):
    return [
        recipient.strip()
        for recipient in recipients
        if recipient and recipient.strip() and recipient.strip() != "REPLACE_ME"
    ]


def main(report_date=None, send_mode="both", test_recipient=None):
    if report_date is None:
        report_date = default_report_date()
    date_str = report_date.isoformat()
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    sdr_config = load_sdr_config()
    sdr_recipients = {
        sdr["name"]: sdr.get("email", "").strip()
        for sdr in sdr_config.get("sdrs", [])
    }
    manager_recipients = _valid_recipients(sdr_config.get("managers", []))

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
    if send_mode in ("both", "sdr"):
        for name in active_roster:
            kpis = kpis_by_sdr[name]
            display_name = SDR_SHORT.get(name, name.split(" ")[0])
            sdr_view = build_sdr_view(kpis, previous_kpis=prev_kpis_by_sdr.get(name))
            html = sdr_template.render(sdr_name=display_name, date=date_str, kpis=sdr_view, logo_data_uri=logo)

            pdf_path = TMP_DIR / f"sdr_report_{name.replace(' ', '_')}_{date_str}.pdf"
            render_long_pdf(html, str(pdf_path), page_width_px=740)

            recipient = test_recipient or sdr_recipients.get(name)
            if not recipient or recipient == "REPLACE_ME":
                print(f"WARNING: no email configured for {name}; skipping SDR report.")
                continue

            send_email_with_attachment(
                to=recipient,
                subject=f"Daily Performance - {display_name} - {date_str}",
                text_body=f"Daily performance report for {display_name} ({date_str}) attached.",
                attachment_path=str(pdf_path),
                attachment_filename=f"{display_name}_Daily_Performance_{date_str}.pdf",
            )

    # --- Manager rollup PDF ---
    if send_mode in ("both", "manager"):
        summary, rows, team_donut_svg, team_legend = build_manager_view(
            kpis_by_sdr, active_roster, previous_kpis_by_sdr=prev_kpis_by_sdr
        )
        manager_html = manager_template.render(
            date=date_str, summary=summary, leaderboard=rows,
            team_donut_svg=team_donut_svg, team_legend=team_legend, logo_data_uri=logo,
        )
        manager_pdf_path = TMP_DIR / f"manager_report_{date_str}.pdf"
        render_long_pdf(manager_html, str(manager_pdf_path), page_width_px=940)

        recipients = [test_recipient] if test_recipient else manager_recipients
        if not recipients:
            print("WARNING: no manager emails configured; skipping manager report.")
        for recipient in recipients:
            send_email_with_attachment(
                to=recipient,
                subject=f"Team Daily Rollup - {date_str}",
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
    parser.add_argument(
        "--send",
        choices=("both", "manager", "sdr"),
        default="both",
        help="Which reports to email. Defaults to both.",
    )
    parser.add_argument(
        "--test-recipient",
        default=None,
        help="Send all selected reports to this address instead of the configured recipients.",
    )
    args = parser.parse_args()
    main(report_date=args.date, send_mode=args.send, test_recipient=args.test_recipient)
