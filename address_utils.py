"""Address helpers — randomize a plausible US residential address when missing."""

from __future__ import annotations

from typing import Any

# Fallback list used if Faker is unavailable
_FALLBACK_ADDRESSES = [
    {
        "street": "742 Evergreen Terrace",
        "city": "Springfield",
        "state": "IL",
        "zip": "62704",
        "country": "United States",
    },
    {
        "street": "1600 Pennsylvania Avenue NW",
        "city": "Washington",
        "state": "DC",
        "zip": "20500",
        "country": "United States",
    },
    {
        "street": "350 Fifth Avenue",
        "city": "New York",
        "state": "NY",
        "zip": "10118",
        "country": "United States",
    },
    {
        "street": "221B Baker Street",
        "city": "Austin",
        "state": "TX",
        "zip": "78701",
        "country": "United States",
    },
    {
        "street": "1 Infinite Loop",
        "city": "Cupertino",
        "state": "CA",
        "zip": "95014",
        "country": "United States",
    },
]


def _faker_address() -> dict[str, str]:
    from faker import Faker

    fake = Faker("en_US")
    return {
        "street": fake.street_address(),
        "city": fake.city(),
        "state": fake.state_abbr(),
        "zip": fake.zipcode(),
        "country": "United States",
    }


def random_us_address() -> dict[str, str]:
    try:
        return _faker_address()
    except Exception:
        import secrets

        return dict(_FALLBACK_ADDRESSES[secrets.randbelow(len(_FALLBACK_ADDRESSES))])


def normalize_address(raw: Any) -> dict[str, str] | None:
    """Accept string or dict address; return structured dict or None if empty."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        street = str(raw.get("street") or "").strip()
        city = str(raw.get("city") or "").strip()
        state = str(raw.get("state") or "").strip()
        zip_code = str(raw.get("zip") or raw.get("postal") or "").strip()
        if not any([street, city, state, zip_code]):
            return None
        return {
            "street": street,
            "city": city,
            "state": state,
            "zip": zip_code,
            "country": str(raw.get("country") or "United States"),
        }
    text = str(raw).strip()
    if not text:
        return None
    # Best-effort single-line address
    return {
        "street": text,
        "city": "",
        "state": "",
        "zip": "",
        "country": "United States",
    }


def resolve_address(raw: Any) -> tuple[dict[str, str], bool]:
    """
    Return (address_dict, was_randomized).
    Randomizes when the user left address empty.
    """
    parsed = normalize_address(raw)
    if parsed and (parsed.get("street") or parsed.get("city")):
        return parsed, False
    return random_us_address(), True


def format_address_line(addr: dict[str, str]) -> str:
    parts = [
        addr.get("street") or "",
        ", ".join(p for p in [addr.get("city"), addr.get("state")] if p),
        addr.get("zip") or "",
    ]
    return " ".join(p for p in parts if p).strip()
