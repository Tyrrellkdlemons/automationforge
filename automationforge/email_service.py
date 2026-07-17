"""
Email sign-up / verification helpers.

Supported out of the box:
  - Tigrmail (temp inbox API) when TIGRMAIL_API_KEY is set
  - Gmail IMAP (read verification codes/links from your own inbox)

How to extend with other providers (Mail.tm, Guerrilla Mail, custom SMTP, etc.):
  1. Subclass BaseEmailService
  2. Implement create_address(), list_messages(), wait_for_message()
  3. Register in get_email_service() or pass the instance into main.run_email_step()

IMPORTANT: Use only for your own accounts / legitimate verification flows.
Never use temp email to abuse third-party services or violate ToS.
"""

from __future__ import annotations

import email
import imaplib
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from email.header import decode_header
from typing import Any, Callable

import httpx

from automationforge import config


@dataclass
class EmailMessage:
    id: str
    subject: str
    from_addr: str
    body_text: str
    body_html: str = ""
    received_at: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def extract_code(self, pattern: str = r"\b(\d{4,8})\b") -> str | None:
        for source in (self.subject, self.body_text, self.body_html):
            m = re.search(pattern, source or "")
            if m:
                return m.group(1)
        return None

    def extract_links(self) -> list[str]:
        text = f"{self.body_text}\n{self.body_html}"
        return re.findall(r"https?://[^\s\"'<>]+", text or "")


class BaseEmailService(ABC):
    """Interface for temp-mail / inbox verification providers."""

    name: str = "base"

    @abstractmethod
    def create_address(self, local_part: str | None = None) -> str:
        """Create or return an inbox address to use for sign-up."""

    @abstractmethod
    def list_messages(self, address: str | None = None) -> list[EmailMessage]:
        """List recent messages for the active inbox."""

    def wait_for_message(
        self,
        *,
        address: str | None = None,
        timeout_sec: int = 120,
        poll_sec: float = 5.0,
        predicate: Callable[[EmailMessage], bool] | None = None,
    ) -> EmailMessage | None:
        """Poll until a matching message arrives or timeout."""
        deadline = time.time() + timeout_sec
        seen: set[str] = set()
        while time.time() < deadline:
            for msg in self.list_messages(address):
                if msg.id in seen:
                    continue
                seen.add(msg.id)
                if predicate is None or predicate(msg):
                    return msg
            time.sleep(poll_sec)
        return None

    def wait_for_code(
        self,
        *,
        address: str | None = None,
        timeout_sec: int = 120,
        subject_contains: str | None = None,
    ) -> str | None:
        def pred(m: EmailMessage) -> bool:
            if subject_contains and subject_contains.lower() not in (m.subject or "").lower():
                return False
            return m.extract_code() is not None

        msg = self.wait_for_message(address=address, timeout_sec=timeout_sec, predicate=pred)
        return msg.extract_code() if msg else None


class TigrmailService(BaseEmailService):
    """
    Example Tigrmail client.

    The public Tigrmail API shapes vary; this implementation uses a pragmatic
    REST shape. Adjust endpoints in _request / methods if your account docs differ.

    Env:
      TIGRMAIL_API_KEY
      TIGRMAIL_BASE_URL (default https://api.tigrmail.com)
    """

    name = "tigrmail"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key or config.TIGRMAIL_API_KEY
        self.base_url = (base_url or config.TIGRMAIL_BASE_URL).rstrip("/")
        self._address: str | None = None
        self._inbox_id: str | None = None
        if not self.api_key:
            raise RuntimeError("TIGRMAIL_API_KEY is not set in .env")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=30.0) as client:
            r = client.request(method, url, headers=self._headers(), **kwargs)
            # Some deployments return 404 for unused paths — surface clearly
            if r.status_code >= 400:
                raise RuntimeError(f"Tigrmail {method} {path} → {r.status_code}: {r.text[:500]}")
            if not r.content:
                return {}
            return r.json()

    def create_address(self, local_part: str | None = None) -> str:
        """
        Create a temporary inbox.

        Try common endpoint variants so minor API renames still work.
        Extend here when Tigrmail documents a stable path for your plan.
        """
        payload: dict[str, Any] = {}
        if local_part:
            payload["local"] = local_part

        # Attempt known/likely routes; first success wins.
        candidates = [
            ("POST", "/v1/inboxes", payload),
            ("POST", "/inboxes", payload),
            ("POST", "/api/v1/mailbox", payload),
        ]
        last_err: Exception | None = None
        for method, path, body in candidates:
            try:
                data = self._request(method, path, json=body or None)
                address = (
                    data.get("email")
                    or data.get("address")
                    or data.get("inbox")
                    or (data.get("data") or {}).get("email")
                )
                inbox_id = data.get("id") or data.get("inbox_id") or (data.get("data") or {}).get("id")
                if address:
                    self._address = address
                    self._inbox_id = str(inbox_id) if inbox_id else None
                    return address
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                continue
        raise RuntimeError(
            "Could not create Tigrmail inbox. Check TIGRMAIL_BASE_URL / API docs and extend "
            f"TigrmailService.create_address(). Last error: {last_err}"
        )

    def list_messages(self, address: str | None = None) -> list[EmailMessage]:
        addr = address or self._address
        inbox = self._inbox_id or addr
        if not inbox:
            raise RuntimeError("No Tigrmail inbox — call create_address() first")

        candidates = [
            f"/v1/inboxes/{inbox}/messages",
            f"/inboxes/{inbox}/messages",
            f"/api/v1/mailbox/{inbox}/messages",
        ]
        data: Any = None
        last_err: Exception | None = None
        for path in candidates:
            try:
                data = self._request("GET", path)
                break
            except Exception as exc:  # noqa: BLE001
                last_err = exc
        if data is None:
            raise RuntimeError(f"Failed to list Tigrmail messages: {last_err}")

        items = data if isinstance(data, list) else data.get("messages") or data.get("data") or []
        out: list[EmailMessage] = []
        for item in items:
            out.append(
                EmailMessage(
                    id=str(item.get("id") or item.get("message_id") or len(out)),
                    subject=item.get("subject") or "",
                    from_addr=item.get("from") or item.get("sender") or "",
                    body_text=item.get("text") or item.get("body") or item.get("body_text") or "",
                    body_html=item.get("html") or item.get("body_html") or "",
                    received_at=str(item.get("date") or item.get("received_at") or ""),
                    raw=item if isinstance(item, dict) else {},
                )
            )
        return out


