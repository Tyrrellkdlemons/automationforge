"""LLM page analysis → structured fill plan (Ollama preferred, API fallback)."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from automationforge import config

FILL_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["fields", "submit", "captcha_detected", "notes"],
    "properties": {
        "page_title": {"type": "string"},
        "page_purpose": {"type": "string"},
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["action", "value"],
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["fill", "select", "check", "uncheck", "click", "skip"],
                    },
                    "selector": {"type": "string", "description": "CSS or role-based selector"},
                    "role": {"type": "string"},
                    "name": {"type": "string"},
                    "label": {"type": "string"},
                    "value": {"type": "string"},
                    "field_key": {"type": "string", "description": "Key from personal data used"},
                    "sensitive": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
            },
        },
        "submit": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "label": {"type": "string"},
                "requires_approval": {"type": "boolean"},
            },
        },
        "captcha_detected": {"type": "boolean"},
        "complex_form": {"type": "boolean"},
        "extraction_hints": {
            "type": "array",
            "items": {"type": "string"},
            "description": "What confirmation data to look for after submit",
        },
        "notes": {"type": "string"},
    },
}


SYSTEM_PROMPT = """You are AutomationForge, a careful personal form-filling assistant.
You analyze web page accessibility snapshots and produce a JSON fill plan.

Rules:
1. Output ONLY valid JSON matching the schema — no markdown fences, no commentary.
2. Map personal data to form fields by label/name/placeholder/role. Prefer exact matches.
3. Never invent personal data. If a required field has no matching data, set action to "skip" and explain in reason.
4. Mark password, SSN, payment, and similar fields as sensitive=true. Prefer skip unless data is explicitly provided.
5. Detect CAPTCHAs / bot checks → captcha_detected=true. Do not propose bypass steps.
6. Identify the primary submit button. Always set requires_approval=true.
7. Prefer stable selectors: #id, [name=...], [aria-label=...], or role+name.
8. For checkboxes/radios use check/uncheck or click. For dropdowns use select with visible option text as value.
9. If the page is multi-step, wizard, or heavily JS-driven with unclear controls, set complex_form=true and only fill clear fields.
10. Human-in-the-loop: never assume consent for marketing checkboxes; leave unchecked unless personal data says otherwise.
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty LLM response")
    # Strip markdown fences if present
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    # Find outermost object
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def _personal_data_for_prompt(personal: dict[str, Any]) -> dict[str, Any]:
    """Strip internal keys before sending to the model."""
    return {k: v for k, v in personal.items() if not str(k).startswith("_")}


