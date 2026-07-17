"""Cryptographically random unique ID generator: [8|9]XX-XX-XXXX (9 digits).

These are NOT Social Security Numbers — they are opaque unique identifiers
that only look similar in dash formatting. Do not use them as real SSNs.
"""

from __future__ import annotations

import secrets
from typing import Callable


def generate_candidate() -> str:
    """Return one candidate ID like 8XX-XX-XXXX or 9XX-XX-XXXX."""
    first = secrets.choice(("8", "9"))
    rest = "".join(str(secrets.randbelow(10)) for _ in range(8))
    digits = first + rest  # 9 digits total
    return f"{digits[0:3]}-{digits[3:5]}-{digits[5:9]}"


def issue_unique_id(
    submission_id: str,
    *,
    claim_fn: Callable[[str, str], bool] | None = None,
    max_attempts: int = 100,
) -> tuple[str | None, str]:
    """
    Generate a unique ID and claim it via claim_fn(number, submission_id).

    Returns (number_or_None, status_message).
    If all attempts collide, returns (None, "human_review_required").
    """
    if claim_fn is None:
        from firebase_client import claim_number

        claim_fn = claim_number

    for attempt in range(1, max_attempts + 1):
        candidate = generate_candidate()
        try:
            ok = claim_fn(candidate, submission_id)
        except Exception as exc:
            return None, f"claim_error: {exc}"
        if ok:
            return candidate, f"issued on attempt {attempt}"
    return None, "human_review_required"
