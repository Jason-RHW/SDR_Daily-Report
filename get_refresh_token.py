"""
Run this ONCE, locally, to generate a refresh token covering everything
your automations need: reading Gmail (email_to_sheets.py), reading/writing
Sheets (email_to_sheets.py, fetch_samples_sheet.py), and sending Gmail
(send_pdf_report.py / send_report.py).

Usage:
    pip install google-auth-oauthlib
    python get_refresh_token.py

This opens your browser for a Google login + consent screen. After you
approve, the refresh token prints to the terminal - copy it into the
GMAIL_REFRESH_TOKEN GitHub secret (replacing the old one).

Make sure the account you log in with is added as a Test User on the
OAuth consent screen if the app is still in "Testing" publishing status,
or the token may expire unexpectedly.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_ID = "PASTE_YOUR_GMAIL_CLIENT_ID_HERE"
CLIENT_SECRET = "PASTE_YOUR_GMAIL_CLIENT_SECRET_HERE"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets",
]

client_config = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
# access_type=offline + prompt=consent is required to get a REFRESH token
# back (not just a short-lived access token) - easy to miss and re-hit
# the "token expires and I don't know why" problem from before.
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

print()
print("=" * 60)
print("REFRESH TOKEN (save this into GMAIL_REFRESH_TOKEN secret):")
print(creds.refresh_token)
print("=" * 60)
