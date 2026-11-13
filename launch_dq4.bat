@echo off
setlocal
cd /d "%~dp0"

call :m_title
call :m_intro

rem --- 1. Python: prefer a stable version that has precompiled packages
set "PY="
for %%V in (3.13 3.12 3.14) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys" >nul 2>nul && set "PY=python"
)
if not defined PY (
  call :m_python_missing
  pause
  exit /b 1
)

rem --- 1b. a ".venv" copied from another PC does not work (it points to the other machine's Python): it is rebuilt
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
  if errorlevel 1 (
    call :m_venv_other_pc
    rd /s /q ".venv"
  )
)

rem --- 2. isolated environment + modules (once only)
if not exist ".venv\Scripts\python.exe" (
  call :m_venv_creating
  %PY% -m venv .venv
  if errorlevel 1 ( call :m_venv_failed & pause & exit /b 1 )
)
if not exist ".venv\modules_ok.txt" (
  call :m_install
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "requirements.txt"
  if errorlevel 1 (
    call :m_install_failed
    pause
    exit /b 1
  )
  echo ok> ".venv\modules_ok.txt"
)

rem --- 2b. data folder layout: files left by older versions of the port are moved into "data" (nothing is deleted or overwritten)
".venv\Scripts\python.exe" -m dq4_pc.paths

rem --- 2c. original menu windows: layout read from the game's code (once only, if the code dump exists); a layout file made by an older version is rebuilt
rem     the cache folder is asked of Python: with DQ4_DATA it is not "data\cache"
set "DQ4_CACHE=data\cache"
for /f "usebackq delims=" %%C in (`".venv\Scripts\python.exe" -m dq4_pc.paths --cache`) do set "DQ4_CACHE=%%C"
if exist "%DQ4_CACHE%\ui_layout.json" (
  ".venv\Scripts\python.exe" -c "import json,os,sys; d=json.load(open(os.path.join(os.environ['DQ4_CACHE'], 'ui_layout.json'), encoding='utf-8')); sys.exit(0 if 'message' in d and d['header'].get('gen', 1) >= 3 else 1)" >nul 2>nul
  if errorlevel 1 del "%DQ4_CACHE%\ui_layout.json"
)
if not exist "%DQ4_CACHE%\ui_layout.json" (
  if exist "%DQ4_CACHE%\il2cpp\dump.cs" (
    call :m_ui_reading
    ".venv\Scripts\python.exe" "tools\ui_il2cpp\generate_ui.py"
    if errorlevel 1 (
      call :m_ui_failed
      pause
    )
  ) else (
    call :m_ui_plain
  )
)

rem --- 3. launch: the console closes by itself when the game window closes; it stays open only if the game stops on an error (to read the message)
".venv\Scripts\python.exe" -m dq4_pc %*
set "CODE=%errorlevel%"
if not "%CODE%"=="0" (
  call :m_game_error %CODE%
  pause
)
exit /b %CODE%

rem ============================================================================================================================
rem Messages (one label per message; "exit /b" returns to the "call" line). ASCII text only: the Windows console does not display accents without a setting.
rem ============================================================================================================================

:m_title
title Dragon Quest IV - PC port (16:9 trial)
exit /b

:m_intro
echo.
echo  Dragon Quest IV - PC port ^(trial^)
echo  ---------------------------------
echo  Reads your APK files in "data\apk\fr" ^(French version^) or "data\apk\en" ^(English version^), according to the language chosen in the Esc menu ^(read at startup only^)
echo  and your saves in "data\saves" ^(data1.dat... copied from the phone^)
echo  ^(other data location: set DQ4_DATA=path\to\data^)
echo  ^(the game reads and writes its saves there; savestates are in "data\saves\savestates"^)
echo.
exit /b

:m_python_missing
echo  Python was not found. Install Python 3.12 from https://www.python.org/downloads/
echo  ^(tick "Add python.exe to PATH"^), then run this file again.
exit /b

:m_venv_other_pc
echo  The Python environment ^(.venv^) comes from another PC: it is being rebuilt ^(once only^)...
exit /b

:m_venv_creating
echo  Creating the Python environment ^(once only^)...
exit /b

:m_venv_failed
echo  Could not create the Python environment.
exit /b

:m_install
echo  Installing the modules ^(once only, 1 to 3 minutes^)...
exit /b

:m_install_failed
echo.
echo  The installation failed. If your Python is very recent, install Python 3.12:
echo     winget install Python.Python.3.12
echo  then delete the ".venv" folder here and run this file again.
exit /b

:m_ui_reading
echo  Reading the original window layout ^(once only, a few minutes^)...
exit /b

:m_ui_failed
echo.
echo  Reading failed: details in data\cache\ui_generation.log ^(plain menus this time^).
exit /b

:m_ui_plain
echo  Plain menus ^(for the original windows: run tools\dump_il2cpp.bat first^).
exit /b

:m_game_error
echo.
echo  The game stopped on an error ^(code %1^): read the lines above ^(details in data\logs^).
exit /b
