#Requires -Version 5.1
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
Write-Host "Starting Streamlit admin (Local fill · Submissions · Manual handling)..." -ForegroundColor Cyan
Write-Host "Open http://localhost:8501 when ready." -ForegroundColor Green
& .\.venv\Scripts\streamlit.exe run streamlit_app.py --server.headless true
