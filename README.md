# SDR Daily Report

Pulls yesterday's calls from Aircall, computes per-SDR KPIs, cross-references
sample counts against the Sample Google Sheet, and generates a branded,
chart-heavy PDF report — one per SDR plus a team rollup for managers.

## Current phase: PDF delivery

`send_pdf_report.py` is the active script. It generates a long, unpaginated
PDF for each SDR and for the manager rollup, then emails each as a plain-text
message with the PDF attached. Recipients come from `sdrs.json`. Use
`--test-recipient` to send the selected reports to one test address instead of
the real recipients.

## Before running

1. **Gmail OAuth scope.** The existing `GMAIL_CLIENT_ID`/`SECRET`/
   `REFRESH_TOKEN` (reused from `email_to_sheets.py`) was authorized for
   reading Gmail + writing Sheets - **not sending mail**. Sending requires
   the `https://www.googleapis.com/auth/gmail.send` scope specifically.
   Re-run the OAuth consent flow for this account requesting the union of
   all scopes needed (`gmail.readonly`, `spreadsheets`, `gmail.send`), and
   update the `GMAIL_REFRESH_TOKEN` secret with the new token. Sending will
   fail with a 403 until this is done.

2. **Sample Sheet access.** `fetch_samples_sheet.py` reads
   `https://docs.google.com/spreadsheets/d/1ehyBGdfJ2TVMVRo28ObskWACQbdr2D4ON9eC8QvEaY4`
   via the Sheets API, tab assumed to be `Sheet1` (from `gid=0` in the URL)
   and range `A:AI`. Confirm both against the real sheet - a wrong tab name
   fails loudly (API error), but a wrong range could silently miss columns.

3. **Verify SDR name matching** in `sdr_config.py` (`AIRCALL_USER_MAP`) and
   `fetch_samples_sheet.py` (`SHEET_OWNER_MAP`) - two different systems, two
   different naming quirks (e.g. Aircall's "Grace Manansala" vs Sheet's
   "Lorenzo Bamiano" for Lhoreto). Confirmed current mappings; recheck if
   the team roster changes.

4. **Set these secrets** (GitHub repo -> Settings -> Secrets -> Actions):
   - `AIRCALL_API_ID`, `AIRCALL_API_TOKEN`
   - `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`
     (re-authorized per step 1 above)

5. **Set recipients** in `sdrs.json`:
   - `sdrs[].email` controls each individual SDR dashboard recipient.
   - `managers` controls who receives the manager rollup. Add multiple manager
     emails as separate strings in the array.

## Testing locally

```bash
pip install requests jinja2 google-auth google-api-python-client weasyprint pymupdf numpy
# WeasyPrint also needs system libs - on Ubuntu/Debian:
sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info

export AIRCALL_API_ID=...
export AIRCALL_API_TOKEN=...
export GMAIL_CLIENT_ID=...
export GMAIL_CLIENT_SECRET=...
export GMAIL_REFRESH_TOKEN=...

python send_pdf_report.py
# Optional backfill/rerun for a specific PST report date:
python send_pdf_report.py --date 2026-07-06
# Only send the manager dashboard:
python send_pdf_report.py --send manager
# Only send individual SDR dashboards:
python send_pdf_report.py --send sdr
# Test without sending to the real recipients:
python send_pdf_report.py --send both --test-recipient you@example.com
```

This sends real Aircall + Sheet data and real charts. Without
`--test-recipient`, emails go to the recipients configured in `sdrs.json`.

The scheduled GitHub Action defaults to yesterday in Pacific time. When running
it manually from GitHub Actions, fill in the optional `report_date` field with a
date like `2026-07-06` to rerun a specific day. Use `send_mode` to choose
`both`, `manager`, or `sdr`; use `test_recipient` to route all selected reports
to one email address for testing.

## Going live (later)

Once PDF output has been checked against a few real days:
1. Decide: keep PDF-only delivery, or bring back `send_report.py`'s HTML
   email body with the PDF as a fallback attachment (discussed earlier -
   HTML gives Gmail/mobile users a glance-without-opening experience, PDF
   guarantees the charts render correctly for Outlook desktop users).
2. Update the GitHub Actions workflow's cron to the live schedule/recipient
   logic.

## Known things to revisit

- **DST**: the cron line needs manual updating twice a year (PST <-> PDT)
  unless you build in month-aware scheduling. Currently set for PDT.
- **Active Hours / clock chart** assumes a call span of 12 hours or less -
  a longer span wraps around the dial oddly. Fine for a normal shift.
- **Samples Sent Today / Conversion Rate** are now sourced from the Sample
  Sheet, not Aircall's "Send Sample" tag - deliberately, so a missing form
  shows up as a gap between what the SDR did on calls and what's actually
  logged. Conversion Rate therefore mixes two systems (Sheet samples /
  Aircall calls) - confirmed intentional, not an oversight.
- No manager PDF/email will be meaningful if `sdrs.json`'s SDR list and
  `sdr_config.SDR_NAMES` ever drift out of sync - keep them matched.
