"""
AutomationForge v2 — Streamlit dashboard.

Run:  streamlit run streamlit_app.py

Pages:
  • Local fill — personal URL pipeline (same safety rules as CLI)
  • Submissions — Firestore admin table + worker retry
  • Manual handling — operator GUI for one submission / one flow at a time

Every external-site SUBMIT still requires explicit operator approval.
"""

from __future__ import annotations

import html
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from automationforge.browser_controller import BrowserController
from automationforge.data_manager import DataManager, normalize_url
from automationforge.llm_agent import LLMAgent
from email_sender import send_unique_id_email
from firebase_client import (
    append_manual_log,
    firestore_ready,
    get_submission,
    list_submissions,
    submission_stats,
    update_submission,
)
from manual_handler import ManualFlowRunner, flow_defs
from unique_id_generator import issue_unique_id
from worker import process_submission

PAGES = ["Local fill", "Submissions", "Manual handling"]

STATUS_PILL_CSS: dict[str, tuple[str, str]] = {
    "new": ("#1e3a5f", "#93c5fd"),
    "processing": ("#422006", "#fcd34d"),
    "manual": ("#3b0764", "#d8b4fe"),
    "completed": ("#052e16", "#86efac"),
    "failed": ("#450a0a", "#fca5a5"),
}

CUSTOM_CSS = """
<style>
.status-pill {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    white-space: nowrap;
}
.metric-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px;
    padding: 0.75rem 1rem;
}
.metric-card .label {
    font-size: 0.75rem;
    opacity: 0.7;
    text-transform: uppercase;
}
.metric-card .value {
    font-size: 1.6rem;
    font-weight: 700;
    line-height: 1.2;
}
.log-box {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.82rem;
    line-height: 1.45;
    background: #0b1220;
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px;
    padding: 0.75rem 1rem;
    max-height: 420px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
}
.log-line { margin: 0.15rem 0; }
.log-info { color: #94a3b8; }
.log-success { color: #4ade80; }
.log-warn { color: #fbbf24; }
.log-error { color: #f87171; }
.sub-row {
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px;
    padding: 0.85rem 1rem;
    margin-bottom: 0.65rem;
    background: rgba(255,255,255,0.02);
}
.summary-card {
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 10px;
    padding: 1rem 1.1rem;
    background: rgba(255,255,255,0.03);
}
</style>
"""


