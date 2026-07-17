# AutomationForge v2 — full feature setup (Firebase, worker, manual GUI, follow-ups, paywall)

See **START_HERE.md** for the short daily loop. This file is the detailed checklist.

## Features overview

1. Public form `/submit` — state required; address optional → state-based generation  
2. Worker issues unique ID + confirmation email **before** flows  
3. Optional Twilio SMS (`SEND_SMS`)  
4. Manual handling GUI in Streamlit  
5. Follow-up Command Center (24–48h)  
6. Paywall ready (`PAYWALL_ENABLED`) — Stripe or `PAYMENT_PROVIDER=manual` (GoDaddy/etc.)

## Firebase

1. Login (paste auth code into Cursor when prompted).  
2. Create/select project → Firestore.  
3. Service account → `firebase_key.json` locally.  
4. Netlify: `FIREBASE_SERVICE_ACCOUNT_JSON`, `SUBMISSION_SECRET`.  
5. Deploy rules: `npx -y firebase-tools@latest deploy --only firestore:rules`

Rules deny all client access (Admin SDK only) — see `firestore.rules`.

## Local

```powershell
.\GET_IN.ps1
.\serve.ps1
.\work.ps1
```

## Paywall

| Env | Meaning |
|-----|---------|
| `PAYWALL_ENABLED=false` | No payment (default) |
| `PAYMENT_PROVIDER=stripe` | Stripe Elements on form |
| `PAYMENT_PROVIDER=manual` | User enters GoDaddy/invoice ref |
| `STRIPE_*` | Keys + webhook secret |

Webhook URL: `https://YOUR-SITE.netlify.app/api/stripe-webhook`

## Manual handling

Streamlit → Manual handling → Take Over → Start flow → Approve Submit → Issue ID / Send Email.

## Test plan

1. Open `/submit?token=SECRET` — select state, leave street blank → submit.  
2. Without Firebase JSON on Netlify → expect 500 (expected until configured).  
3. With Firebase + worker: confirm email arrives with ID + address before flows finish.  
4. Streamlit Follow-ups: send 24–48h email; mark sent.  
5. Manual: Take Over, headed browser, approve submit.  
6. Paywall off: form works. Paywall on + Stripe test keys: card required.

## Access links

- User: https://peeezmachine-appflow.netlify.app/submit  
- Admin web: https://peeezmachine-appflow.netlify.app  
- Alias: https://automationforge-429d00fc.netlify.app  
- Local GUI: http://localhost:8501  

