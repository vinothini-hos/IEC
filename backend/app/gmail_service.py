"""
Thin wrapper around the Gmail API, built on top of the OAuth client /
Pub-Sub setup already configured in Google Cloud Console for this project
(topic: gmail-notifications, subscription: gmail-notifications-sub).

Responsibilities:
  - authenticate using the stored OAuth token (refreshing as needed)
  - fetch a thread's messages from Gmail and normalize them
  - send a new email / reply through the Gmail API
  - decode the History API delta so the webhook can pull only what changed
"""
import base64
import logging
import os
import uuid
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .config import settings

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

logger = logging.getLogger(__name__)


def get_credentials() -> Credentials:
    creds = None
    if os.path.exists(settings.gmail_token_path):
        creds = Credentials.from_authorized_user_file(settings.gmail_token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # One-time interactive auth. On a server this should be run once
            # locally (or via a dedicated /auth route) and the resulting
            # token.json copied into place - not triggered on every request.
            flow = InstalledAppFlow.from_client_secrets_file(
                settings.gmail_credentials_path, SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(settings.gmail_token_path, "w") as f:
            f.write(creds.to_json())

    return creds


def get_service():
    return build("gmail", "v1", credentials=get_credentials())


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _walk_parts(part: dict, out: dict):
    mime_type = part.get("mimeType", "")
    filename = part.get("filename") or ""
    body = part.get("body", {})

    if filename:
        out["attachments"].append({
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": body.get("size", 0),
            "gmail_attachment_id": body.get("attachmentId"),
        })
    elif mime_type == "text/plain" and "data" in body:
        out["body_text"] += base64.urlsafe_b64decode(body["data"]).decode("utf-8", "ignore")
    elif mime_type == "text/html" and "data" in body:
        out["body_html"] += base64.urlsafe_b64decode(body["data"]).decode("utf-8", "ignore")

    for sub in part.get("parts", []) or []:
        _walk_parts(sub, out)


def normalize_message(msg: dict, my_email: str) -> dict:
    """Convert a raw Gmail API message resource into our internal shape."""
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])

    out = {"body_text": "", "body_html": "", "attachments": []}
    _walk_parts(payload, out)

    sender = _header(headers, "From")
    direction = "outgoing" if my_email and my_email in sender else "incoming"

    return {
        "gmail_message_id": msg["id"],
        "gmail_thread_id": msg["threadId"],
        "direction": direction,
        "sender": sender,
        "recipient": _header(headers, "To"),
        "cc": _header(headers, "Cc"),
        "subject": _header(headers, "Subject"),
        "snippet": msg.get("snippet", ""),
        "body_text": out["body_text"] or out["body_html"],
        "body_html": out["body_html"] or None,
        "attachments": out["attachments"],
        "internal_date_ms": int(msg.get("internalDate", "0")),
    }


def fetch_thread(gmail_thread_id: str, my_email: str) -> list[dict]:
    service = get_service()
    thread = service.users().threads().get(
        userId="me", id=gmail_thread_id, format="full"
    ).execute()
    return [normalize_message(m, my_email) for m in thread.get("messages", [])]


def fetch_recent_thread_ids(max_results: int = 25) -> list[str]:
    service = get_service()
    resp = service.users().messages().list(
        userId="me", maxResults=max_results, labelIds=["INBOX"]
    ).execute()
    thread_ids = []
    for m in resp.get("messages", []):
        if m["threadId"] not in thread_ids:
            thread_ids.append(m["threadId"])
    return thread_ids


def send_email(
    to: str,
    subject: str,
    body_text: str,
    cc: Optional[str] = None,
    gmail_thread_id: Optional[str] = None,
    in_reply_to_message_id: Optional[str] = None,
    attachments: Optional[list[dict]] = None,
) -> dict:
    """attachments (optional): [{"filename", "mime_type", "content": bytes}]"""
    service = get_service()

    if attachments:
        message = MIMEMultipart()
        message.attach(MIMEText(body_text))
        for att in attachments:
            part = MIMEApplication(att["content"], Name=att["filename"])
            part["Content-Disposition"] = f'attachment; filename="{att["filename"]}"'
            message.attach(part)
    else:
        message = MIMEText(body_text)

    message["to"] = to
    message["subject"] = subject
    if cc:
        message["cc"] = cc
    if in_reply_to_message_id:
        message["In-Reply-To"] = in_reply_to_message_id
        message["References"] = in_reply_to_message_id

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    body = {"raw": raw}
    if gmail_thread_id:
        body["threadId"] = gmail_thread_id

    return service.users().messages().send(userId="me", body=body).execute()


def save_attachment_locally(
    gmail_message_id: str, gmail_attachment_id: str, filename: str
) -> Optional[str]:
    """Downloads a received attachment's bytes from Gmail and saves them to
    disk, returning the local path (or None if the fetch fails)."""
    try:
        service = get_service()
        att = service.users().messages().attachments().get(
            userId="me", messageId=gmail_message_id, id=gmail_attachment_id
        ).execute()
        content = base64.urlsafe_b64decode(att["data"])
    except Exception:
        logger.exception("Failed to download attachment %s", gmail_attachment_id)
        return None

    os.makedirs(settings.attachment_storage_dir, exist_ok=True)
    local_path = os.path.join(settings.attachment_storage_dir, f"{uuid.uuid4()}_{filename}")
    with open(local_path, "wb") as f:
        f.write(content)
    return local_path


def decode_pubsub_history_id(pubsub_envelope: dict) -> Optional[str]:
    """Pub/Sub push delivers {'message': {'data': base64(json)}}."""
    data_b64 = pubsub_envelope.get("message", {}).get("data")
    if not data_b64:
        return None
    import json
    decoded = json.loads(base64.b64decode(data_b64).decode("utf-8"))
    return decoded.get("historyId")
