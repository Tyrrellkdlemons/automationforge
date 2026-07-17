# Setup: Public submissions + Firebase worker + Manual handling

This guide extends AutomationForge v2 with:

- Public Netlify form at `/submit`
- Firestore storage (`submissions`, `issued_numbers`)
- Local worker that runs **3 sign-up flows** per submission
- Unique ID generator (`8XX-XX-XXXX` / `9XX-XX-XXXX`) — **not real SSNs**
- SMTP email delivery of the unique ID
- Streamlit admin + **Manual handling** GUI

---

## 1. Firebase project

1. Go to [Firebase Console](https://console.firebase.google.com/) → **Add project**.
2. Build → **Firestore Database** → Create database (start in **production** mode, pick a region).
3. Project settings → **Service accounts** → **Generate new private key**.
4. Save the JSON as `firebase_key.json` in the project root (gitignored).
5. Copy `firebase_key.json.example` only as a template — never commit real keys.
6. Collections are created automatically on first write:
   - `submissions/{id}`
   - `issued_numbers/{number}` (document ID = the unique number)

Optional security: lock Firestore to service-account-only access (no public client SDK rules needed for this design).

---

## 2. Local Python env

```powershell
cd "C:\Users\TKDL\Desktop\_AI\Combined\______COMBINED AI______\Project App Workflow"
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
```

Edit `.env`:

| Variable | Purpose |
|----------|---------|
| `FIREBASE_SERVICE_ACCOUNT_PATH` | Path to `firebase_key.json` |
| `SUBMISSION_SECRET` | Shared secret for public form posts |
| `EMAIL_SENDER` / `EMAIL_PASSWORD` | Gmail address + **App Password** for SMTP |
| `FLOW_NEWSLETTER_URL` | Real newsletter form URL |
| `FLOW_SAAS_TRIAL_URL` | Real SaaS trial form URL |
| `FLOW_JOB_PROFILE_URL` | Real job-board profile URL |
| `WORKER_POLL_INTERVAL_SEC` | Default `30` |

Replace the three `FLOW_*_URL` placeholders before production. Defaults point at `example.com`.

---

## 3. Netlify env + deploy

In Netlify → Site settings → Environment variables, set:

| Key | Value |
|-----|--------|
| `SUBMISSION_SECRET` | Same long random string as local `.env` |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Entire service account JSON as **one line** |
| `AUTH_SECRET` | Already used for admin dashboard login |

Deploy:

```powershell
npm install
npm install --prefix netlify/functions/submit-submission
netlify deploy --prod
```

Public form:

- https://YOUR-SITE.netlify.app/submit  
- Or https://YOUR-SITE.netlify.app/submit.html  

Pass the secret via the form’s **Access token** field, or use a trusted link:

`https://YOUR-SITE.netlify.app/submit?token=YOUR_SUBMISSION_SECRET`

---

## 4. Run the worker (auto processing)

```powershell
python main.py --worker
# or
python worker.py
# single poll cycle:
python main.py --worker-once
```

Behavior:

1. Polls Firestore for `status == "new"` every 30s (configurable).
2. Skips `status == "manual"` / `manualOverride == true`.
3. Randomizes US address if empty (Faker).
4. Runs 3 flows (newsletter, SaaS trial, job profile) with **one retry** each.
5. **Every external submit still asks y/n** in the terminal.
6. On full success → unique ID → SMTP email → `status = completed`.

---

## 5. Streamlit admin + manual handling

```powershell
streamlit run streamlit_app.py
```

- **Submissions** — table, stats, Retry Auto, Take Over.
- **Manual handling** — visual log, screenshots, Approve Submit / CAPTCHA continue, Generate ID, Send Email.
- Headed browser toggle so you can solve CAPTCHAs in a visible window.

---

## 6. Test plan

### A. Form → Firestore
1. Open `/submit` on Netlify.
2. Fill name, email, DOB; leave address blank; enter `SUBMISSION_SECRET`.
3. Expect success + **submission ID**.
4. In Firebase Console, confirm a `submissions` doc with `status: new`.

### B. Unauthorized reject
1. Submit with wrong/missing secret → HTTP 401.

### C. Worker happy path (use editable test HTML pages if needed)
1. Point `FLOW_*_URL` at local/static test forms or authorized staging sites.
2. Run `python main.py --worker-once`.
3. Approve each submit when prompted.
4. Confirm `issued_id` written, `issued_numbers/{id}` exists, email arrives.

### D. Address randomization
1. Submit with empty address.
2. After processing, doc should show structured `address` + `addressRandomized: true`.

### E. Unique ID collision / format
1. Generated IDs match `^[89]\d{2}-\d{2}-\d{4}$`.
2. Re-issuing the same candidate fails claim (document already exists).

### F. Manual handling
1. In Streamlit Submissions → 🖐️ Take Over.
2. Start Newsletter flow; watch live log + screenshots.
3. Click Approve Submit; mark flow success.
4. Click Generate Now + Send Email.

### G. Worker vs manual race
1. Take Over a `new` submission.
2. Worker must skip it (`manual` / `manualOverride`).

---

## 7. File map

| Path | Role |
|------|------|
| `public/submit.html` → copied to `web/submit.html` | Public form |
| `netlify/functions/submit-submission/` | Firestore write API |
| `firebase_client.py` | Admin SDK helpers |
| `unique_id_generator.py` | Cryptographic unique IDs |
| `email_sender.py` | SMTP notifier |
| `address_utils.py` | Faker / fallback US addresses |
| `signup_flows.py` | 3 hardcoded flows (edit URLs) |
| `worker.py` | Polling engine |
| `manual_handler.py` | Threaded manual runner |
| `streamlit_app.py` | Local fill + admin + manual GUI |
| `main.py --worker` | Worker entry |

---

## 8. Safety

- Unique IDs are **opaque identifiers**, not Social Security Numbers.
- Do not bypass site CAPTCHAs or operator submit approval.
- Only process forms you are authorized to use; respect Terms of Service.
- Never commit `firebase_key.json`, `.env`, or real `SUBMISSION_SECRET`.
