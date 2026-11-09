@echo off
setlocal
cd /d "%~dp0"
echo === AgencyDesk first-run installer ===
python --version || (echo Python not found & exit /b 1)
node --version || (echo Node not found & exit /b 1)
cd backend
if not exist .env python configure.py
if errorlevel 1 exit /b 1
if not exist .venv python -m venv .venv
if errorlevel 1 exit /b 1
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
python init_db.py
if errorlevel 1 exit /b 1
python migrate.py
if errorlevel 1 exit /b 1
echo.
echo Seeding a fresh local demo with the password saved in backend\.env.
python seed_demo.py
if errorlevel 1 exit /b 1
cd ..\frontend
call npm install
if errorlevel 1 exit /b 1
cd ..
echo.
echo Setup complete! Double-click start_windows.bat or run it from this folder.
endlocal
