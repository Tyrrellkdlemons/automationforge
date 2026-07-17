"""
Optional Streamlit UI for AutomationForge v2.

Run:  streamlit run streamlit_app.py

Same safety rules as the CLI: every SUBMIT requires explicit approval.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from automationforge.browser_controller import BrowserController
from automationforge.data_manager import DataManager, normalize_url
from automationforge.llm_agent import LLMAgent

st.set_page_config(page_title="AutomationForge", page_icon="AF", layout="wide")

st.title("AutomationForge v2")
st.caption(
    "Local personal form assistant · Every SUBMIT needs your approval · "
    "Legitimate personal use only — you are responsible for ToS and laws."
)

dm = DataManager()
llm = LLMAgent()

with st.sidebar:
    st.header("Settings")
    profiles = dm.list_profiles()
    profile = st.selectbox(
        "Application profile",
        profiles,
        index=profiles.index("general") if "general" in profiles else 0,
    )
    force = st.checkbox("Force run (ignore duplicate URL)", value=False)
    merge_extracted = st.checkbox("Merge extracted data into personal_data.json", value=False)
    st.divider()
    if st.button("Refresh LLM health"):
        st.session_state["health"] = llm.healthcheck()
    health = st.session_state.get("health") or llm.healthcheck()
    st.json(health)
    st.divider()
    st.markdown("Edit `personal_data.json` or use the Netlify dashboard forms.")

url_block = st.text_area(
    "Application URL(s) — one per line, max 5",
    placeholder="https://example.com/apply\nhttps://another.com/form",
    height=110,
)
extra = st.text_area("Extra instructions (optional)", height=80)
approve_submit = st.checkbox(
    "I approve SUBMIT if a submit button is found (required to actually submit)",
    value=False,
)
all_urls = [u.strip() for u in (url_block or "").splitlines() if u.strip()]
urls = all_urls[:5]
run = st.button("Run fill pipeline", type="primary", disabled=not urls)
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

        def log(msg: str, _lines=lines, _box=log_box) -> None:
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
