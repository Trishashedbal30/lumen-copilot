@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set PYTHONUTF8=1
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
  py -3.12 bootstrap.py %*
  set "LUMEN_EXIT=!ERRORLEVEL!"
  goto finish
)
py -3.11 -c "import sys" >nul 2>&1
if not errorlevel 1 (
  py -3.11 bootstrap.py %*
  set "LUMEN_EXIT=!ERRORLEVEL!"
  goto finish
)
python -c "import sys" >nul 2>&1
if not errorlevel 1 (
  python bootstrap.py %*
  set "LUMEN_EXIT=!ERRORLEVEL!"
  goto finish
)
set "LUMEN_EXIT=1"
echo Python was not found. Install 64-bit Python 3.12, enable Add Python to PATH, then retry.
:finish
if not defined LUMEN_EXIT set "LUMEN_EXIT=1"
if not "%LUMEN_EXIT%"=="0" echo Setup failed. See the error above.
pause
exit /b %LUMEN_EXIT%
