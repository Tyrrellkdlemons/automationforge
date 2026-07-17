"""Firestore helpers for submissions + issued unique IDs."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from automationforge import config

_db = None
_init_error: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_firestore():
    """Lazy-init Firebase Admin / Firestore. Raises RuntimeError if misconfigured."""
    global _db, _init_error
    if _db is not None:
        return _db
    if _init_error:
        raise RuntimeError(_init_error)

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError as exc:
        _init_error = "firebase-admin is not installed. Run: pip install firebase-admin"
        raise RuntimeError(_init_error) from exc

    if not firebase_admin._apps:
        path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()
        raw_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
        if path:
            cred_path = Path(path)
            if not cred_path.is_absolute():
                cred_path = config.ROOT_DIR / cred_path
            if not cred_path.exists():
                _init_error = f"Service account file not found: {cred_path}"
                raise RuntimeError(_init_error)
            raw = cred_path.read_text(encoding="utf-8")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                _init_error = f"Invalid JSON in {cred_path}: {exc}"
                raise RuntimeError(_init_error) from exc
            if "private_key" not in data or data.get("_comment"):
                _init_error = (
                    f"{cred_path} is still a placeholder. Download a real service "
                    "account key from Firebase Console → Project settings → Service accounts."
                )
                raise RuntimeError(_init_error)
            cred = credentials.Certificate(data)
        elif raw_json:
            cred = credentials.Certificate(json.loads(raw_json))
        else:
            _init_error = (
                "Set FIREBASE_SERVICE_ACCOUNT_PATH or FIREBASE_SERVICE_ACCOUNT_JSON in .env"
            )
            raise RuntimeError(_init_error)
        firebase_admin.initialize_app(cred)

    _db = firestore.client()
    return _db


def firestore_ready() -> tuple[bool, str]:
    try:
        get_firestore()
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def create_submission(data: dict[str, Any]) -> str:
    db = get_firestore()
    payload = {
        **data,
        "status": data.get("status") or "new",
        "issued_id": None,
        "flows": data.get("flows")
        or {
            "newsletter": {"status": "pending", "error": None},
            "saas_trial": {"status": "pending", "error": None},
            "job_profile": {"status": "pending", "error": None},
        },
        "manualOverride": False,
        "manualLogs": [],
        "createdAt": _utc_now(),
        "updatedAt": _utc_now(),
    }
    _, ref = db.collection("submissions").add(payload)
    return ref.id


def get_submission(submission_id: str) -> dict[str, Any] | None:
    db = get_firestore()
    snap = db.collection("submissions").document(submission_id).get()
    if not snap.exists:
        return None
    out = snap.to_dict() or {}
    out["id"] = snap.id
    return out


def list_submissions(limit: int = 100) -> list[dict[str, Any]]:
    db = get_firestore()
    # Order by createdAt desc when present; fall back to unordered if index missing
    try:
        docs = (
            db.collection("submissions")
            .order_by("createdAt", direction="DESCENDING")
            .limit(limit)
            .stream()
        )
    except Exception:
        docs = db.collection("submissions").limit(limit).stream()
    rows = []
    for snap in docs:
        row = snap.to_dict() or {}
        row["id"] = snap.id
        rows.append(row)
    return rows


def list_new_submissions(limit: int = 10) -> list[dict[str, Any]]:
    """Fetch submissions ready for automatic worker processing."""
    db = get_firestore()
    docs = (
        db.collection("submissions")
        .where("status", "==", "new")
        .limit(limit)
        .stream()
    )
    rows = []
    for snap in docs:
        row = snap.to_dict() or {}
        row["id"] = snap.id
        # Skip manual takeover
        if row.get("manualOverride") or row.get("status") == "manual":
            continue
        rows.append(row)
    return rows


def update_submission(submission_id: str, fields: dict[str, Any]) -> None:
    db = get_firestore()
    fields = {**fields, "updatedAt": _utc_now()}
    db.collection("submissions").document(submission_id).set(fields, merge=True)


def append_manual_log(submission_id: str, line: str) -> None:
    db = get_firestore()
    from firebase_admin import firestore as fs

    db.collection("submissions").document(submission_id).update(
        {
            "manualLogs": fs.ArrayUnion([{"ts": _utc_now(), "message": line[:2000]}]),
            "updatedAt": _utc_now(),
        }
    )


def claim_number(number: str, submission_id: str) -> bool:
    """Atomically claim an issued number. Returns False if already taken."""
    db = get_firestore()
    from firebase_admin import firestore as fs

    ref = db.collection("issued_numbers").document(number)

    @fs.transactional
    def _claim(transaction) -> bool:
        snap = ref.get(transaction=transaction)
        if snap.exists:
            return False
        transaction.set(
            ref,
            {
                "issuedAt": _utc_now(),
                "submissionId": submission_id,
            },
        )
        return True

    return bool(_claim(db.transaction()))


def submission_stats() -> dict[str, int]:
    rows = list_submissions(limit=500)
    stats = {
        "total": len(rows),
        "new": 0,
        "processing": 0,
        "manual": 0,
        "completed": 0,
        "failed": 0,
        "pending_followups": 0,
    }
    for r in rows:
        status = (r.get("status") or "new").lower()
        if status in stats:
            stats[status] += 1
        if status == "completed" and not r.get("followup_sent"):
            stats["pending_followups"] += 1
    return stats


def list_pending_followups(limit: int = 100) -> list[dict[str, Any]]:
    rows = list_submissions(limit=500)
    out = [
        r
        for r in rows
        if (r.get("status") or "").lower() == "completed" and not r.get("followup_sent")
    ]
    return out[:limit]


def append_followup_history(submission_id: str, entry: dict[str, Any]) -> None:
    db = get_firestore()
    from firebase_admin import firestore as fs

    db.collection("submissions").document(submission_id).update(
        {
            "followup_history": fs.ArrayUnion([entry]),
            "followup_sent": True,
            "followup_sent_at": _utc_now(),
            "updatedAt": _utc_now(),
        }
    )
