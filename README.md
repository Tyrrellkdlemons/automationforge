# AutomationForge v2

Local-first Python agent for **legitimate personal** web form automation.

Paste a URL → stealth Playwright captures an accessibility snapshot → an LLM (Ollama preferred) builds a structured fill plan → fields are filled with human-like pacing → **you must approve every SUBMIT (y/n)** → confirmations are extracted and logged to `application_log.json` plus a human-readable `.txt` under `logs/`.

---

## Safety & legal (read this)

- **Every form SUBMIT requires explicit user approval.** Nothing is submitted without your `y` / checkbox.
- **No CAPTCHA bypass.** If a CAPTCHA or bot check appears, AutomationForge pauses and asks you to solve it.
- **Legitimate personal use only.** You are solely responsible for complying with each site’s Terms of Service and applicable laws.
- Do **not** use this for credential stuffing, spam, fraud, bulk account abuse, or evading security controls.
- Typing delays exist for **UX and reliability** on ordinary forms (fewer flaky inputs), not as a primary purpose of bypassing security systems.
- Treat `personal_data.json` as sensitive. Do not commit real PII to public repos.

---

## Architecture

```
┌─────────────┐   URL + profile    ┌──────────────────┐
│  main.py /  │ ─────────────────► │  DataManager     │  personal_data.json
│ streamlit   │                    │  (profiles, log, │  application_log.json
└──────┬──────┘                    │   txt export)    │  logs/*.txt
       │                           └────────▲─────────┘
       │ accessibility snapshot             │ append / merge
       ▼                                    │
┌──────────────────┐   fill plan JSON  ┌────┴───────────┐
│ BrowserController│ ◄──────────────── │   LLMAgent     │
│ Playwright +     │                   │ Ollama → OpenAI│
│ playwright-stealth│                  │ → Anthropic    │
└────────┬─────────┘                   └────────────────┘
         │ optional
         ▼
┌──────────────────┐
│  EmailService    │  Tigrmail / Gmail IMAP / manual
└──────────────────┘
```

**Flow per URL**

1. Optional email step (temp inbox or IMAP verification).
2. Choose an application **profile** (`job_application`, `housing`, …).
3. Skip if normalized URL already exists in `application_log.json` (unless forced).
4. Open page → accessibility snapshot → LLM fill plan.
5. Fill fields (3 retries + screenshots on failure). Pause on CAPTCHA / sensitive fields.
6. **Ask y/n before submit.**
7. Extract confirmation → log JSON + TXT → optional merge into `personal_data.json`.

---

## Requirements