def _init_session_state() -> None:
    defaults: dict[str, Any] = {
        "nav_page": PAGES[0],
        "manual_sub_id": None,
        "manual_logs": [],
        "manual_shots": [],
        "await_submit": None,
        "await_captcha": None,
        "detail_ids": set(),
        "runner": ManualFlowRunner(),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def status_pill_html(status: str) -> str:
    key = (status or "new").lower()
    bg, fg = STATUS_PILL_CSS.get(key, ("#374151", "#e5e7eb"))
    label = html.escape(key)
    return (
        f'<span class="status-pill status-{label}" '
        f'style="background:{bg};color:{fg}">{label}</span>'
    )


def submission_display_name(sub: dict[str, Any]) -> str:
    first = str(sub.get("firstName") or "").strip()
    last = str(sub.get("lastName") or "").strip()
    name = f"{first} {last}".strip()
    return name or "(no name)"


def render_log_box(logs: list[dict[str, Any]]) -> None:
    if not logs:
        st.markdown('<div class="log-box"><span class="log-info">No log lines yet.</span></div>', unsafe_allow_html=True)
        return
    lines: list[str] = []
    for entry in logs[-400:]:
        level = html.escape(str(entry.get("level") or "info"))
        message = html.escape(str(entry.get("message") or ""))
        lines.append(f'<div class="log-line log-{level}">{message}</div>')
    st.markdown(f'<div class="log-box">{"".join(lines)}</div>', unsafe_allow_html=True)


def drain_runner_events() -> None:
    runner: ManualFlowRunner = st.session_state.runner
    sub_id = st.session_state.get("manual_sub_id")

    for ev in runner.drain():
        ev_type = ev.get("type")
        if ev_type == "log":
            line = str(ev.get("message") or "")
            level = str(ev.get("level") or "info")
            st.session_state.manual_logs.append({"level": level, "message": line})
            if sub_id and line:
                try:
                    append_manual_log(sub_id, line)
                except Exception:
                    pass
        elif ev_type == "screenshot":
            st.session_state.manual_shots.append(ev)
        elif ev_type == "await_submit":
            st.session_state.await_submit = ev
        elif ev_type == "await_captcha":
            st.session_state.await_captcha = ev
        elif ev_type == "done":
            st.session_state.await_submit = None
            st.session_state.await_captcha = None
            result = ev.get("result") or {}
            ok = result.get("ok")
            status = result.get("status") or ("success" if ok else "failed")
            msg = f"Flow finished: {status}"
            if result.get("error"):
                msg += f" — {result['error']}"
            st.session_state.manual_logs.append(
                {"level": "success" if ok else "error", "message": msg}
            )
            if sub_id:
                flow_key = ev.get("flow") or result.get("flow")
                if flow_key:
                    try:
                        live = get_submission(sub_id) or {}
                        flows = dict(live.get("flows") or {})
                        flows[flow_key] = {
                            "status": "success" if ok else "failed",
                            "error": result.get("error"),
                            "detail_status": status,
                            "screenshots": result.get("screenshots") or [],
                        }
                        update_submission(sub_id, {"flows": flows})
                    except Exception:
                        pass
        elif ev_type == "error":
            st.session_state.await_submit = None
            st.session_state.await_captcha = None
            msg = str(ev.get("message") or "Unknown error")
            st.session_state.manual_logs.append({"level": "error", "message": msg})
            if sub_id:
                try:
                    append_manual_log(sub_id, f"ERROR: {msg}")
                except Exception:
                    pass


def render_local_fill(dm: DataManager, llm: LLMAgent) -> None:
    with st.sidebar:
        st.header("Local fill settings")
        profiles = dm.list_profiles()
        profile = st.selectbox(
            "Application profile",
            profiles,
            index=profiles.index("general") if "general" in profiles else 0,
            key="local_profile",
        )
        force = st.checkbox("Force run (ignore duplicate URL)", value=False, key="local_force")
        merge_extracted = st.checkbox(
            "Merge extracted data into personal_data.json",
            value=False,
            key="local_merge",
        )
        st.divider()
        if st.button("Refresh LLM health", key="local_health_btn"):
            st.session_state["health"] = llm.healthcheck()
        health = st.session_state.get("health") or llm.healthcheck()
        st.json(health)
        st.divider()
        st.caption("Edit `personal_data.json` or use the public submit form.")

    st.header("Local fill")
    st.caption(
        "Run the personal form assistant against 1–5 URLs. "
        "Every SUBMIT requires your explicit approval."
    )

    url_block = st.text_area(
        "Application URL(s) — one per line, max 5",
        placeholder="https://example.com/apply\nhttps://another.com/form",
        height=110,
        key="local_urls",
    )
    extra = st.text_area("Extra instructions (optional)", height=80, key="local_extra")
    approve_submit = st.checkbox(
        "I approve SUBMIT if a submit button is found (required to actually submit)",
        value=False,
        key="local_approve",
    )
    all_urls = [u.strip() for u in (url_block or "").splitlines() if u.strip()]
    urls = all_urls[:5]
    run = st.button("Run fill pipeline", type="primary", disabled=not urls, key="local_run")
    if len(all_urls) > 5:
        st.caption("Only the first 5 URLs will run.")

    if run and urls:
        for idx, url in enumerate(urls, 1):
            st.markdown(f"### Application {idx}/{len(urls)}")
            if not force:
                dup = dm.find_duplicate(url)
                if dup:
                    st.warning(
                        f"Duplicate URL found: {dup.get('id')} @ {dup.get('timestamp')} "
                        f"(status={dup.get('status')}). Enable force to continue."
                    )
                    continue

            personal = dm.resolve_profile(profile)
            status_box = st.empty()
            log_box = st.empty()
            lines: list[str] = []

            def log(msg: str, _lines: list[str] = lines, _box: Any = log_box) -> None:
                _lines.append(msg)
                _box.code("\n".join(_lines))

            fields_filled: list = []
            screenshots: list[str] = []
            status = "failed"
            confirmation = ""
            extracted: dict = {}
            error = ""
            plan: dict = {}

            try:
                status_box.info("Starting browser…")
                with BrowserController(headless=False) as browser:
                    status_box.info("Loading page…")
                    browser.goto(url)
                    snap = browser.accessibility_snapshot()
                    browser.screenshot("streamlit_loaded")
                    status_box.info("Analyzing with LLM…")
                    plan = llm.analyze_page(
                        url=url,
                        accessibility_snapshot=snap,
                        personal_data=personal,
                        profile_name=profile,
                        extra_instructions=extra,
                    )
                    st.subheader("Fill plan")
                    st.json({k: v for k, v in plan.items() if not str(k).startswith("_")})

                    if plan.get("captcha_detected"):
                        st.warning(
                            "CAPTCHA detected. Solve it in the browser window, then continue."
                        )
                        if not st.button(f"Continue after CAPTCHA ({idx})", key=f"captcha_{idx}"):
                            continue

                    status_box.info("Filling fields…")
                    result = browser.execute_fill_plan(
                        plan,
                        on_captcha=lambda: True,
                        on_sensitive=lambda f: st.session_state.get("fill_sensitive", False),
                        progress=log,
                    )
                    fields_filled = result.get("fields_filled") or []
                    browser.screenshot("streamlit_pre_submit")

                    if approve_submit:
                        status_box.info("Submitting (approved)…")
                        try:
                            browser.click_submit(plan)
                            browser.screenshot("streamlit_post_submit")
                            extraction = llm.extract_confirmation(
                                url=url,
                                page_text=browser.page_text(),
                                accessibility_snapshot=browser.accessibility_snapshot(),
                                fill_plan=plan,
                            )
                            confirmation = extraction.get("confirmation") or ""
                            extracted = extraction.get("extracted") or {}
                            status = "completed" if extraction.get("success_likely") else "submitted"
                        except Exception as exc:
                            error = str(exc)
                            status = "submit_failed"
                            browser.screenshot("streamlit_submit_error")
                            st.error(f"Submit failed: {exc}")
                    else:
                        status = "filled_not_submitted"
                        st.info("Submit not approved — form left filled for review.")

                    screenshots = list(browser.screenshot_paths)
                    status_box.success(f"Done: {status}")

            except Exception as exc:
                error = str(exc)
                status = "failed"
                st.error(f"Run failed: {exc}")

            entry = {
                "id": f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{idx}",
                "url": url,
                "profile": profile,
                "status": status,
                "fields_filled": [
                    {
                        "label": f.get("label") or f.get("name") or f.get("selector"),
                        "value": f.get("value"),
                        "status": f.get("status"),
                    }
                    for f in fields_filled
                ],
                "extracted": extracted,
                "confirmation": confirmation,
                "screenshots": screenshots,
                "error": error,
                "notes": (plan or {}).get("notes") or "streamlit",
            }
            if merge_extracted and extracted:
                dm.merge_extracted_into_personal(extracted, profile_name=profile)
            txt_path = dm.export_txt_summary({**entry, "url_normalized": normalize_url(url)})
            entry["txt_path"] = str(txt_path)
            dm.append_log_entry(entry)
            st.write(f"Logged → `{dm.log_path.name}` | summary → `{txt_path}`")

    st.divider()
    st.subheader("Recent application log")
    log_data = dm.load_application_log()
    entries = list(reversed(log_data.get("entries") or []))[:20]
    if entries:
        st.dataframe(
            [
                {
                    "id": e.get("id"),
                    "timestamp": e.get("timestamp"),
                    "profile": e.get("profile"),
                    "status": e.get("status"),
                    "url": e.get("url"),
                }
                for e in entries
            ],
            use_container_width=True,
        )
    else:
        st.write("No entries yet.")


def render_submissions() -> None:
    st.header("Submissions")
    st.caption("Firestore admin view — take over, retry, or inspect public form submissions.")

    with st.sidebar:
        st.header("Submissions")
        if st.button("Refresh list", key="sub_refresh"):
            st.rerun()

    ok, detail = firestore_ready()
    if not ok:
        st.error(f"Firebase not ready: {detail}")
        st.info("Set FIREBASE_SERVICE_ACCOUNT_PATH or FIREBASE_SERVICE_ACCOUNT_JSON in `.env`.")
        return

    try:
        stats = submission_stats()
        rows = list_submissions(limit=100)
    except Exception as exc:
        st.error(f"Failed to load submissions: {exc}")
        return

    m1, m2, m3, m4, m5 = st.columns(5)
    for col, key, label in zip(
        (m1, m2, m3, m4, m5),
        ("total", "new", "processing", "completed", "failed"),
        ("Total", "New", "Processing", "Completed", "Failed"),
    ):
        with col:
            st.markdown(
                f'<div class="metric-card"><div class="label">{label}</div>'
                f'<div class="value">{stats.get(key, 0)}</div></div>',
                unsafe_allow_html=True,
            )

    if not rows:
        st.info("No submissions yet.")
        return

    st.divider()
    for sub in rows:
        sid = sub.get("id") or ""
        name = submission_display_name(sub)
        email = sub.get("email") or "—"
        created = sub.get("createdAt") or "—"
        status = (sub.get("status") or "new").lower()
        issued = sub.get("issued_id") or "—"

        st.markdown(
            f'<div class="sub-row">'
            f'<strong>{html.escape(name)}</strong> &nbsp;·&nbsp; '
            f'{html.escape(str(email))} &nbsp;·&nbsp; '
            f'<span style="opacity:0.7">{html.escape(str(created))}</span> &nbsp;·&nbsp; '
            f'{status_pill_html(status)} &nbsp;·&nbsp; '
            f'<span style="opacity:0.8">ID: {html.escape(str(issued))}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Take Over", key=f"takeover_{sid}"):
                try:
                    update_submission(
                        sid,
                        {"status": "manual", "manualOverride": True},
                    )
                    st.session_state.manual_sub_id = sid
                    st.session_state.manual_logs = []
                    st.session_state.manual_shots = []
                    st.session_state.await_submit = None
                    st.session_state.await_captcha = None
                    st.session_state.nav_page = "Manual handling"
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        with c2:
            if st.button("Retry Auto", key=f"retry_{sid}"):
                try:
                    update_submission(sid, {"status": "new", "manualOverride": False})
                    fresh = get_submission(sid) or sub
                    with st.spinner(f"Processing {sid}…"):
                        process_submission(fresh)
                    st.success("Worker finished — refresh list to see updated status.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Retry failed: {exc}")
        with c3:
            show = sid in st.session_state.detail_ids
            if st.button(
                "Hide Details" if show else "View Details",
                key=f"details_{sid}",
            ):
                if show:
                    st.session_state.detail_ids.discard(sid)
                else:
                    st.session_state.detail_ids.add(sid)
                st.rerun()

        if sid in st.session_state.detail_ids:
            st.json(sub)


def _address_fields(sub: dict[str, Any]) -> dict[str, str]:
    addr = sub.get("address") or {}
    if isinstance(addr, str):
        return {"street": addr, "city": "", "state": "", "zip": "", "country": "United States"}
    return {
        "street": str(addr.get("street") or ""),
        "city": str(addr.get("city") or ""),
        "state": str(addr.get("state") or ""),
        "zip": str(addr.get("zip") or addr.get("postal") or ""),
        "country": str(addr.get("country") or "United States"),
    }


def render_manual_handling() -> None:
    st.header("Manual handling")
    st.caption("Operator console — one submission, one flow at a time with live logs.")

    drain_runner_events()
    runner: ManualFlowRunner = st.session_state.runner

    ok, detail = firestore_ready()
    if not ok:
        st.error(f"Firebase not ready: {detail}")
        return

    try:
        rows = list_submissions(limit=100)
    except Exception as exc:
        st.error(f"Failed to load submissions: {exc}")
        return

    if not rows:
        st.info("No submissions available.")
        return

    options = {f"{submission_display_name(r)} ({r.get('id')})": r.get("id") for r in rows}
    labels = list(options.keys())
    preselect = st.session_state.manual_sub_id
    default_index = 0
    if preselect:
        for i, sid in enumerate(options.values()):
            if sid == preselect:
                default_index = i
                break

    with st.sidebar:
        st.header("Manual console")
        headed = st.toggle("Headed browser (visible window)", value=True, key="manual_headed")
        if st.button("Clear local logs", key="manual_clear_logs"):
            st.session_state.manual_logs = []
            st.session_state.manual_shots = []
            st.session_state.await_submit = None
            st.session_state.await_captcha = None
            st.rerun()
        if runner.busy:
            st.warning("Flow running…")

    selected_label = st.selectbox("Submission", labels, index=default_index, key="manual_pick")
    selected_id = options[selected_label]
    st.session_state.manual_sub_id = selected_id

    sub = get_submission(selected_id) or next((r for r in rows if r.get("id") == selected_id), {})
    if (sub.get("status") or "").lower() != "manual":
        try:
            update_submission(selected_id, {"status": "manual", "manualOverride": True})
            sub = get_submission(selected_id) or sub
        except Exception as exc:
            st.warning(f"Could not set manual status: {exc}")

    addr = _address_fields(sub)

    with st.container():
        st.markdown('<div class="summary-card">', unsafe_allow_html=True)
        st.subheader("Submission summary")
        sc1, sc2 = st.columns(2)
        with sc1:
            first_name = st.text_input("First name", value=str(sub.get("firstName") or ""), key="mh_fn")
            last_name = st.text_input("Last name", value=str(sub.get("lastName") or ""), key="mh_ln")
            email = st.text_input("Email", value=str(sub.get("email") or ""), key="mh_email")
            dob = st.text_input(
                "Date of birth (YYYY-MM-DD)",
                value=str(sub.get("dob") or sub.get("dateOfBirth") or ""),
                key="mh_dob",
            )
        with sc2:
            street = st.text_input("Street", value=addr["street"], key="mh_street")
            city = st.text_input("City", value=addr["city"], key="mh_city")
            state = st.text_input("State", value=addr["state"], key="mh_state")
            zip_code = st.text_input("ZIP", value=addr["zip"], key="mh_zip")

        if st.button("Save overrides", key="mh_save"):
            try:
                update_submission(
                    selected_id,
                    {
                        "firstName": first_name.strip(),
                        "lastName": last_name.strip(),
                        "email": email.strip().lower(),
                        "dob": dob.strip(),
                        "address": {
                            "street": street.strip(),
                            "city": city.strip(),
                            "state": state.strip(),
                            "zip": zip_code.strip(),
                            "country": addr.get("country") or "United States",
                        },
                    },
                )
                st.success("Overrides saved.")
                sub = get_submission(selected_id) or sub
            except Exception as exc:
                st.error(str(exc))

        meta_c1, meta_c2, meta_c3 = st.columns(3)
        with meta_c1:
            st.markdown(status_pill_html(sub.get("status") or "manual"), unsafe_allow_html=True)
        with meta_c2:
            st.write(f"**Issued ID:** {sub.get('issued_id') or '—'}")
        with meta_c3:
            st.write(f"**Created:** {sub.get('createdAt') or '—'}")
        st.markdown("</div>", unsafe_allow_html=True)

    flow_list = flow_defs()
    tab_labels = [f.label for f in flow_list]
    tabs = st.tabs(tab_labels)

    for tab, flow in zip(tabs, flow_list):
        with tab:
            st.write(f"**URL:** `{flow.url}`")
            flow_state = (sub.get("flows") or {}).get(flow.key) or {}
            st.caption(f"Last status: {flow_state.get('status') or 'pending'}")
            if flow_state.get("error"):
                st.warning(flow_state["error"])

            bc1, bc2 = st.columns(2)
            with bc1:
                start = st.button(
                    "Start flow",
                    key=f"start_{selected_id}_{flow.key}",
                    disabled=runner.busy,
                )
            with bc2:
                retry = st.button(
                    "Retry flow",
                    key=f"retry_{selected_id}_{flow.key}",
                    disabled=runner.busy,
                )

            if (start or retry) and not runner.busy:
                fresh = get_submission(selected_id) or sub
                started = runner.start_flow(fresh, flow.key, headed=headed)
                if started:
                    st.session_state.manual_logs.append(
                        {"level": "info", "message": f"Started flow: {flow.label}"}
                    )
                    st.rerun()
                else:
                    st.error("Could not start flow (runner busy or unknown flow).")

    st.subheader("Live log")
    render_log_box(st.session_state.manual_logs)

    await_submit = st.session_state.await_submit
    if await_submit:
        st.warning("Submit approval required for the running flow.")
        plan = await_submit.get("plan") or {}
        with st.expander("Submit plan preview", expanded=False):
            st.json({k: v for k, v in plan.items() if not str(k).startswith("_")})
        ac1, ac2 = st.columns(2)
        with ac1:
            if st.button("Approve Submit", type="primary", key="mh_approve"):
                runner.approve_submit(True)
                st.session_state.await_submit = None
                st.session_state.manual_logs.append(
                    {"level": "success", "message": "Submit approved by operator."}
                )
                st.rerun()
        with ac2:
            if st.button("Skip / Cancel submit", key="mh_skip"):
                runner.approve_submit(False)
                st.session_state.await_submit = None
                st.session_state.manual_logs.append(
                    {"level": "warn", "message": "Submit cancelled by operator."}
                )
                st.rerun()

    if st.session_state.await_captcha:
        st.warning("CAPTCHA detected — solve it in the visible browser window.")
        if st.button("Continue after CAPTCHA", type="primary", key="mh_captcha"):
            runner.captcha_continue()
            st.session_state.await_captcha = None
            st.session_state.manual_logs.append(
                {"level": "info", "message": "Operator continued after CAPTCHA."}
            )
            st.rerun()

    if st.session_state.manual_shots:
        st.subheader("Screenshots")
        for i, shot in enumerate(reversed(st.session_state.manual_shots[-20:])):
            path = shot.get("path")
            label = shot.get("label") or (Path(path).name if path else f"shot_{i}")
            with st.expander(label, expanded=(i == 0)):
                if path and Path(path).exists():
                    st.image(str(path), use_container_width=True)
                else:
                    preview = shot.get("preview_b64")
                    if preview:
                        st.image(f"data:image/png;base64,{preview}", use_container_width=True)
                    else:
                        st.write("Screenshot file not found.")

    st.divider()
    act1, act2, act3 = st.columns(3)
    with act1:
        if st.button("Issue Unique ID", key="mh_issue_id"):
            number, msg = issue_unique_id(selected_id)
            if number:
                try:
                    update_submission(
                        selected_id,
                        {"issued_id": number, "idIssueNote": msg},
                    )
                    st.success(f"Issued {number} ({msg})")
                    sub = get_submission(selected_id) or sub
                except Exception as exc:
                    st.error(str(exc))
            else:
                st.error(f"Could not issue ID: {msg}")
    with act2:
        issued_id = sub.get("issued_id")
        if st.button("Send Email", key="mh_send_email", disabled=not issued_id):
            result = send_unique_id_email(
                str(sub.get("email") or ""),
                str(issued_id),
                first_name=str(sub.get("firstName") or ""),
            )
            if result.get("ok"):
                try:
                    update_submission(
                        selected_id,
                        {"emailSent": True, "emailError": None},
                    )
                except Exception:
                    pass
                st.success("Email sent.")
            else:
                st.error(result.get("error") or "Email failed")
    with act3:
        if st.button("Refresh submission", key="mh_refresh_sub"):
            st.rerun()

    if runner.busy:
        time.sleep(1)
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="AutomationForge", page_icon="AF", layout="wide")
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    _init_session_state()

    dm = DataManager()
    llm = LLMAgent()

    st.title("AutomationForge v2")
    st.caption(
        "Local personal form assistant · Every SUBMIT needs your approval · "
        "Legitimate personal use only — you are responsible for ToS and laws."
    )

    with st.sidebar:
        page = st.radio(
            "Page",
            PAGES,
            index=PAGES.index(st.session_state.nav_page)
            if st.session_state.nav_page in PAGES
            else 0,
            key="nav_radio",
        )
        st.session_state.nav_page = page

    if page == "Local fill":
        render_local_fill(dm, llm)
    elif page == "Submissions":
        render_submissions()
    else:
        render_manual_handling()


if __name__ == "__main__":
    main()
