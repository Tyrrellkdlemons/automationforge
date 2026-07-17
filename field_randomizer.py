"""Generate plausible consistent values for missing form fields."""

from __future__ import annotations

import secrets
import string
from typing import Any


_MIDDLE = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_SECURITY = [
    ("mother_maiden", "Smith"),
    ("first_pet", "Buddy"),
    ("favorite_teacher", "Mr Johnson"),
    ("city_born", "Springfield"),
]


def _password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def ensure_randomized_fields(submission: dict[str, Any]) -> dict[str, str]:
    """
    Return randomized_fields dict (merge existing). Always includes password + middle initial.
    """
    existing = dict(submission.get("randomized_fields") or {})
    if not existing.get("password"):
        existing["password"] = submission.get("generated_password") or _password()
    if not existing.get("middle_initial"):
        existing["middle_initial"] = secrets.choice(_MIDDLE)
    if not existing.get("username"):
        first = str(submission.get("firstName") or "user").lower()
        last = str(submission.get("lastName") or "person").lower()
        existing["username"] = f"{first}.{last}{secrets.randbelow(9000) + 1000}"
    for key, value in _SECURITY:
        existing.setdefault(f"security_{key}", value)
    existing.setdefault("phone_alt", f"+1-555-{secrets.randbelow(9000) + 1000}")
    return existing
