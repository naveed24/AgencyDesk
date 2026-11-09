@echo off
cd /d "%~dp0backend"
if not exist .venv\Scripts\python.exe (
  echo First run setup_windows.bat
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pytest -v
pause
