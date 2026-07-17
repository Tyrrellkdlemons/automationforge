"""
Three hardcoded sign-up flows for submission processing.

IMPORTANT: URLs below are PLACEHOLDERS (example.com). Edit FLOW_*_URL env vars
or the constants in this file to point at your real target forms before production use.
Legitimate personal / authorized use only — respect each site's Terms of Service.
"""

from __future__ import annotations

import os
import secrets
import string
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class FlowDef:
    key: str
    label: str
    url: str
    profile_hint: str
    extra_instructions: str


def _gen_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_flows() -> list[FlowDef]:
    """Return the three distinct sign-up flows (edit URLs for real targets)."""
    return [
        FlowDef(
            key="newsletter",
            label="Newsletter subscription",
            url=os.getenv(
                "FLOW_NEWSLETTER_URL",
                "https://example.com/newsletter-signup",
            ),
            profile_hint="registration",
            extra_instructions=(
                "This is a newsletter sign-up. Fill name and email only. "
                "Do not invent a password. Skip optional marketing checkboxes unless required."
            ),
        ),
        FlowDef(
            key="saas_trial",
            label="SaaS free trial account",
            url=os.getenv(
                "FLOW_SAAS_TRIAL_URL",
                "https://example.com/trial-signup",
            ),
            profile_hint="registration",
            extra_instructions=(
                "This is a free trial SaaS account form. Fill full name, email, and password. "
                "Use the password provided in personal data (generated_password). "
                "Accept terms if required to continue."
            ),
        ),
        FlowDef(
            key="job_profile",
            label="Job-board profile",
            url=os.getenv(
                "FLOW_JOB_PROFILE_URL",
                "https://example.com/job-profile-create",
            ),
            profile_hint="job_application",
            extra_instructions=(
                "This is a job-board profile. Fill name, date of birth, address, email, phone if present. "
                "Skip resume upload if optional. Do not invent employment history."
            ),
        ),
    ]


def build_personal_from_submission(submission: dict[str, Any]) -> dict[str, Any]:
    """Build a temporary AutomationForge personal-data dict from a Firestore submission."""
    from address_utils import format_address_line, resolve_address

    first = str(submission.get("firstName") or "").strip()
    last = str(submission.get("lastName") or "").strip()
    email = str(submission.get("email") or "").strip()
    dob = str(submission.get("dob") or submission.get("dateOfBirth") or "").strip()
    address, randomized = resolve_address(submission.get("address"))
    password = submission.get("generated_password") or _gen_password()

    return {
        "first_name": first,
        "last_name": last,
        "full_name": f"{first} {last}".strip(),
        "email": email,
        "phone": str(submission.get("phone") or ""),
        "date_of_birth": dob,
        "address": address,
        "address_line": format_address_line(address),
        "generated_password": password,
        "password": password,
        "address_randomized": randomized,
        "notes": "Temporary profile built from public submission.",
        "custom_fields": {},
    }


ApproveFn = Callable[[dict[str, Any]], bool]
CaptchaFn = Callable[[], bool]
ProgressFn = Callable[[str], None]