class LLMAgent:
    """Ollama-first LLM client with OpenAI-compatible and Anthropic fallbacks."""

    def __init__(self) -> None:
        self.provider = (config.LLM_PROVIDER or "auto").lower()
        self.last_provider_used: str | None = None

    def analyze_page(
        self,
        *,
        url: str,
        accessibility_snapshot: str,
        personal_data: dict[str, Any],
        profile_name: str = "general",
        extra_instructions: str = "",
    ) -> dict[str, Any]:
        user_prompt = self._build_user_prompt(
            url=url,
            accessibility_snapshot=accessibility_snapshot,
            personal_data=personal_data,
            profile_name=profile_name,
            extra_instructions=extra_instructions,
        )
        raw = self._complete(SYSTEM_PROMPT, user_prompt)
        plan = _extract_json(raw)
        plan = self._normalize_plan(plan)
        plan["_provider"] = self.last_provider_used
        return plan

    def extract_confirmation(
        self,
        *,
        url: str,
        page_text: str,
        accessibility_snapshot: str,
        fill_plan: dict[str, Any],
    ) -> dict[str, Any]:
        hints = fill_plan.get("extraction_hints") or []
        system = (
            "Extract confirmation / reference data from a post-submit page. "
            "Return ONLY JSON: "
            '{"confirmation":"...", "extracted":{...}, "success_likely":true/false, "notes":"..."}'
        )
        user = (
            f"URL: {url}\n"
            f"Hints: {json.dumps(hints)}\n\n"
            f"Page text (truncated):\n{page_text[:8000]}\n\n"
            f"Accessibility snapshot (truncated):\n{accessibility_snapshot[:6000]}\n"
        )
        raw = self._complete(system, user)
        try:
            data = _extract_json(raw)
        except Exception:
            data = {
                "confirmation": "",
                "extracted": {},
                "success_likely": False,
                "notes": "Failed to parse extraction JSON",
            }
        if not isinstance(data.get("extracted"), dict):
            data["extracted"] = {}
        return data

    def _build_user_prompt(
        self,
        *,
        url: str,
        accessibility_snapshot: str,
        personal_data: dict[str, Any],
        profile_name: str,
        extra_instructions: str,
    ) -> str:
        schema_hint = json.dumps(FILL_PLAN_SCHEMA, indent=2)
        pdata = json.dumps(_personal_data_for_prompt(personal_data), indent=2, ensure_ascii=False)
        # Cap snapshot size for context windows
        snap = accessibility_snapshot[:20000]
        extra = f"\nExtra instructions from user:\n{extra_instructions}\n" if extra_instructions else ""
        return (
            f"URL: {url}\n"
            f"Application profile: {profile_name}\n"
            f"{extra}\n"
            f"Personal data (use only these values):\n{pdata}\n\n"
            f"Accessibility snapshot:\n{snap}\n\n"
            f"Respond with JSON matching this schema:\n{schema_hint}\n"
        )

    def _normalize_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        plan.setdefault("fields", [])
        plan.setdefault("captcha_detected", False)
        plan.setdefault("complex_form", False)
        plan.setdefault("notes", "")
        plan.setdefault("extraction_hints", [])
        submit = plan.get("submit") or {}
        if not isinstance(submit, dict):
            submit = {}
        submit["requires_approval"] = True  # CRITICAL safety invariant
        plan["submit"] = submit
        # Ensure fields are list of dicts
        cleaned = []
        for item in plan.get("fields") or []:
            if not isinstance(item, dict):
                continue
            item.setdefault("action", "fill")
            item.setdefault("value", "")
            item.setdefault("sensitive", False)
            cleaned.append(item)
        plan["fields"] = cleaned
        return plan

    # ── providers ──────────────────────────────────────────────────────────

    def _complete(self, system: str, user: str) -> str:
        order = self._provider_order()
        errors: list[str] = []
        for name in order:
            try:
                if name == "ollama":
                    text = self._call_ollama(system, user)
                elif name == "openai":
                    text = self._call_openai(system, user)
                elif name == "anthropic":
                    text = self._call_anthropic(system, user)
                else:
                    continue
                self.last_provider_used = name
                return text
            except Exception as exc:  # noqa: BLE001 — try next provider
                errors.append(f"{name}: {exc}")
        raise RuntimeError(
            "All LLM providers failed. Configure Ollama or set OPENAI_API_KEY / ANTHROPIC_API_KEY.\n"
            + "\n".join(errors)
        )

    def _provider_order(self) -> list[str]:
        if self.provider == "ollama":
            return ["ollama"]
        if self.provider == "openai":
            return ["openai"]
        if self.provider == "anthropic":
            return ["anthropic"]
        # auto: local first, then APIs
        order = ["ollama"]
        if config.OPENAI_API_KEY:
            order.append("openai")
        if config.ANTHROPIC_API_KEY:
            order.append("anthropic")
        return order

    def _call_ollama(self, system: str, user: str) -> str:
        url = f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/chat"
        payload = {
            "model": config.OLLAMA_MODEL,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": config.LLM_TEMPERATURE,
                "num_predict": config.LLM_MAX_TOKENS,
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        with httpx.Client(timeout=120.0) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        msg = data.get("message") or {}
        content = msg.get("content") or data.get("response") or ""
        if not content:
            raise RuntimeError(f"Empty Ollama response: {data!r}")
        return content

    def _call_openai(self, system: str, user: str) -> str:
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not set")
        url = f"{config.OPENAI_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config.OPENAI_MODEL,
            "temperature": config.LLM_TEMPERATURE,
            "max_tokens": config.LLM_MAX_TOKENS,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        with httpx.Client(timeout=120.0) as client:
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"]

    def _call_anthropic(self, system: str, user: str) -> str:
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": config.ANTHROPIC_MODEL,
            "max_tokens": config.LLM_MAX_TOKENS,
            "temperature": config.LLM_TEMPERATURE,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        with httpx.Client(timeout=120.0) as client:
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        parts = data.get("content") or []
        texts = [p.get("text", "") for p in parts if p.get("type") == "text"]
        content = "\n".join(texts).strip()
        if not content:
            raise RuntimeError(f"Empty Anthropic response: {data!r}")
        return content

    def healthcheck(self) -> dict[str, Any]:
        """Report which providers look available."""
        status: dict[str, Any] = {"preferred": self.provider, "providers": {}}
        # Ollama
        try:
            with httpx.Client(timeout=3.0) as client:
                r = client.get(f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/tags")
                ok = r.status_code == 200
                models = [m.get("name") for m in (r.json().get("models") or [])] if ok else []
                status["providers"]["ollama"] = {"ok": ok, "models": models, "model": config.OLLAMA_MODEL}
        except Exception as exc:  # noqa: BLE001
            status["providers"]["ollama"] = {"ok": False, "error": str(exc)}
        status["providers"]["openai"] = {
            "ok": bool(config.OPENAI_API_KEY),
            "model": config.OPENAI_MODEL,
            "base_url": config.OPENAI_BASE_URL,
        }
        status["providers"]["anthropic"] = {
            "ok": bool(config.ANTHROPIC_API_KEY),
            "model": config.ANTHROPIC_MODEL,
        }
        return status
