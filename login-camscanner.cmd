@echo off
cd /d "%~dp0"
set "LOCALAPPDATA=%~dp0data\auth"
node_modules\@camscanner-cli\win32-x64\bin\camscanner-cli.exe auth login
node_modules\@camscanner-cli\win32-x64\bin\camscanner-cli.exe auth status
pause
