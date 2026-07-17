"""
AutomationForge v2 — Rich CLI orchestration loop.

Safety: every form SUBMIT requires explicit y/n approval.
Legitimate personal use only — you are responsible for ToS and applicable laws.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow running as `python main.py` from project root
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from automationforge import __version__
from automationforge.browser_controller import BrowserController
from automationforge.data_manager import DataManager, normalize_url
from automationforge.email_service import get_email_service, ManualEmailService
from automationforge.llm_agent import LLMAgent

console = Console()


BANNER = f"""
[bold cyan]AutomationForge[/] v{__version__}
Local-first personal web form assistant

[yellow]Safety[/]: Every SUBMIT requires your explicit approval (y/n).
No CAPTCHA bypass. Legitimate personal use only — you own ToS/legal compliance.
"""


def print_banner() -> None:
    console.print(Panel(BANNER.strip(), border_style="cyan"))


def choose_profile(dm: DataManager) -> str:
    profiles = dm.list_profiles()
    data = dm.load_personal_data()
    table = Table(title="Application profiles", show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=4)
    table.add_column("Profile")
    table.add_column("Description")
    for i, name in enumerate(profiles, 1):
        meta = (data.get("profiles") or {}).get(name) or {}
        table.add_row(str(i), name, meta.get("description", ""))
    console.print(table)
    raw = Prompt.ask("Select profile number or name", default="general")
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(profiles):
            return profiles[idx - 1]
    if raw in profiles:
        return raw
    console.print(f"[yellow]Unknown profile '{raw}', using general[/]")
    return "general" if "general" in profiles else profiles[0]


def run_email_step() -> dict[str, Any] | None:
    """Optional first step: create/verify email address for sign-up flows."""
    if not Confirm.ask("Run optional email sign-up / verification step?", default=False):
        return None

    provider = Prompt.ask(
        "Email provider",
        choices=["auto", "tigrmail", "gmail_imap", "manual"],
        default="auto",
    )
    try:
        svc = get_email_service(None if provider == "auto" else provider)
    except Exception as exc:
        console.print(f"[red]Email service error:[/] {exc}")
        svc = ManualEmailService()

    console.print(f"Using email service: [bold]{svc.name}[/]")
    local = Prompt.ask("Preferred local-part / alias (optional)", default="")
    try:
        address = svc.create_address(local or None)
    except Exception as exc:
        console.print(f"[yellow]Could not auto-create address:[/] {exc}")
        address = Prompt.ask("Enter email address to use")
        if isinstance(svc, ManualEmailService):
            svc.create_address(address)

    console.print(f"Email address: [green]{address}[/]")
    console.print("Use this address on the site. Then wait for a verification code/link if needed.")

    result: dict[str, Any] = {"provider": svc.name, "address": address, "code": None, "links": []}

    if Confirm.ask("Wait for a verification email now?", default=False):
        if svc.name == "manual":
            code = Prompt.ask("Paste the verification code (or leave blank)")
            result["code"] = code or None
        else:
            subject_filter = Prompt.ask("Subject must contain (optional)", default="")
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task("Waiting for email…", total=None)
                code = svc.wait_for_code(
                    address=address,
                    timeout_sec=180,
                    subject_contains=subject_filter or None,
                )
            if code:
                console.print(f"[green]Verification code:[/] {code}")
                result["code"] = code
            else:
                console.print("[yellow]Timed out waiting for code. Check inbox manually.[/]")
                msgs = []
                try:
                    msgs = svc.list_messages(address)
                except Exception:
                    pass
                if msgs:
                    latest = msgs[0]
                    result["links"] = latest.extract_links()[:5]
                    console.print(f"Latest subject: {latest.subject}")
                    if result["links"]:
                        console.print("Links found:")
                        for link in result["links"]:
                            console.print(f"  {link}")

    return result


def approve_submit(plan: dict[str, Any]) -> bool:
    submit = plan.get("submit") or {}
    console.print(
        Panel(
            f"[bold red]SUBMIT APPROVAL REQUIRED[/]\n\n"
            f"Button: {submit.get('label') or submit.get('selector') or '(unknown)'}\n"
            f"Page: {plan.get('page_title') or ''}\n"
            f"Purpose: {plan.get('page_purpose') or ''}\n\n"
            f"Nothing will be submitted unless you type [bold]y[/].",
            border_style="red",
        )
    )
    return Confirm.ask("Approve SUBMIT?", default=False)


def run_application(
    dm: DataManager,
    llm: LLMAgent,
    *,
    url: str,
    profile: str,
    email_info: dict[str, Any] | None = None,
    force: bool = False,
    extra_instructions: str = "",
) -> dict[str, Any]:
    """Full pipeline for one URL."""
    url = url.strip()
    if not url:
        raise ValueError("URL is empty")

    dup = None if force else dm.find_duplicate(url)
    if dup:
        console.print(
            Panel(
                f"[yellow]Duplicate detected[/] for {normalize_url(url)}\n"
                f"Previous: {dup.get('timestamp')} status={dup.get('status')} id={dup.get('id')}",
                border_style="yellow",
            )
        )
        if not Confirm.ask("Continue anyway?", default=False):
            entry = {
                "url": url,
                "profile": profile,
                "status": "skipped_duplicate",
                "notes": f"Matched prior entry {dup.get('id')}",
            }
            txt = dm.export_txt_summary({**entry, "url_normalized": normalize_url(url)})
            entry["txt_path"] = str(txt)
            return dm.append_log_entry(entry)

    personal = dm.resolve_profile(profile)
    if email_info and email_info.get("address"):
        # Prefill email from verification step when profile email is placeholder/empty
        personal["email"] = email_info["address"]
        if email_info.get("code"):
            personal["verification_code"] = email_info["code"]
            personal["custom_fields_verification_code"] = email_info["code"]

    console.print(f"[cyan]Profile:[/] {profile}  [cyan]URL:[/] {url}")

    fields_filled: list[dict[str, Any]] = []
    screenshots: list[str] = []
    status = "failed"
    confirmation = ""
    extracted: dict[str, Any] = {}
    error = ""
    plan: dict[str, Any] = {}

    try:
        with BrowserController() as browser:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Opening page…", total=None)
                browser.goto(url)
                progress.update(task, description="Capturing accessibility snapshot…")
                snap = browser.accessibility_snapshot()
                browser.screenshot("page_loaded")
                progress.update(task, description="LLM analyzing form…")
                plan = llm.analyze_page(
                    url=url,
                    accessibility_snapshot=snap,
                    personal_data=personal,
                    profile_name=profile,
                    extra_instructions=extra_instructions,
                )

            console.print(
                Panel(
                    f"[bold]{plan.get('page_title') or 'Page'}[/]\n"
                    f"{plan.get('page_purpose') or ''}\n"
                    f"Provider: {plan.get('_provider')} | "
                    f"Fields: {len(plan.get('fields') or [])} | "
                    f"CAPTCHA: {plan.get('captcha_detected')} | "
                    f"Complex: {plan.get('complex_form')}\n"
                    f"{plan.get('notes') or ''}",
                    title="Fill plan",
                    border_style="blue",
                )
            )

            if plan.get("complex_form"):
                console.print(
                    "[yellow]Complex form detected — will fill clear fields only. "
                    "You may need to finish remaining steps manually.[/]"
                )

            def on_captcha() -> bool:
                console.print(
                    "[bold yellow]CAPTCHA / bot check detected.[/]\n"
                    "Solve it in the browser window, then continue. "
                    "AutomationForge will never bypass CAPTCHAs."
                )
                return Confirm.ask("CAPTCHA solved / continue filling?", default=True)

            def on_sensitive(field: dict[str, Any]) -> bool:
                console.print(
                    f"[yellow]Sensitive field:[/] {field.get('label') or field.get('name')} "
                    f"→ value length {len(str(field.get('value') or ''))}"
                )
                return Confirm.ask("Fill this sensitive field?", default=False)

            result = browser.execute_fill_plan(
                plan,
                on_captcha=on_captcha,
                on_sensitive=on_sensitive,
                progress=lambda m: console.print(f"  {m}"),
            )
            fields_filled = result.get("fields_filled") or []
            screenshots = list(browser.screenshot_paths)

            if result.get("cancelled"):
                status = "cancelled"
                error = "; ".join(result.get("errors") or [])
            else:
                browser.screenshot("pre_submit")
                if approve_submit(plan):
                    try:
                        browser.click_submit(plan)
                        browser.screenshot("post_submit")
                        status = "submitted"
                        # Extract confirmation
                        with console.status("Extracting confirmation…"):
                            extraction = llm.extract_confirmation(
                                url=url,
                                page_text=browser.page_text(),
                                accessibility_snapshot=browser.accessibility_snapshot(),
                                fill_plan=plan,
                            )
                        confirmation = extraction.get("confirmation") or ""
                        extracted = extraction.get("extracted") or {}
                        if extraction.get("success_likely"):
                            status = "completed"
                        console.print(f"Confirmation: {confirmation or '(none parsed)'}")
                        if extracted:
                            console.print(f"Extracted: {extracted}")
                            if Confirm.ask("Merge extracted data into personal_data.json?", default=False):
                                dm.merge_extracted_into_personal(extracted, profile_name=profile)
                    except Exception as exc:
                        error = str(exc)
                        status = "submit_failed"
                        browser.screenshot("submit_error")
                        console.print(f"[red]Submit failed:[/] {exc}")
                        console.print("You can finish manually in the open browser if needed.")
                        Prompt.ask("Press Enter after you are done with the browser", default="")
                else:
                    status = "filled_not_submitted"
                    console.print("[yellow]Submit declined — form left filled for your review.[/]")
                    if Confirm.ask("Keep browser open for manual finish?", default=True):
                        Prompt.ask("Press Enter when finished", default="")

            screenshots = list(browser.screenshot_paths)

    except Exception as exc:
        error = str(exc)
        status = "failed"
        console.print(f"[red]Run failed:[/] {exc}")

    entry = {
        "id": f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "url": url,
        "profile": profile,
        "status": status,
        "fields_filled": [
            {
                "label": f.get("label") or f.get("name") or f.get("selector"),
                "value": f.get("value"),
                "status": f.get("status"),
                "field_key": f.get("field_key"),
            }
            for f in fields_filled
        ],
        "extracted": extracted,
        "confirmation": confirmation,
        "screenshots": screenshots,
        "error": error,
        "notes": plan.get("notes") or "",
    }
    txt_path = dm.export_txt_summary({**entry, "url_normalized": normalize_url(url)})
    entry["txt_path"] = str(txt_path)
    record = dm.append_log_entry(entry)
    console.print(f"[green]Logged[/] → {dm.log_path.name} | summary → {txt_path}")
    return record


def show_llm_health(llm: LLMAgent) -> None:
    health = llm.healthcheck()
    table = Table(title="LLM providers", show_header=True)
    table.add_column("Provider")
    table.add_column("Status")
    table.add_column("Detail")
    for name, info in (health.get("providers") or {}).items():
        ok = info.get("ok")
        detail = info.get("model") or info.get("error") or ""
        if name == "ollama" and info.get("models"):
            detail = f"model={info.get('model')} available={', '.join(info['models'][:5])}"
        table.add_row(name, "[green]ok[/]" if ok else "[red]no[/]", str(detail))
    console.print(table)
    console.print(f"Preferred mode: {health.get('preferred')}")


def main() -> None:
    print_banner()
    dm = DataManager()
    llm = LLMAgent()

    show_llm_health(llm)

    email_info = run_email_step()

    profile = choose_profile(dm)
    console.print(f"Active profile: [bold]{profile}[/]")

    force_default = False
    while True:
        console.print()
        url = Prompt.ask(
            "[bold]Paste application URL[/] (or [cyan]q[/]=quit, [cyan]p[/]=profile, "
            "[cyan]e[/]=email, [cyan]h[/]=health)"
        ).strip()
        if not url:
            continue
        low = url.lower()
        if low in {"q", "quit", "exit"}:
            console.print("Goodbye.")
            break
        if low in {"p", "profile"}:
            profile = choose_profile(dm)
            continue
        if low in {"e", "email"}:
            email_info = run_email_step()
            continue
        if low in {"h", "health"}:
            show_llm_health(llm)
            continue

        extra = Prompt.ask("Extra instructions for this form (optional)", default="")
        force = Confirm.ask("Force run even if duplicate URL?", default=force_default)

        try:
            run_application(
                dm,
                llm,
                url=url,
                profile=profile,
                email_info=email_info,
                force=force,
                extra_instructions=extra,
            )
        except Exception as exc:
            console.print(f"[red]Unhandled error:[/] {exc}")

        if not Confirm.ask("Process another URL?", default=True):
            break

    console.print("[dim]Remember: you are responsible for site ToS and applicable laws.[/]")


if __name__ == "__main__":
    main()
