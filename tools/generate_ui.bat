@echo off
setlocal
cd /d "%~dp0"
rem the game: first argument (dq4, dq5 or dq6), otherwise DQ_GAME, otherwise dq4
set "ARG_GAME="
for %%G in (dq4 dq5 dq6) do if /i "%~1"=="%%G" set "ARG_GAME=%%G"
if defined ARG_GAME set "DQ_GAME=%ARG_GAME%"
if defined ARG_GAME shift
if not defined DQ_GAME set "DQ_GAME=dq4"
title Original layout of the menu windows
echo.
echo  Reading the EXACT layout of the game's menu windows
echo  -------------------------------------------------------------
echo  Runs the game's original code (Make_*) under emulation and writes
echo  ..\data\cache\%DQ_GAME%\fr\ui_layout.json  (stays on your PC, not sent to GitHub).
echo  Prerequisite: tools\dump_il2cpp.bat %DQ_GAME% already run. A few minutes, one time only.
echo.
if not exist "..\.venv\Scripts\python.exe" (
  echo  First run launch_dq4.bat ^(at the project root^) once to create the Python environment.
  pause
  exit /b 1
)
"..\.venv\Scripts\python.exe" -c "import unicorn" >nul 2>nul
if errorlevel 1 "..\.venv\Scripts\python.exe" -m pip install --quiet unicorn
"..\.venv\Scripts\python.exe" ui_il2cpp\generate_ui.py %1
echo.
pause
