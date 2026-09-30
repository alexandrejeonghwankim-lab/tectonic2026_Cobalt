@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv-win\Scripts\python.exe" (
    echo Creating a Python virtual environment...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv .venv-win
    ) else (
        python -m venv .venv-win
    )
    if errorlevel 1 goto :failed
)

".venv-win\Scripts\python.exe" -c "import reflex" >nul 2>nul
if errorlevel 1 (
    echo Installing project requirements. This may take a few minutes on first run...
    ".venv-win\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :failed
)

if not exist "data\customer_signals.csv" goto :generate
if not exist "data\customers.csv" goto :generate
if not exist "data\accounts.csv" goto :generate
if not exist "data\insurance_claims.csv" goto :generate
goto :launch
:generate
echo Generating synthetic data...
".venv-win\Scripts\python.exe" generate_data.py
if errorlevel 1 goto :failed

:launch
echo Opening the local address shown below ^(usually http://localhost:3000^). No login is required.
echo Press Ctrl+C to stop.
".venv-win\Scripts\python.exe" -m reflex run %*
if errorlevel 1 goto :failed
exit /b 0

:failed
echo Could not start the demo. Check that Python 3.12 and Node.js are installed and available in PATH.
pause
exit /b 1
