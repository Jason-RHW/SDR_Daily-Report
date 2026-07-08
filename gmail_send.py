"""
Gmail send helper - same OAuth refresh-token pattern as email_to_sheets.py.
Requires the gmail.send scope on top of whatever scopes that token
already has (readonly Gmail + Sheets) - see README for the re-auth steps.
"""
import base64
import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CLIENT_ID = os.environ["GMAIL_CLIENT_ID"]
CLIENT_SECRET = os.environ["GMAIL_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["GMAIL_REFRESH_TOKEN"]


def _get_service():
    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("gmail", "v1", credentials=creds)


def send_email(to, subject, html_body):
    service = _get_service()
    message = MIMEText(html_body, "html")
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"Sent to {to}: {subject}")


def send_email_with_attachment(to, subject, text_body, attachment_path, attachment_filename=None):
    """Sends a plain-text email with a single file attached (used for the
    PDF-only delivery mode - no HTML body)."""
    service = _get_service()
    message = MIMEMultipart()
    message["to"] = to
    message["subject"] = subject
    message.attach(MIMEText(text_body, "plain"))

    filename = attachment_filename or os.path.basename(attachment_path)
    with open(attachment_path, "rb") as f:
        part = MIMEApplication(f.read(), _subtype="pdf")
    part.add_header("Content-Disposition", "attachment", filename=filename)
    message.attach(part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"Sent to {to}: {subject} (attached {filename})")
