"""SMTP email sender for unique-ID delivery (Gmail app password supported)."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any


def _settings() -> dict[str, str]:
    return {
        "host": os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com"),
        "port": os.getenv("EMAIL_SMTP_PORT", "587"),
        "sender": os.getenv("EMAIL_SENDER", os.getenv("GMAIL_IMAP_USER", "")),
        "password": os.getenv("EMAIL_PASSWORD", os.getenv("GMAIL_IMAP_PASSWORD", "")),
        "from_name": os.getenv("EMAIL_FROM_NAME", "AutomationForge"),
    }


def send_unique_id_email(to_email: str, unique_id: str, *, first_name: str = "") -> dict[str, Any]:
    """Send the unique ID notification email. Returns {ok, error?}."""
    cfg = _settings()
    if not cfg["sender"] or not cfg["password"]:
        return {
            "ok": False,
            "error": "EMAIL_SENDER / EMAIL_PASSWORD not configured in .env",
        }
    if not to_email or "@" not in to_email:
        return {"ok": False, "error": "Invalid recipient email"}

    greeting = f"Hi {first_name}," if first_name else "Hi,"
    body = (
        f"{greeting}\n\n"
        f"Your unique ID is: {unique_id}\n\n"
        "Thank you for signing up.\n\n"
        "— AutomationForge\n"
    )

    msg = EmailMessage()
    msg["Subject"] = "Your unique ID"
    msg["From"] = f"{cfg['from_name']} <{cfg['sender']}>"
    msg["To"] = to_email
    msg.set_content(body)

    try:
        port = int(cfg["port"])
        with smtplib.SMTP(cfg["host"], port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(cfg["sender"], cfg["password"])
            smtp.send_message(msg)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
