"""
Submission worker — polls Firestore for new submissions and runs 3 sign-up flows.

Usage:
  python worker.py
  python main.py --worker

Skips submissions with status == "manual" or manualOverride == true.
Every external-site SUBMIT still requires explicit operator y/n approval.
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

from address_utils import resolve_address
from email_sender import send_unique_id_email
from firebase_client import (
    firestore_ready,
    get_submission,
    list_new_submissions,
    update_submission,
)
from signup_flows import build_personal_from_submission, get_flows, run_flow_with_retry
from unique_id_generator import issue_unique_id

console = Console()


def _poll_interval() -> int:
    return max(5, int(os.getenv("WORKER_POLL_INTERVAL_SEC", "30")))


def process_submission(submission: dict[str, Any], *, interactive: bool = True) -> dict[str, Any]:
    """Process one submission end-to-end. Returns summary dict."""
    sid = submission["id"]
    console.print(Panel(f"Processing submission [bold]{sid}[/]", border_style="cyan"))

    update_submission(sid, {"status": "processing"})

    # Persist randomized address back onto the submission when needed
    address, randomized = resolve_address(submission.get("address"))
    if randomized:
        update_submission(sid, {"address": address, "addressRandomized": True})
        submission["address"] = address

    personal = build_personal_from_submission(submission)
    update_submission(sid, {"generated_password": personal.get("generated_password")})

    flows_state: dict[str, Any] = {}
    all_ok = True

    for flow in get_flows():
        console.rule(f"[bold]{flow.label}[/]")

        def progress(msg: str) -> None:
            console.print(msg)

        result = run_flow_with_retry(
            flow,
            personal,
            headless=False,
            progress=progress,
        )
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

    if not all_ok:
        update_submission(
            sid,
            {
                "status": "failed",
                "flows": flows_state,
                "error": "One or more sign-up flows failed",
            },
        )
        return {"id": sid, "status": "failed", "flows": flows_state}

    number, msg = issue_unique_id(sid)
    if not number:
        update_submission(
            sid,
            {
                "status": "failed",
                "humanReviewRequired": True,
                "error": f"Unique ID generation failed: {msg}",
                "flows": flows_state,
            },
        )
        console.print(f"[red]Unique ID failed:[/] {msg}")
        return {"id": sid, "status": "failed", "error": msg}

    email_result = send_unique_id_email(
        submission.get("email") or "",
        number,
        first_name=str(submission.get("firstName") or ""),
    )
    update_submission(
        sid,
        {
            "status": "completed",
            "issued_id": number,
            "flows": flows_state,
            "emailSent": bool(email_result.get("ok")),
            "emailError": email_result.get("error"),
            "idIssueNote": msg,
        },
    )
    console.print(f"[green]Completed[/] {sid} → issued_id={number} email_ok={email_result.get('ok')}")
    return {
        "id": sid,
        "status": "completed",
        "issued_id": number,
        "email": email_result,
        "flows": flows_state,
    }


def run_worker_loop(*, once: bool = False) -> None:
    ok, detail = firestore_ready()
    if not ok:
        console.print(f"[red]Firebase not ready:[/] {detail}")
        raise SystemExit(1)

    interval = _poll_interval()
    console.print(
        Panel(
            f"Worker polling every {interval}s for status=='new'\n"
            "Skips status=='manual'. Every site SUBMIT still needs your y/n.",
            title="AutomationForge Worker",
            border_style="green",
        )
    )

    while True:
        try:
            batch = list_new_submissions(limit=5)
            if not batch:
                console.print("[dim]No new submissions…[/]")
            for sub in batch:
                # Re-check live status to avoid racing with manual takeover
                live = get_submission(sub["id"]) or sub
                if live.get("status") == "manual" or live.get("manualOverride"):
                    console.print(f"[yellow]Skip manual submission[/] {sub['id']}")
                    continue
                try:
                    process_submission(live)
                except Exception as exc:
                    console.print(f"[red]Worker error on {sub['id']}:[/] {exc}")
                    try:
                        update_submission(
                            sub["id"],
                            {"status": "failed", "error": str(exc)},
                        )
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