def run_single_flow(
    flow: FlowDef,
    personal: dict[str, Any],
    *,
    headless: bool | None = None,
    approve_submit: ApproveFn | None = None,
    on_captcha: CaptchaFn | None = None,
    progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """
    Run one sign-up flow using existing BrowserController + LLMAgent.
    Still requires explicit submit approval via approve_submit (CLI or GUI).
    """
    from automationforge import config
    from automationforge.browser_controller import BrowserController
    from automationforge.llm_agent import LLMAgent

    log = progress or (lambda _m: None)
    result: dict[str, Any] = {
        "flow": flow.key,
        "label": flow.label,
        "url": flow.url,
        "ok": False,
        "status": "failed",
        "error": "",
        "fields_filled": [],
        "screenshots": [],
    }

    use_headless = config.HEADLESS if headless is None else headless
    llm = LLMAgent()

    try:
        log(f"▶️ Starting flow '{flow.label}' → {flow.url}")
        with BrowserController(headless=use_headless) as browser:
            log("🌐 Navigating…")
            browser.goto(flow.url)
            shot = browser.screenshot(f"{flow.key}_loaded")
            result["screenshots"].append(str(shot))
            log(f"📸 Screenshot saved: {shot.name}")

            log("🧠 Capturing accessibility snapshot + LLM fill plan…")
            snap = browser.accessibility_snapshot()
            plan = llm.analyze_page(
                url=flow.url,
                accessibility_snapshot=snap,
                personal_data=personal,
                profile_name=flow.profile_hint,
                extra_instructions=flow.extra_instructions,
            )
            log(
                f"📋 Plan ready: {len(plan.get('fields') or [])} fields, "
                f"captcha={plan.get('captcha_detected')}, complex={plan.get('complex_form')}"
            )

            def _captcha() -> bool:
                log("⏸️ CAPTCHA DETECTED – please solve in the browser window.")
                browser.screenshot(f"{flow.key}_captcha")
                if on_captcha:
                    return on_captcha()
                from rich.prompt import Confirm

                return Confirm.ask("CAPTCHA solved / continue?", default=True)

            def _sensitive(field: dict[str, Any]) -> bool:
                label = field.get("label") or field.get("name") or "field"
                log(f"⚠️ Sensitive field '{label}' — auto-allow for submission flows")
                return True

            fill = browser.execute_fill_plan(
                plan,
                on_captcha=_captcha,
                on_sensitive=_sensitive,
                progress=lambda m: log(f"  {m}"),
            )
            result["fields_filled"] = fill.get("fields_filled") or []
            for f in result["fields_filled"]:
                if f.get("status") == "filled":
                    log(
                        f"✅ Filled field '{f.get('label') or f.get('name')}' "
                        f"with {str(f.get('value') or '')[:40]}"
                    )

            browser.screenshot(f"{flow.key}_pre_submit")
            log("🔍 Searching for submit button…")
            log("⏸️ Submit pending your approval.")

            approved = False
            if approve_submit:
                approved = bool(approve_submit(plan))
            else:
                from rich.prompt import Confirm
                from rich.panel import Panel
                from rich.console import Console

                Console().print(
                    Panel(
                        f"[bold red]SUBMIT APPROVAL REQUIRED[/]\nFlow: {flow.label}\nURL: {flow.url}",
                        border_style="red",
                    )
                )
                approved = Confirm.ask("Approve SUBMIT?", default=False)

            if not approved:
                result["status"] = "filled_not_submitted"
                result["error"] = "Submit declined by operator"
                log("🛑 Submit skipped / cancelled by operator")
                result["screenshots"] = list(browser.screenshot_paths)
                return result

            try:
                browser.click_submit(plan)
                browser.screenshot(f"{flow.key}_post_submit")
                result["ok"] = True
                result["status"] = "success"
                log("✅ Submit clicked successfully")
            except Exception as exc:
                result["error"] = str(exc)
                result["status"] = "submit_failed"
                browser.screenshot(f"{flow.key}_submit_error")
                log(f"❌ Submit failed: {exc}")

            result["screenshots"] = list(browser.screenshot_paths)
    except Exception as exc:
        result["error"] = str(exc)
        result["status"] = "failed"
        log(f"❌ Flow error: {exc}")

    return result


def run_flow_with_retry(
    flow: FlowDef,
    personal: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """Run a flow; on failure retry once."""
    first = run_single_flow(flow, personal, **kwargs)
    if first.get("ok"):
        return first
    progress = kwargs.get("progress")
    if progress:
        progress(f"🔁 Retrying flow '{flow.label}' once…")
    second = run_single_flow(flow, personal, **kwargs)
    if not second.get("ok"):
        second["retried"] = True
        second["first_error"] = first.get("error")
    return second