class GmailImapService(BaseEmailService):
    """
    Read verification mail from your own Gmail via IMAP.

    Setup:
      1. Enable 2FA on Google account
      2. Create an App Password
      3. Set GMAIL_IMAP_USER and GMAIL_IMAP_PASSWORD in .env

    create_address() returns your real Gmail address (does not create aliases).
    For plus-aliases, pass local_part like "you+jobapps".
    """

    name = "gmail_imap"

    def __init__(
        self,
        user: str | None = None,
        password: str | None = None,
        host: str | None = None,
        folder: str | None = None,
    ) -> None:
        self.user = user or config.GMAIL_IMAP_USER
        self.password = password or config.GMAIL_IMAP_PASSWORD
        self.host = host or config.GMAIL_IMAP_HOST
        self.folder = folder or config.GMAIL_IMAP_FOLDER
        self._address = self.user
        if not self.user or not self.password:
            raise RuntimeError("GMAIL_IMAP_USER / GMAIL_IMAP_PASSWORD not set in .env")

    def create_address(self, local_part: str | None = None) -> str:
        if local_part and "@" in local_part:
            self._address = local_part
        elif local_part and self.user and "@" in self.user:
            domain = self.user.split("@", 1)[1]
            # Support plus-addressing: user+tag@gmail.com
            base = self.user.split("@", 1)[0].split("+", 1)[0]
            self._address = f"{base}+{local_part}@{domain}"
        else:
            self._address = self.user
        return self._address or self.user

    def list_messages(self, address: str | None = None) -> list[EmailMessage]:
        _ = address  # IMAP searches the configured mailbox
        mail = imaplib.IMAP4_SSL(self.host)
        try:
            mail.login(self.user, self.password)
            mail.select(self.folder)
            status, data = mail.search(None, "ALL")
            if status != "OK":
                return []
            ids = data[0].split()
            # Most recent first, limit
            ids = list(reversed(ids[-30:]))
            out: list[EmailMessage] = []
            for mid in ids:
                status, msg_data = mail.fetch(mid, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                if not isinstance(raw, (bytes, bytearray)):
                    continue
                parsed = email.message_from_bytes(raw)
                subject = _decode_mime(parsed.get("Subject", ""))
                from_addr = _decode_mime(parsed.get("From", ""))
                body_text, body_html = _extract_bodies(parsed)
                out.append(
                    EmailMessage(
                        id=mid.decode() if isinstance(mid, bytes) else str(mid),
                        subject=subject,
                        from_addr=from_addr,
                        body_text=body_text,
                        body_html=body_html,
                        received_at=parsed.get("Date", ""),
                    )
                )
            return out
        finally:
            try:
                mail.logout()
            except Exception:
                pass


def _decode_mime(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    chunks: list[str] = []
    for part, enc in parts:
        if isinstance(part, bytes):
            chunks.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            chunks.append(part)
    return "".join(chunks)


def _extract_bodies(msg: email.message.Message) -> tuple[str, str]:
    text, html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if ctype == "text/plain" and not text:
                text = decoded
            elif ctype == "text/html" and not html:
                html = decoded
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
    return text, html


class ManualEmailService(BaseEmailService):
    """
    No-API fallback: user provides an address and pastes the code manually.
    Useful when temp-mail providers are unavailable.
    """

    name = "manual"

    def __init__(self) -> None:
        self._address: str | None = None

    def create_address(self, local_part: str | None = None) -> str:
        self._address = local_part or ""
        return self._address

    def list_messages(self, address: str | None = None) -> list[EmailMessage]:
        return []


def get_email_service(preferred: str | None = None) -> BaseEmailService:
    """
    Factory: prefer explicit name, else Tigrmail if keyed, else Gmail IMAP, else manual.

    To plug in another provider:
      class MyMail(BaseEmailService): ...
      # then: return MyMail() when preferred == "mymail"
    """
    name = (preferred or "").lower().strip()
    if name in ("tigrmail", "tigr"):
        return TigrmailService()
    if name in ("gmail", "gmail_imap", "imap"):
        return GmailImapService()
    if name == "manual":
        return ManualEmailService()

    if config.TIGRMAIL_API_KEY:
        try:
            return TigrmailService()
        except Exception:
            pass
    if config.GMAIL_IMAP_USER and config.GMAIL_IMAP_PASSWORD:
        try:
            return GmailImapService()
        except Exception:
            pass
    return ManualEmailService()
