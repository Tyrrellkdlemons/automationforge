# AutomationForge + PEEEZ intake — get in, work, serve

## Two sites (front / back)

| End | URL | Purpose |
|-----|-----|---------|
| **User intake** | https://peeezmachine-appflow.netlify.app | People enter details; confirmation email grants unique ID |
| **Command center** | https://automationforge-429d00fc.netlify.app | You receive inbox, build workflows, download/run locally |
| **Local GUI** | `.\serve.ps1` → http://localhost:8501 | Manual / follow-ups / worker companion |
| **GitHub** | https://github.com/tyrrellkdlemons/automationforge | Source of truth |

User invite link (token required):  
`https://peeezmachine-appflow.netlify.app/?token=YOUR_SUBMISSION_SECRET`

## Commands

```powershell
.\GET_IN.ps1
.\serve.ps1
.\work.ps1

# Deploy each Netlify site after changes:
npm run deploy:intake   # peeezmachine-appflow
npm run deploy:admin    # automationforge-429d00fc
```

## Pipeline

User intake → Firebase → worker issues unique ID + confirmation email → 3 flows → Follow-ups (24–48h)

Details: **CHECKPOINT.md** · **SETUP_NEW_FEATURE.md**
