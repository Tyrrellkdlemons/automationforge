#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host ""
Write-Host "=== AutomationForge - GET IN ===" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
  Write-Host "Creating Python venv..."
  python -m venv .venv
}
Write-Host "Installing Python packages..."
& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
try {
  & .\.venv\Scripts\python.exe -m playwright install chromium
} catch {
  Write-Host "Playwright browser install skipped or already done." -ForegroundColor DarkGray
}

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env from .env.example" -ForegroundColor Green
} else {
  Write-Host ".env already exists" -ForegroundColor DarkGray
}

if (Test-Path ".submission_secret.tmp") {
  $sec = (Get-Content ".submission_secret.tmp" -Raw).Trim()
  $lines = Get-Content ".env"
  $out = foreach ($line in $lines) {
    if ($line -match '^SUBMISSION_SECRET=') {
      "SUBMISSION_SECRET=$sec"
    } else {
      $line
    }
  }
  $out | Set-Content ".env"
  Write-Host "Synced SUBMISSION_SECRET into .env" -ForegroundColor Green
}

$keyOk = $false
if (Test-Path "firebase_key.json") {
  $raw = Get-Content "firebase_key.json" -Raw
  if ($raw -notmatch "REPLACE_ME" -and $raw -notmatch "_comment") {
    $keyOk = $true
  }
}
if (-not $keyOk) {
  Write-Host ""
  Write-Host "MISSING real firebase_key.json" -ForegroundColor Yellow
  Write-Host "  Open https://console.firebase.google.com/"
  Write-Host "  Project settings > Service accounts > Generate new private key"
  Write-Host "  Save as: $Root\firebase_key.json"
  Write-Host ""
} else {
  Write-Host "firebase_key.json found" -ForegroundColor Green
}

Write-Host ""
Write-Host "Health check..." -ForegroundColor Cyan
$env:PYTHONPATH = $Root
& .\.venv\Scripts\python.exe -c "from firebase_client import firestore_ready; from unique_id_generator import generate_candidate; ok, detail = firestore_ready(); print('Firebase:', 'OK' if ok else 'NOT READY - ' + detail); print('Sample unique ID:', generate_candidate())"

Write-Host ""
Write-Host "=== NEXT ===" -ForegroundColor Cyan
Write-Host "  WORK:  .\work.ps1"
Write-Host "  SERVE: .\serve.ps1"
Write-Host "  Form:  https://automationforge-429d00fc.netlify.app/submit"
Write-Host ""
