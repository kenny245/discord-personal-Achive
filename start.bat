@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [DPA] Setting up Python environment...
  py -3 -m venv .venv
  if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
".venv\Scripts\python.exe" run.py
goto :end
:error
echo.
echo Setup failed. Check Python 3.11+ and your network connection.
pause
:end
endlocal
