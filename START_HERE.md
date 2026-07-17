# AutomationForge — how to get in, work, and serve

## Access links (both ends)

| Who | Link |
|-----|------|
| **Public submit (user)** | https://automationforge-429d00fc.netlify.app/submit |
| **Admin web panel** | https://automationforge-429d00fc.netlify.app |
| **Local admin GUI** | http://localhost:8501 after `.\serve.ps1` |
| **GitHub** | https://github.com/Tyrrellkdlemons/automationforge |

Form access token = `SUBMISSION_SECRET` in `.env`  
Quick link: `https://automationforge-429d00fc.netlify.app/submit?token=YOUR_SECRET`

---

## Three commands

```powershell
.\GET_IN.ps1   # install + .env + health
.\serve.ps1    # Streamlit: Local fill · Submissions · Manual · Follow-ups
.\work.ps1     # Worker: ID + confirm email FIRST, then 3 flows (y/n submits)
```

---

## One-time Firebase (still required)

1. Finish Google login in the browser Cursor opened → **paste the auth code in chat**.
2. Create/select a Firebase project → enable Firestore.
3. Download service account → save as `firebase_key.json`.
4. Netlify env: `FIREBASE_SERVICE_ACCOUNT_JSON` = same JSON (one line).
5. Set `EMAIL_SENDER` + `EMAIL_PASSWORD` (Gmail app password) in `.env`.

Until step 3–4, the public form cannot write submissions.

---

## What happens on submit

1. User picks **state** (required); street/city/ZIP optional.
2. Worker issues unique ID `8XX-XX-XXXX` / `9XX-XX-XXXX`.
3. Confirmation email (name, address used, ID, 24–48h message) — **before** flows.
4. Optional SMS if `SEND_SMS=true`.
5. Three sign-up flows run (or take over in **Manual**).
6. Admin sends 24–48h follow-up from **Follow-ups** page.

---

## Paywall (off by default)

```
PAYWALL_ENABLED=false
PAYMENT_PROVIDER=stripe   # or: manual  (GoDaddy / invoice / other)
```

Flip to `true` on Netlify + add Stripe keys (or use `manual` + payment reference).

---

## Folder map (simplified)

| Path | Purpose |
|------|---------|
| `web/` | Netlify site (admin UI + `/submit`) |
| `public/submit.html` | Source form (copied to `web/` on deploy) |
| `netlify/functions/` | submit, paywall, stripe, auth |
| `worker.py` / `work.ps1` | Auto processing |
| `streamlit_app.py` / `serve.ps1` | Local command center |
| `START_HERE.md` | This file |
| `SETUP_NEW_FEATURE.md` | Full Firebase/Stripe detail |
