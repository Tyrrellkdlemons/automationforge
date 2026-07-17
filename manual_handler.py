"""
Manual flow runner for Streamlit — one flow at a time with live logs + screenshots.

Runs Playwright in a background thread; emits events onto a queue:
  {"type": "log", "level": "info|success|warn|error", "message": "..."}
  {"type": "screenshot", "path": "...", "label": "..."}
  {"type": "await_submit", "plan": {...}}
  {"type": "done", "result": {...}}
  {"type": "error", "message": "..."}
"""

from __future__ import annotations

import base64
import queue
import threading
import time
from pathlib import Path
from typing import Any

from signup_flows import (
    FlowDef,
    build_personal_from_submission,
    get_flows,
    run_single_flow,
)


class ManualFlowRunner:
    """Thread-friendly runner that mirrors worker logic with GUI-friendly events."""

    def __init__(self) -> None:
        self.events: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._approve_event = threading.Event()
        self._approve_result = False
        self._captcha_event = threading.Event()
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    def drain(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        while True:
            try:
                items.append(self.events.get_nowait())
            except queue.Empty:
                break
        return items

    def approve_submit(self, approved: bool = True) -> None:
        self._approve_result = approved
        self._approve_event.set()

    def captcha_continue(self) -> None:
        self._captcha_event.set()

    def _emit(self, payload: dict[str, Any]) -> None:
        self.events.put(payload)

    def _log(self, message: str, level: str = "info") -> None:
        self._emit({"type": "log", "level": level, "message": message})

    def start_flow(
        self,
        submission: dict[str, Any],
        flow_key: str,
        *,
        headed: bool = True,
    ) -> bool:
        if self._busy:
            return False
        flows = {f.key: f for f in get_flows()}
        flow = flows.get(flow_key)
        if not flow:
            self._log(f"Unknown flow: {flow_key}", "error")
            return False

        self._busy = True
        self._approve_event.clear()
        self._captcha_event.clear()
        self._approve_result = False

        personal = build_personal_from_submission(submission)

        def worker() -> None:
            try:
                def progress(msg: str) -> None:
                    level = "info"
                    if msg.startswith("✅") or "success" in msg.lower():
                        level = "success"
                    elif msg.startswith("❌") or "fail" in msg.lower():
                        level = "error"
                    elif msg.startswith("⚠️") or msg.startswith("⏸️") or "CAPTCHA" in msg:
                        level = "warn"
                    self._log(msg, level)

                def approve(plan: dict[str, Any]) -> bool:
                    self._emit({"type": "await_submit", "plan": plan, "flow": flow.key})
                    self._log("⏸️ Submit pending your approval in the dashboard.", "warn")
                    # Wait until Streamlit sets approve_submit()
                    while not self._approve_event.wait(timeout=0.5):
                        if not self._busy:
                            return False
                    self._approve_event.clear()
                    return bool(self._approve_result)

                def on_captcha() -> bool:
                    self._emit({"type": "await_captcha", "flow": flow.key})
                    self._log(
                        "⏸️ CAPTCHA DETECTED – solve it in the visible browser, then click Continue.",
                        "warn",
                    )
                    self._captcha_event.clear()
                    while not self._captcha_event.wait(timeout=0.5):
                        if not self._busy:
                            return False
                    return True

                result = run_single_flow(
                    flow,
                    personal,
                    headless=not headed,
                    approve_submit=approve,
                    on_captcha=on_captcha,
                    progress=progress,
                )
                # Attach latest screenshots as paths (not base64 in Firestore)
                for path in result.get("screenshots") or []:
                    self._emit(
                        {
                            "type": "screenshot",
                            "path": path,
                            "label": Path(path).name,
                            "preview_b64": _file_to_b64(path),
                        }
                    )
                self._emit({"type": "done", "result": result})
            except Exception as exc:
                self._emit({"type": "error", "message": str(exc)})
            finally:
                self._busy = False

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._busy = False
        self._approve_event.set()
        self._captcha_event.set()


def _file_to_b64(path: str | Path) -> str | None:
    try:
        data = Path(path).read_bytes()
        return base64.b64encode(data).decode("ascii")
    except Exception:
        return None


def flow_defs() -> list[FlowDef]:
    return get_flows()


def sleep_brief() -> None:
    time.sleep(0.05)
