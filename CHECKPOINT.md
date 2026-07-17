# Dual-site workflow checkpoint

**Saved:** 2026-07-17  
**Firebase:** `automationforge-app`

## Site split

| Role | Netlify project | URL |
|------|-----------------|-----|
| **Command center (you)** | `automationforge-429d00fc` | https://automationforge-429d00fc.netlify.app |
| **User intake** | `peeezmachine-appflow` | https://peeezmachine-appflow.netlify.app |

Invite users with: `https://peeezmachine-appflow.netlify.app/?token=YOUR_SUBMISSION_SECRET`

## Pipeline (unchanged)

```
User intake site (/)
  → Firestore submissions (status=new)
  → Worker .\work.ps1
      1) Resolve state address + randomized fields
      2) Issue unique ID 8XX/9XX-XX-XXXX
      3) Confirmation email (before site fills)
      4) Three flows: newsletter · saas_trial · job_profile
      5) status=completed | failed
  → Streamlit Follow-ups (24–48h)  OR  Command Center inbox
  → Optional Manual takeover anytime
```

## Deploy

```powershell
npm run deploy:admin    # AutomationForge command center
npm run deploy:intake   # PEEEZ user form
```

Both sites share `netlify/functions`. Set env on **each** Netlify project:
- Intake: `SUBMISSION_SECRET`, `FIREBASE_SERVICE_ACCOUNT_JSON`, paywall/Stripe optional
- Admin: `AUTH_SECRET`, `FIREBASE_SERVICE_ACCOUNT_JSON` (inbox)

## Do not break

- Operator y/n (or Streamlit Approve) before site submit
- Skip `status=manual`
- Paywall off by default (`PAYWALL_ENABLED=false`)
- Keep internals off the public intake page
