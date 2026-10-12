@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m eval.run_eval
if errorlevel 1 goto failed
echo Validation finished. To verify the browser UI, follow WINDOWS_START_HERE.md.
pause
exit /b 0
:missing
echo Run setup.bat first.
:failed
echo Validation stopped. Read the error above.
pause
exit /b 1
