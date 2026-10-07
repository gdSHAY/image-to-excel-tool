@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "try { $s = Invoke-RestMethod 'http://127.0.0.1:8788/api/health' -TimeoutSec 3; if ($s.application -ne 'ScanTableStudio' -or -not $s.pid) { throw 'This port is not ScanTableStudio' }; Stop-Process -Id $s.pid -ErrorAction Stop; Write-Host 'ScanTableStudio stopped.' } catch { Write-Host $_.Exception.Message }"
pause
