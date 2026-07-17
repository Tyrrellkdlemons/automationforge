"""Personal data, application log, duplicate detection, merge & txt export."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from automationforge import config


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_url(url: str) -> str:
    """Normalize URL for duplicate detection (scheme/host/path; drop tracking params)."""
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url

    parsed = urlparse(url)
    scheme = (parsed.scheme or "https").lower()
    netloc = (parsed.netloc or "").lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/") or "/"

    # Drop common tracking / session noise
    drop_prefixes = ("utm_", "fbclid", "gclid", "mc_", "_ga", "ref", "source")
    qs = parse_qs(parsed.query, keep_blank_values=False)
    cleaned = {
        k: v
        for k, v in qs.items()
        if not any(k.lower().startswith(p) or k.lower() == p for p in drop_prefixes)
    }
    query = urlencode({k: v[0] if len(v) == 1 else v for k, v in sorted(cleaned.items())}, doseq=True)

    return urlunparse((scheme, netloc, path, "", query, ""))


class DataManager:
    """Load/save personal_data.json and application_log.json; export run summaries."""

    def __init__(
        self,
        personal_path: Path | None = None,
        log_path: Path | None = None,
        logs_dir: Path | None = None,
    ) -> None:
        self.personal_path = Path(personal_path or config.PERSONAL_DATA_PATH)
        self.log_path = Path(log_path or config.APPLICATION_LOG_PATH)
        self.logs_dir = Path(logs_dir or config.LOGS_DIR)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_files()

    def _ensure_files(self) -> None:
        if not self.personal_path.exists():
            self.save_personal_data(self.default_personal_template())
        if not self.log_path.exists():
            self.save_application_log({"entries": [], "version": 1})

    @staticmethod
    def default_personal_template() -> dict[str, Any]:
        return {
            "version": 2,
            "defaults": {
                "first_name": "Alex",
                "last_name": "Rivera",
                "full_name": "Alex Rivera",
                "email": "alex.rivera@example.com",
                "phone": "+1-555-0100",
                "date_of_birth": "1990-01-15",
                "address": {
                    "street": "123 Main St",
                    "city": "Austin",
                    "state": "TX",
                    "zip": "78701",
                    "country": "United States",
                },
                "linkedin": "",
                "website": "",
                "notes": "",
            },
            "profiles": {
                "general": {
                    "description": "Default profile for generic registrations",
                    "overrides": {},
                },
                "job_application": {
                    "description": "Job / career applications",
                    "overrides": {
                        "desired_salary": "85000",
                        "years_experience": "5",
                        "work_authorization": "Authorized to work",
                        "willing_to_relocate": "Yes",
                        "cover_letter_blurb": "Experienced professional seeking new opportunities.",
                        "resume_path": "",
                    },
                },
                "housing": {
                    "description": "Housing / rental applications",
                    "overrides": {
                        "monthly_income": "6000",
                        "employment_status": "Employed",
                        "employer": "Acme Corp",
                        "move_in_date": "2026-08-01",
                        "number_of_occupants": "1",
                        "pets": "No",
                        "current_landlord": "",
                        "reason_for_moving": "Relocation for work",
                    },
                },
                "registration": {
                    "description": "Account / membership sign-ups",
                    "overrides": {
                        "username_preference": "alexrivera",
                        "newsletter_opt_in": "No",
                        "marketing_opt_in": "No",
                    },
                },
            },
            "custom_fields": {
                "emergency_contact_name": "",
                "emergency_contact_phone": "",
                "ssn_last4": "",
                "driver_license": "",
            },
        }

    # ── personal data ──────────────────────────────────────────────────────

    def load_personal_data(self) -> dict[str, Any]:
        with open(self.personal_path, encoding="utf-8") as f:
            return json.load(f)

    def save_personal_data(self, data: dict[str, Any]) -> None:
        self.personal_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.personal_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

    def list_profiles(self) -> list[str]:
        data = self.load_personal_data()
        profiles = data.get("profiles") or {}
        names = list(profiles.keys())
        if "general" not in names:
            names.insert(0, "general")
        return names

    def resolve_profile(self, profile_name: str | None = None) -> dict[str, Any]:
        """
        Merge defaults + profile overrides + custom_fields into a flat fill dict.
        Nested address becomes address_street, address_city, etc., plus a dotted copy.
        """
        data = self.load_personal_data()
        defaults = deepcopy(data.get("defaults") or {})
        custom = deepcopy(data.get("custom_fields") or {})
        profiles = data.get("profiles") or {}
        name = (profile_name or "general").strip() or "general"
        profile = profiles.get(name) or profiles.get("general") or {}
        overrides = deepcopy(profile.get("overrides") or {})

        merged: dict[str, Any] = {}
        merged.update(self._flatten(defaults, prefix=""))
        merged.update(self._flatten(custom, prefix=""))
        merged.update(self._flatten(overrides, prefix=""))

        # Keep nested originals for LLM context
        merged["_profile"] = name
        merged["_profile_description"] = profile.get("description", "")
        merged["_raw_defaults"] = defaults
        merged["_raw_overrides"] = overrides
        merged["_raw_custom"] = custom
        return merged

    @staticmethod
    def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
        out: dict[str, Any] = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = f"{prefix}{k}" if not prefix else f"{prefix}_{k}" if prefix and not prefix.endswith("_") else f"{prefix}{k}"
                # Prefer address_street style for nested address
                if prefix == "" and k == "address" and isinstance(v, dict):
                    for ak, av in v.items():
                        out[f"address_{ak}"] = av
                        out[f"address.{ak}"] = av
                    out["address"] = ", ".join(
                        str(v[p]) for p in ("street", "city", "state", "zip", "country") if v.get(p)
                    )
                elif isinstance(v, dict):
                    out.update(DataManager._flatten(v, prefix=key))
                else:
                    out[key if prefix else k] = v
        else:
            if prefix:
                out[prefix] = obj
        return out

    def merge_extracted_into_personal(
        self,
        extracted: dict[str, Any],
        *,
        profile_name: str | None = None,
        into_custom: bool = True,
    ) -> dict[str, Any]:
        """
        Merge newly extracted fields back into personal_data.json.
        Unknown keys go to custom_fields (or profile overrides if profile_name set).
        """
        if not extracted:
            return self.load_personal_data()

        data = self.load_personal_data()
        defaults = data.setdefault("defaults", {})
        custom = data.setdefault("custom_fields", {})
        profiles = data.setdefault("profiles", {})

        known_default_keys = set(self._flatten(defaults).keys()) | {
            "first_name",
            "last_name",
            "full_name",
            "email",
            "phone",
            "date_of_birth",
            "linkedin",
            "website",
            "notes",
        }

        for key, value in extracted.items():
            if key.startswith("_") or value in (None, ""):
                continue
            if key.startswith("address_") or key.startswith("address."):
                addr = defaults.setdefault("address", {})
                sub = key.split("_", 1)[-1] if "_" in key else key.split(".", 1)[-1]
                if isinstance(addr, dict):
                    addr[sub] = value
                continue
            if key in known_default_keys and key in defaults:
                defaults[key] = value
            elif profile_name and profile_name in profiles:
                overrides = profiles[profile_name].setdefault("overrides", {})
                overrides[key] = value
            elif into_custom:
                custom[key] = value
            else:
                defaults[key] = value

        self.save_personal_data(data)
        return data

    # ── application log ────────────────────────────────────────────────────

    def load_application_log(self) -> dict[str, Any]:
        with open(self.log_path, encoding="utf-8") as f:
            return json.load(f)

    def save_application_log(self, log: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
            f.write("\n")

    def find_duplicate(self, url: str) -> dict[str, Any] | None:
        """Return most recent log entry matching normalized URL, if any."""
        target = normalize_url(url)
        if not target:
            return None
        log = self.load_application_log()
        matches = [
            e
            for e in log.get("entries", [])
            if normalize_url(e.get("url", "")) == target
            and e.get("status") not in ("failed", "cancelled", "skipped_duplicate")
        ]
        if not matches:
            return None
        return matches[-1]

    def append_log_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        log = self.load_application_log()
        record = {
            "id": entry.get("id") or f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            "timestamp": entry.get("timestamp") or _utc_now_iso(),
            "url": entry.get("url", ""),
            "url_normalized": normalize_url(entry.get("url", "")),
            "profile": entry.get("profile", "general"),
            "status": entry.get("status", "unknown"),
            "fields_filled": entry.get("fields_filled") or [],
            "extracted": entry.get("extracted") or {},
            "confirmation": entry.get("confirmation") or "",
            "screenshots": entry.get("screenshots") or [],
            "error": entry.get("error") or "",
            "txt_path": entry.get("txt_path") or "",
            "notes": entry.get("notes") or "",
        }
        log.setdefault("entries", []).append(record)
        self.save_application_log(log)
        return record

    def export_txt_summary(self, entry: dict[str, Any]) -> Path:
        """Write a human-readable .txt summary under logs/ and return its path."""
        ts = entry.get("timestamp") or _utc_now_iso()
        safe_ts = re.sub(r"[^\dT]", "", ts.replace(":", ""))[:15] or datetime.now().strftime("%Y%m%d_%H%M%S")
        profile = re.sub(r"[^\w\-]+", "_", str(entry.get("profile", "general")))
        filename = f"{safe_ts}_{profile}_{entry.get('status', 'run')}.txt"
        path = self.logs_dir / filename

        fields = entry.get("fields_filled") or []
        if isinstance(fields, list):
            fields_lines = []
            for item in fields:
                if isinstance(item, dict):
                    fields_lines.append(
                        f"  - {item.get('label') or item.get('name') or item.get('selector')}: "
                        f"{item.get('value', '')}"
                    )
                else:
                    fields_lines.append(f"  - {item}")
            fields_block = "\n".join(fields_lines) if fields_lines else "  (none)"
        else:
            fields_block = f"  {fields}"

        extracted = entry.get("extracted") or {}
        if isinstance(extracted, dict) and extracted:
            extracted_block = "\n".join(f"  - {k}: {v}" for k, v in extracted.items())
        else:
            extracted_block = "  (none)"

        body = f"""AutomationForge Application Summary
====================================
ID:          {entry.get('id', '')}
Timestamp:   {ts}
URL:         {entry.get('url', '')}
Normalized:  {entry.get('url_normalized') or normalize_url(entry.get('url', ''))}
Profile:     {entry.get('profile', '')}
Status:      {entry.get('status', '')}
Confirmation:{(' ' + str(entry.get('confirmation'))) if entry.get('confirmation') else ' (none)'}

Fields filled:
{fields_block}

Extracted information:
{extracted_block}

Screenshots:
{chr(10).join('  - ' + s for s in (entry.get('screenshots') or [])) or '  (none)'}

Error:
  {entry.get('error') or '(none)'}

Notes:
  {entry.get('notes') or '(none)'}
"""
        path.write_text(body, encoding="utf-8")
        return path