- Python **3.10+** (tested intent: 3.10–3.13)
- [Playwright](https://playwright.dev/python/) browsers
- Optional: [Ollama](https://ollama.com/) with a local model (recommended)
- Optional: OpenAI-compatible or Anthropic API keys as fallback

---

## Exact setup

```powershell
cd "C:\Users\TKDL\Desktop\_AI\Combined\______COMBINED AI______\Project App Workflow"

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
playwright install chromium

copy .env.example .env
# Edit .env — at minimum leave AF_LLM_PROVIDER=auto and start Ollama,
# or set OPENAI_API_KEY / ANTHROPIC_API_KEY.

# Edit personal_data.json with YOUR real defaults and profile overrides.
```

### Ollama (preferred)

```powershell
ollama pull llama3.2
ollama serve
```

Confirm the health table in the CLI shows Ollama `ok`.

### API fallback

Set in `.env`:

- `OPENAI_API_KEY` (+ optional `OPENAI_BASE_URL` for compatible proxies)
- and/or `ANTHROPIC_API_KEY`

With `AF_LLM_PROVIDER=auto`, AutomationForge tries **Ollama → OpenAI → Anthropic**.

---

## Run commands

**CLI (primary)**

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

Then:

1. Optionally run the email verification step.
2. Pick a profile (general / job_application / housing / registration).
3. Paste any application URL.
4. Review the fill plan; approve CAPTCHA / sensitive fields if asked.
5. Type **y** only if you want to SUBMIT.

Loop commands inside the CLI: `q` quit · `p` change profile · `e` email step · `h` LLM health.

**Streamlit UI (optional)**

```powershell
streamlit run streamlit_app.py
```

Check **“I approve SUBMIT…”** only when you intend to submit.

---

## Prefill profiles (`personal_data.json`)

```json
{
  "defaults": { "first_name": "...", "email": "...", "address": { } },
  "profiles": {
    "job_application": { "description": "...", "overrides": { "desired_salary": "85000" } },
    "housing": { "overrides": { "monthly_income": "6000" } },
    "general": { "overrides": {} }
  },
  "custom_fields": { "emergency_contact_name": "" }
}
```

- **defaults** — shared identity fields for all forms.
- **profiles.\*.overrides** — per application-type prefills (job vs housing vs registration).
- **custom_fields** — anything else you want the LLM to map by label.

The CLI/UI merges `defaults + custom_fields + profile.overrides` before analysis. Add new profiles anytime; they appear in the picker automatically.

---

## Outputs

| Artifact | Purpose |
|----------|---------|
| `application_log.json` | Structured run history; duplicate detection by normalized URL |
| `logs/*.txt` | Human-readable per-run summary (URL, status, fields, extracted info) |
| `screenshots/*.png` | Page load, retries, CAPTCHA, pre/post submit failures |

---

## Email verification

| Provider | Env | Notes |
|----------|-----|-------|
| **Tigrmail** | `TIGRMAIL_API_KEY` | Temp inbox example; adjust endpoints in `email_service.py` if your API docs differ |
| **Gmail IMAP** | `GMAIL_IMAP_USER`, `GMAIL_IMAP_PASSWORD` (App Password) | Reads your real inbox for codes/links |
| **Manual** | none | You paste the address/code yourself |

### Extending email APIs

1. Subclass `BaseEmailService` in `automationforge/email_service.py`.
2. Implement `create_address()` and `list_messages()`.
3. Register in `get_email_service()`.

Comments in that file show where to plug Mail.tm / Guerrilla / custom SMTP-style providers.

---

## Extending LLM / form logic

- **Schema**: `FILL_PLAN_SCHEMA` in `llm_agent.py` — keep JSON structured.
- **Prompts**: `SYSTEM_PROMPT` — tighten mapping rules for your domain.
- **Provider**: set `AF_LLM_PROVIDER` to `ollama`, `openai`, or `anthropic`.
- **Selectors**: `browser_controller._resolve_locator` — add site-specific heuristics if needed.
- **Retries**: `AF_MAX_RETRIES` (default 3) + automatic screenshots on failure.

Complex / multi-step wizards: the agent marks `complex_form=true`, fills only clear fields, and leaves the rest for you.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| All LLM providers failed | Start Ollama (`ollama serve`) or set an API key; check `AF_LLM_PROVIDER` |
| Ollama empty / bad JSON | Try a stronger model (`llama3.1:8b`, `qwen2.5`, etc.); keep `format=json` |
| Playwright not installed | `playwright install chromium` |
| Fields not found | Re-run with extra instructions (“use name=email”); inspect accessibility snapshot quality |
| Duplicate skipped | Confirm force, or delete the entry from `application_log.json` |
| Tigrmail 404 | Update paths in `TigrmailService` to match your account’s API docs |
| Gmail IMAP auth error | Use a Google **App Password**, not your normal password |
| Stealth import warning | Ensure `playwright-stealth` is installed; controller still runs without it |

---

## Module map

| File | Role |
|------|------|
| `main.py` | Rich CLI orchestration loop |
| `streamlit_app.py` | Optional simple UI |
| `automationforge/data_manager.py` | personal data, logs, duplicates, merge, txt export |
| `automationforge/browser_controller.py` | Playwright + stealth, snapshot, fill, screenshots, retries |
| `automationforge/llm_agent.py` | Ollama / OpenAI / Anthropic → fill plan + confirmation extract |
| `automationforge/email_service.py` | Tigrmail, Gmail IMAP, manual hooks |
| `automationforge/config.py` | Env-driven settings |
| `personal_data.json` | Editable defaults + profiles |
| `requirements.txt` / `.env.example` | Install & config templates |

---

## Hosted dashboard (GitHub + Netlify)

The **web control panel** at `web/` deploys to Netlify with login:

- Default credentials: **`admin` / `admin`**
- **Password change is required on first login** (cannot use the dashboard until you set a new password ≥ 8 chars)

Browser automation (Playwright) still runs **locally** — Netlify hosts auth + profile/log helpers only.

```powershell
npm install
netlify deploy --prod
```

Set site env `AUTH_SECRET` to a long random string (Netlify UI → Site settings → Environment variables).

---

## Disclaimer

AutomationForge is a **personal productivity tool**. Misuse against third-party services may violate law or Terms of Service. The authors and distributors assume no liability for your use. Always review filled data and **approve submits consciously**.
