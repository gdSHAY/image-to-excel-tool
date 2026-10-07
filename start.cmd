@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "try { $s = Invoke-RestMethod 'http://127.0.0.1:8788/api/health' -TimeoutSec 2; if ($s.application -eq 'ScanTableStudio') { exit 0 } } catch {}; exit 1"
if not errorlevel 1 (
  start "" http://127.0.0.1:8788
  exit /b 0
)
if not exist .venv\Scripts\python.exe (
  echo Please run setup.ps1 first.
  pause
  exit /b 1
)
start "" http://127.0.0.1:8788
.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8788
pause
