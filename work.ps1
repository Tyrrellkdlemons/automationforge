#Requires -Version 5.1
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
Write-Host "Starting Firestore worker (polls new submissions every 30s)..." -ForegroundColor Cyan
Write-Host "You will be asked y/n before every external site SUBMIT." -ForegroundColor Yellow
& .\.venv\Scripts\python.exe main.py --worker
