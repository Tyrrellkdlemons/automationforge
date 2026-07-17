"""
Submission worker — polls Firestore, issues ID + confirmation first, then runs flows.

Usage:
  python worker.py
  python main.py --worker
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rich.console import Console
from rich.panel import Panel

from address_utils import format_address_line, resolve_address
from email_sender import send_confirmation_email
from field_randomizer import ensure_randomized_fields
from firebase_client import (
    firestore_ready,
    get_submission,
    list_new_submissions,
    update_submission,
)
from signup_flows import build_personal_from_submission, get_flows, run_flow_with_retry
from sms_sender import send_unique_id_sms
from unique_id_generator import issue_unique_id

console = Console()


def _poll_interval() -> int:
    return max(5, int(os.getenv("WORKER_POLL_INTERVAL_SEC", "30")))


def prepare_submission_identity(submission: dict[str, Any]) -> dict[str, Any]:
    """Resolve state address, random fields, issue unique ID, send confirmation — BEFORE flows."""
    sid = submission["id"]
    state = submission.get("state") or (submission.get("address") or {}).get("state")
    address, generated = resolve_address(submission.get("address"), state=state)
    randomized = ensure_randomized_fields({**submission, "address": address})

    patch: dict[str, Any] = {
        "address": address,
        "state": address.get("state"),
        "addressRandomized": generated,
        "generatedAddress": address if generated else None,
        "randomized_fields": randomized,
        "generated_password": randomized.get("password"),
        "followup_sent": bool(submission.get("followup_sent")),
    }
    update_submission(sid, patch)
    submission.update(patch)

    # Issue ID immediately (before flows)
    number = submission.get("issued_id")
    if not number:
        number, msg = issue_unique_id(sid)
        if not number:
            update_submission(
                sid,
                {"humanReviewRequired": True, "error": f"Unique ID generation failed: {msg}"},
            )
            raise RuntimeError(f"Unique ID failed: {msg}")
        update_submission(sid, {"issued_id": number, "idIssueNote": msg, "idIssuedEarly": True})
        submission["issued_id"] = number

    # Confirmation email + optional SMS before flows
    if not submission.get("confirmationEmailSent"):
        email_result = send_confirmation_email(
            to_email=str(submission.get("email") or ""),
            first_name=str(submission.get("firstName") or ""),
            last_name=str(submission.get("lastName") or ""),
            address_line=format_address_line(address),
            unique_id=str(number),
        )
        phone = str(submission.get("phone") or randomized.get("phone_alt") or "")
        sms_result = send_unique_id_sms(phone, str(number)) if phone else {"ok": True, "skipped": True}
        update_submission(
            sid,
            {
                "confirmationEmailSent": bool(email_result.get("ok")),
                "confirmationEmailError": email_result.get("error"),
                "smsSent": bool(sms_result.get("ok")) and not sms_result.get("skipped"),
                "smsError": sms_result.get("error"),
            },
        )
        console.print(
            f"[cyan]Confirmation[/] email_ok={email_result.get('ok')} "
            f"sms_ok={sms_result.get('ok')} id={number}"
        )

    return submission


def process_submission(submission: dict[str, Any], *, interactive: bool = True) -> dict[str, Any]:
    sid = submission["id"]
    console.print(Panel(f"Processing submission [bold]{sid}[/]", border_style="cyan"))
    update_submission(sid, {"status": "processing"})

    try:
        submission = prepare_submission_identity(submission)
    except Exception as exc:
        update_submission(sid, {"status": "failed", "error": str(exc)})
        return {"id": sid, "status": "failed", "error": str(exc)}

    personal = build_personal_from_submission(submission)
    # Merge randomized fields into personal profile for LLM fills
    for k, v in (submission.get("randomized_fields") or {}).items():
        personal[k] = v
        if k == "password":
            personal["generated_password"] = v
            personal["password"] = v

    flows_state: dict[str, Any] = dict(submission.get("flows") or {})
    all_ok = True

    for flow in get_flows():
        console.rule(f"[bold]{flow.label}[/]")

        def progress(msg: str) -> None:
            console.print(msg)

        result = run_flow_with_retry(flow, personal, headless=False, progress=progress)
        flows_state[flow.key] = {
            "status": "success" if result.get("ok") else "failed",
            "error": result.get("error"),
            "detail_status": result.get("status"),
            "screenshots": result.get("screenshots") or [],
        }
        update_submission(sid, {"flows": flows_state})
        if not result.get("ok"):
            all_ok = False
            console.print(f"[red]Flow failed:[/] {flow.key} — {result.get('error')}")

    final_status = "completed" if all_ok else "failed"
    update_submission(
        sid,
        {
            "status": final_status,
            "flows": flows_state,
            "error": None if all_ok else "One or more sign-up flows failed",
            "followup_sent": bool(submission.get("followup_sent")),
        },
    )
    console.print(f"[green]Done[/] {sid} status={final_status} id={submission.get('issued_id')}")
    return {"id": sid, "status": final_status, "issued_id": submission.get("issued_id"), "flows": flows_state}


def run_worker_loop(*, once: bool = False) -> None:
    ok, detail = firestore_ready()
    if not ok:
        console.print(f"[red]Firebase not ready:[/] {detail}")
        raise SystemExit(1)

    interval = _poll_interval()
    console.print(
        Panel(
            f"Worker polling every {interval}s · skips status==manual\n"
            "Issues unique ID + confirmation email BEFORE flows. Site submits still need y/n.",
            title="PeeezMachine Worker",
            border_style="green",
        )
    )

    while True:
        try:
            batch = list_new_submissions(limit=5)
            if not batch:
                console.print("[dim]No new submissions…[/]")
            for sub in batch:
                live = get_submission(sub["id"]) or sub
                if live.get("status") == "manual" or live.get("manualOverride"):
                    console.print(f"[yellow]Skip manual[/] {sub['id']}")
                    continue
                try:
                    process_submission(live)
                except Exception as exc:
                    console.print(f"[red]Worker error on {sub['id']}:[/] {exc}")
                    try:
                        update_submission(sub["id"], {"status": "failed", "error": str(exc)})
                    except Exception:
                        pass
        except Exception as exc:
            console.print(f"[red]Poll error:[/] {exc}")

        if once:
            break
        time.sleep(interval)


def main() -> None:
    once = "--once" in sys.argv
    run_worker_loop(once=once)


if __name__ == "__main__":
    main()
