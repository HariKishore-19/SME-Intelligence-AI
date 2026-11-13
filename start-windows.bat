@echo off
cd /d "%~dp0backend"
where py >nul 2>nul
if errorlevel 1 (set "PYTHON_CMD=python") else (set "PYTHON_CMD=py")
if not exist .venv (%PYTHON_CMD% -m venv .venv)
if errorlevel 1 goto fail
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo Open http://localhost:8000 in your browser.
python -m uvicorn main:app --host 127.0.0.1 --port 8000
pause
exit /b
:fail
echo Setup failed. Install Python 3.12 or newer and try again.
pause
