"""Optional Twilio SMS for unique-ID delivery."""

from __future__ import annotations

import os
from typing import Any


def sms_enabled() -> bool:
    return os.getenv("SEND_SMS", "false").lower() in ("1", "true", "yes")


def send_unique_id_sms(to_phone: str, unique_id: str) -> dict[str, Any]:
    if not sms_enabled():
        return {"ok": True, "skipped": True, "reason": "SEND_SMS=false"}
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_num = os.getenv("TWILIO_FROM_NUMBER", "")
    if not (sid and token and from_num and to_phone):
        return {"ok": False, "error": "Twilio env vars or phone missing"}
    try:
        from twilio.rest import Client

        client = Client(sid, token)
        msg = client.messages.create(
            body=f"Your unique ID is {unique_id}. Next steps arrive in 24-48 hours.",
            from_=from_num,
            to=to_phone,
        )
        return {"ok": True, "sid": msg.sid}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
