$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) { python -m venv .venv }
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
npm ci --cache .npm-cache
if ($LASTEXITCODE -ne 0) { throw 'Official CamScanner CLI installation failed' }
Write-Host 'Run login-camscanner.cmd, then start.cmd'
