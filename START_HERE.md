# PEEEZMachine AppFlow — get in, work, serve

## Links

| End | URL |
|-----|-----|
| **User form** | https://peeezmachine-appflow.netlify.app/submit |
| **Admin web** | https://peeezmachine-appflow.netlify.app |
| **Local GUI** | `.\serve.ps1` → http://localhost:8501 |
| **GitHub** | https://github.com/Tyrrellkdlemons/peeezmachine-appflow |

Token link: see **ACCESS.txt** (`SUBMISSION_SECRET`)

## Commands

```powershell
.\GET_IN.ps1   # install + .env + health
.\serve.ps1    # Streamlit: Local fill · Submissions · Manual · Follow-ups
.\work.ps1     # Worker: ID + confirm email FIRST, then 3 flows (y/n submits)
```

## Pipeline

Public submit → unique ID + confirmation email → 3 sign-up flows → Follow-ups (24–48h)

Details: **CHECKPOINT.md** · **SETUP_NEW_FEATURE.md**
