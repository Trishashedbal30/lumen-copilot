@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
  echo First run setup.bat to install this project.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" doctor.py
if errorlevel 1 (
  echo Diagnostics failed. Run setup.bat and retain the error above.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py %*
set "LUMEN_EXIT=%ERRORLEVEL%"
if not "%LUMEN_EXIT%"=="0" echo Lumen stopped with error %LUMEN_EXIT%. See the error above.
pause
exit /b %LUMEN_EXIT%
