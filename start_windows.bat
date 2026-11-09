@echo off
cd /d "%~dp0"
if not exist backend\.venv\Scripts\python.exe (
  echo Run setup_windows.bat first.
  pause
  exit /b 1
)
start "AgencyDesk API" /D "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
start "AgencyDesk React" /D "%~dp0frontend" cmd /k "npm run dev"
echo API: http://127.0.0.1:8000/docs
echo Frontend: http://127.0.0.1:5173
echo Keep the two newly opened terminal windows running.
pause
