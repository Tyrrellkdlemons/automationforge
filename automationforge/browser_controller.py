"""Playwright browser control with stealth, human-like fills, retries & screenshots."""

from __future__ import annotations

import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from automationforge import config

try:
    # playwright-stealth >= 2.0
    from playwright_stealth import Stealth

    def stealth_sync(page: Page) -> None:
        Stealth().apply_stealth_sync(page)

    HAS_STEALTH = True
except ImportError:  # pragma: no cover
    try:
        # playwright-stealth 1.x
        from playwright_stealth import stealth_sync as _stealth_sync

        def stealth_sync(page: Page) -> None:
            _stealth_sync(page)

        HAS_STEALTH = True
    except ImportError:
        HAS_STEALTH = False

        def stealth_sync(page: Page) -> None:
            return None


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _human_pause(min_ms: int | None = None, max_ms: int | None = None) -> None:
    lo = min_ms if min_ms is not None else config.ACTION_PAUSE_MS_MIN
    hi = max_ms if max_ms is not None else config.ACTION_PAUSE_MS_MAX
    if hi < lo:
        hi = lo
    time.sleep(random.uniform(lo, hi) / 1000.0)


class BrowserController:
    """
    Stealth Playwright session for form automation.

    Delays mimic natural user pacing for reliability/UX on ordinary forms —
    not intended to evade security systems. CAPTCHAs always pause for the user.
    """

    def __init__(
        self,
        *,
        headless: bool | None = None,
        screenshots_dir: Path | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.headless = config.HEADLESS if headless is None else headless
        self.screenshots_dir = Path(screenshots_dir or config.SCREENSHOTS_DIR)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.max_retries = max_retries if max_retries is not None else config.MAX_RETRIES

        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None
        self.screenshot_paths: list[str] = []

    # ── lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> Page:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-default-browser-check",
            ],
        )
        self._context = self._browser.new_context(
            viewport={"width": 1365, "height": 900},
            locale="en-US",
            timezone_id="America/Chicago",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        self._context.set_default_timeout(config.BROWSER_TIMEOUT_MS)
        self.page = self._context.new_page()
        if HAS_STEALTH:
            stealth_sync(self.page)
        return self.page

    def close(self) -> None:
        try:
            if self._context:
                self._context.close()
        finally:
            try:
                if self._browser:
                    self._browser.close()
            finally:
                if self._pw:
                    self._pw.stop()
        self.page = None
        self._context = None
        self._browser = None
        self._pw = None

    def __enter__(self) -> "BrowserController":
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ── navigation & snapshots ─────────────────────────────────────────────

    def goto(self, url: str) -> None:
        assert self.page is not None
        self.page.goto(url, wait_until="domcontentloaded")
        try:
            self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        _human_pause(400, 1000)

    def accessibility_snapshot(self, interesting_only: bool = True) -> str:
        """Return a text accessibility tree — preferred input for the LLM.

        Uses Playwright's modern ``locator.aria_snapshot()`` when available,
        with legacy ``page.accessibility.snapshot()`` and a DOM summary fallback.
        """
        assert self.page is not None
        _ = interesting_only  # retained for API compatibility with older callers

        # Playwright 1.49+: aria snapshot (YAML-like tree) — best for LLMs
        try:
            aria = self.page.locator("body").aria_snapshot()
            if aria and str(aria).strip():
                return str(aria)
        except Exception:
            pass

        # Legacy CDP accessibility tree (removed in newer Playwright builds)
        try:
            ax = getattr(self.page, "accessibility", None)
            if ax is not None:
                snap = ax.snapshot(interesting_only=interesting_only)
                if snap:
                    return self._format_ax_node(snap)
        except Exception:
            pass

        return self._fallback_dom_summary()

    def _format_ax_node(self, node: dict[str, Any], depth: int = 0) -> str:
        indent = "  " * depth
        role = node.get("role") or ""
        name = node.get("name") or ""
        value = node.get("value")
        checked = node.get("checked")
        disabled = node.get("disabled")
        parts = [f"{indent}[{role}]"]
        if name:
            parts.append(f' name="{name}"')
        if value is not None:
            parts.append(f' value="{value}"')
        if checked is not None:
            parts.append(f" checked={checked}")
        if disabled:
            parts.append(" disabled")
        # Include useful HTML hints when present
        for key in ("description", "keyshortcuts", "roledescription"):
            if node.get(key):
                parts.append(f' {key}="{node[key]}"')
        lines = ["".join(parts)]
        for child in node.get("children") or []:
            lines.append(self._format_ax_node(child, depth + 1))
        return "\n".join(lines)

    def _fallback_dom_summary(self) -> str:
        assert self.page is not None
        script = """
        () => {
          const els = Array.from(document.querySelectorAll(
            'input, textarea, select, button, [role="button"], a[href]'
          )).slice(0, 200);
          return els.map(el => {
            const tag = el.tagName.toLowerCase();
            const type = el.getAttribute('type') || '';
            const name = el.getAttribute('name') || '';
            const id = el.id || '';
            const label = (el.labels && el.labels[0]) ? el.labels[0].innerText.trim() : '';
            const aria = el.getAttribute('aria-label') || '';
            const ph = el.getAttribute('placeholder') || '';
            const text = (el.innerText || el.value || '').trim().slice(0, 80);
            return {tag, type, name, id, label, aria, placeholder: ph, text};
          });
        }
        """
        try:
            rows = self.page.evaluate(script)
        except Exception as exc:
            return f"(dom summary failed: {exc})"
        lines = []
        for r in rows:
            lines.append(
                f"[{r.get('tag')}/{r.get('type')}] id={r.get('id')!r} name={r.get('name')!r} "
                f"label={r.get('label')!r} aria={r.get('aria')!r} placeholder={r.get('placeholder')!r} "
                f"text={r.get('text')!r}"
            )
        return "\n".join(lines)

    def page_text(self, limit: int = 12000) -> str:
        assert self.page is not None
        try:
            text = self.page.inner_text("body")
        except Exception:
            text = self.page.content()
        return (text or "")[:limit]

    def screenshot(self, label: str = "shot") -> Path:
        assert self.page is not None
        safe = re.sub(r"[^\w\-]+", "_", label)[:60]
        path = self.screenshots_dir / f"{_utc_stamp()}_{safe}.png"
        self.page.screenshot(path=str(path), full_page=True)
        self.screenshot_paths.append(str(path))
        return path

    # ── fill plan execution ────────────────────────────────────────────────

    def execute_fill_plan(
        self,
        plan: dict[str, Any],
        *,
        on_captcha: Callable[[], bool] | None = None,
        on_sensitive: Callable[[dict[str, Any]], bool] | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """
        Apply fill actions from an LLM plan. Does NOT click submit.
        Returns summary of filled/skipped/failed fields.
        """
        assert self.page is not None
        log = lambda m: progress(m) if progress else None  # noqa: E731

        if plan.get("captcha_detected"):
            log("CAPTCHA detected — pausing for human intervention.")
            self.screenshot("captcha_detected")
            ok = True
            if on_captcha:
                ok = on_captcha()
            if not ok:
                return {
                    "ok": False,
                    "cancelled": True,
                    "fields_filled": [],
                    "errors": ["User cancelled at CAPTCHA"],
                }

        fields_filled: list[dict[str, Any]] = []
        errors: list[str] = []

        for field in plan.get("fields") or []:
            action = (field.get("action") or "fill").lower()
            if action == "skip":
                fields_filled.append({**field, "status": "skipped"})
                continue
            if field.get("sensitive") and on_sensitive:
                if not on_sensitive(field):
                    fields_filled.append({**field, "status": "skipped_sensitive"})
                    continue

            try:
                self._run_with_retries(lambda f=field: self._apply_field(f), label=field.get("label") or field.get("name") or "field")
                fields_filled.append({**field, "status": "filled"})
                log(f"Filled: {field.get('label') or field.get('name') or field.get('selector')}")
            except Exception as exc:  # noqa: BLE001
                err = f"{field.get('label') or field.get('selector')}: {exc}"
                errors.append(err)
                fields_filled.append({**field, "status": "error", "error": str(exc)})
                self.screenshot(f"field_error_{field.get('name') or 'unknown'}")
                log(f"Error: {err}")

        return {"ok": len(errors) == 0, "fields_filled": fields_filled, "errors": errors}

    def click_submit(self, plan: dict[str, Any]) -> None:
        """Click the submit control from the plan. Caller must have user approval."""
        assert self.page is not None
        submit = plan.get("submit") or {}
        locator = self._resolve_locator(
            selector=submit.get("selector"),
            role="button",
            name=submit.get("label") or submit.get("name"),
            label=submit.get("label"),
        )
        if locator is None:
            # Last resort common selectors
            for sel in [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Submit")',
                'button:has-text("Apply")',
                'button:has-text("Continue")',
                'button:has-text("Next")',
            ]:
                loc = self.page.locator(sel).first
                if loc.count() > 0:
                    locator = loc
                    break
        if locator is None:
            raise RuntimeError("Could not locate submit button — click it manually, then continue.")
        locator.scroll_into_view_if_needed()
        _human_pause()
        locator.click()
        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        _human_pause(500, 1200)

    def _apply_field(self, field: dict[str, Any]) -> None:
        assert self.page is not None
        action = (field.get("action") or "fill").lower()
        value = "" if field.get("value") is None else str(field.get("value"))
        locator = self._resolve_locator(
            selector=field.get("selector"),
            role=field.get("role"),
            name=field.get("name"),
            label=field.get("label"),
        )
        if locator is None:
            raise RuntimeError("Could not resolve locator for field")

        locator.scroll_into_view_if_needed()
        _human_pause()

        if action == "fill":
            try:
                locator.click(timeout=3000)
            except Exception:
                pass
            try:
                locator.fill("")
            except Exception:
                pass
            # Human-like typing for reliability on controlled inputs
            delay = random.randint(config.TYPING_DELAY_MS_MIN, config.TYPING_DELAY_MS_MAX)
            try:
                locator.type(value, delay=delay)
            except Exception:
                locator.fill(value)
        elif action == "select":
            try:
                locator.select_option(label=value)
            except Exception:
                try:
                    locator.select_option(value=value)
                except Exception:
                    locator.click()
                    self.page.get_by_role("option", name=value).click()
        elif action == "check":
            locator.check()
        elif action == "uncheck":
            locator.uncheck()
        elif action == "click":
            locator.click()
        else:
            raise RuntimeError(f"Unknown action: {action}")

        _human_pause()

    def _resolve_locator(
        self,
        *,
        selector: str | None = None,
        role: str | None = None,
        name: str | None = None,
        label: str | None = None,
    ) -> Any:
        assert self.page is not None
        page = self.page

        if selector:
            loc = page.locator(selector)
            if loc.count() > 0:
                return loc.first

        # Prefer accessible name / label
        for candidate_name in (label, name):
            if not candidate_name:
                continue
            try:
                loc = page.get_by_label(candidate_name, exact=False)
                if loc.count() > 0:
                    return loc.first
            except Exception:
                pass
            if role:
                try:
                    loc = page.get_by_role(role, name=re.compile(re.escape(candidate_name), re.I))
                    if loc.count() > 0:
                        return loc.first
                except Exception:
                    pass
            try:
                loc = page.get_by_placeholder(candidate_name, exact=False)
                if loc.count() > 0:
                    return loc.first
            except Exception:
                pass

        if name:
            loc = page.locator(f'[name="{name}"]')
            if loc.count() > 0:
                return loc.first

        return None

    def _run_with_retries(self, fn: Callable[[], None], label: str = "action") -> None:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                fn()
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                self.screenshot(f"retry_{attempt}_{label}")
                _human_pause(300, 900)
        assert last_exc is not None
        raise last_exc

    def wait_for_user_continue(self, message: str = "Press Enter in the terminal when ready...") -> None:
        """Used when the browser is visible and the user must solve CAPTCHA etc."""
        # Actual input is handled by CLI; this is a no-op hook for Streamlit/custom UIs.
        _ = message
