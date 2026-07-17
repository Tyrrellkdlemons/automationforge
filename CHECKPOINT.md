# PeeezMachine — workflow checkpoint

**Saved:** 2026-07-17  
**Brand:** PeeezMachine (engine modules may still say AutomationForge internally)  
**Firebase:** `automationforge-app`

## Checkpointed pipeline

```
User /submit
  → Firestore submissions (status=new)
  → Worker .\work.ps1
      1) Resolve state address + randomized fields
      2) Issue unique ID 8XX/9XX-XX-XXXX
      3) Confirmation email (before site fills)
      4) Three flows: newsletter · saas_trial · job_profile
      5) status=completed | failed
  → Streamlit Follow-ups (24–48h)
  → Optional Manual takeover anytime
```

## Both ends

| End | URL / command |
|-----|----------------|
| Public | https://automationforge-429d00fc.netlify.app/submit |
| Admin web | https://automationforge-429d00fc.netlify.app |
| Local GUI | `.\serve.ps1` → http://localhost:8501 |
| Worker | `.\work.ps1` |

Full access notes: **ACCESS.txt**

## UI theme

Ink / gold PeeezMachine theme on Netlify admin + public form (gear mark + Roboto Condensed / IBM Plex).
Streamlit titled PeeezMachine with matching gold accents.

## Do not break

- Operator y/n (or Streamlit Approve) before site submit
- Skip `status=manual`
- Paywall off by default (`PAYWALL_ENABLED=false`)
