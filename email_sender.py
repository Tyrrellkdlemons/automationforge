"""SMTP email sender — confirmation, unique ID, and follow-up messages."""

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
        "from_name": os.getenv("EMAIL_FROM_NAME", "PEEEZMachine"),
    }


def _send(to_email: str, subject: str, text_body: str, html_body: str | None = None) -> dict[str, Any]:
    cfg = _settings()
    if not cfg["sender"] or not cfg["password"]:
        return {"ok": False, "error": "EMAIL_SENDER / EMAIL_PASSWORD not configured in .env"}
    if not to_email or "@" not in to_email:
        return {"ok": False, "error": "Invalid recipient email"}

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{cfg['from_name']} <{cfg['sender']}>"
    msg["To"] = to_email
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    try:
        port = int(cfg["port"])
        with smtplib.SMTP(cfg["host"], port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(cfg["sender"], cfg["password"])
            smtp.send_message(msg)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def send_confirmation_email(
    *,
    to_email: str,
    first_name: str,
    last_name: str,
    address_line: str,
    unique_id: str,
) -> dict[str, Any]:
    greeting = f"Hi {first_name}," if first_name else "Hi,"
    text = (
        f"{greeting}\n\n"
        f"Thank you for submitting your information.\n\n"
        f"Name: {first_name} {last_name}\n"
        f"Address on file: {address_line}\n"
        f"Your unique ID is: {unique_id}\n\n"
        "Full verification and next-step instructions will arrive within 24-48 hours.\n\n"
        "— PEEEZMachine\n"
    )
    html = f"""
    <p>{greeting}</p>
    <p>Thank you for submitting your information to PEEEZMachine.</p>
    <ul>
      <li><strong>Name:</strong> {first_name} {last_name}</li>
      <li><strong>Address on file:</strong> {address_line}</li>
      <li><strong>Your unique ID:</strong> <code>{unique_id}</code></li>
    </ul>
    <p>Full verification and next-step instructions will arrive within <strong>24–48 hours</strong>.</p>
    <p>— PEEEZMachine</p>
    """
    return _send(to_email, "PEEEZMachine — your unique ID confirmation", text, html)


def send_unique_id_email(to_email: str, unique_id: str, *, first_name: str = "") -> dict[str, Any]:
    """Backward-compatible short notifier."""
    return send_confirmation_email(
        to_email=to_email,
        first_name=first_name,
        last_name="",
        address_line="(see portal)",
        unique_id=unique_id,
    )


def send_followup_email(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> dict[str, Any]:
    return _send(to_email, subject or "Follow-up", body_text, body_html)
