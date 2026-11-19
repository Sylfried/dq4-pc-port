@echo off
rem The launcher of the port, shared by the games: launch_dq4.bat, launch_dq5.bat and launch_dq6.bat (project root) set DQ_GAME and GAME_NAME, then call this file.
setlocal
cd /d "%~dp0.."
if not defined DQ_GAME set "DQ_GAME=dq4"
if not defined GAME_NAME set "GAME_NAME=Dragon Quest IV"

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

rem --- 2. isolated environment + modules (once only, shared by the games)
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
".venv\Scripts\python.exe" -m dq456_pc.paths

rem --- 2c. original menu windows: layout read from the game's code, once only per game, at its first start: the structure of the game's code is read from the APK
rem     (tools\dump_il2cpp.py: downloads Il2CppDumper the first time, internet needed once), then the layout is built from it (tools\ui_il2cpp\generate_ui.py, a few minutes);
rem     without internet the game starts with plain menus and it is tried again at the next start. A layout file made by an older version is rebuilt.
rem     the cache folder of the game is asked of Python: with DQ_DATA it is not "data\cache\<game>\fr"
set "GAME_CACHE="
for /f "usebackq delims=" %%C in (`".venv\Scripts\python.exe" -m dq456_pc.paths --cache`) do set "GAME_CACHE=%%C"
if not defined GAME_CACHE goto :launch
if exist "%GAME_CACHE%\ui_layout.json" (
  ".venv\Scripts\python.exe" -c "import json,os,sys; d=json.load(open(os.path.join(os.environ['GAME_CACHE'], 'ui_layout.json'), encoding='utf-8')); sys.exit(0 if 'message' in d and d['header'].get('gen', 1) >= 3 else 1)" >nul 2>nul
  if errorlevel 1 del "%GAME_CACHE%\ui_layout.json"
)
if not exist "%GAME_CACHE%\ui_layout.json" (
  if not exist "%GAME_CACHE%\il2cpp\dump.cs" (
    call :m_dump_reading
    ".venv\Scripts\python.exe" "tools\dump_il2cpp.py"
    if errorlevel 1 call :m_dump_failed
  )
)
if not exist "%GAME_CACHE%\ui_layout.json" (
  if exist "%GAME_CACHE%\il2cpp\dump.cs" (
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

:launch
rem --- 3. launch: the console closes by itself when the game window closes; it stays open only if the game stops on an error (to read the message),
rem     or when this version of the port does not run the game (exit code 3: only its files were checked)
".venv\Scripts\python.exe" -m dq456_pc %*
set "CODE=%errorlevel%"
if not "%CODE%"=="0" (
  if not "%CODE%"=="3" call :m_game_error %CODE%
  pause
)
exit /b %CODE%

rem ============================================================================================================================
rem Messages (one label per message; "exit /b" returns to the "call" line). ASCII text only: the Windows console does not display accents without a setting.
rem ============================================================================================================================

:m_title
title %GAME_NAME% - PC port
exit /b

:m_intro
echo.
echo  %GAME_NAME% - PC port
echo  ---------------------------------
echo  Reads your APK files in "data\apk\%DQ_GAME%\fr" ^(French version^) or "data\apk\%DQ_GAME%\en" ^(English version^), according to the language chosen in the Esc menu ^(read at startup only^)
echo  and your saves in "data\saves\%DQ_GAME%" ^(data1.dat... copied from the phone^)
echo  ^(other data location: set DQ_DATA=path\to\data^)
echo  ^(the game reads and writes its saves there; savestates are in "data\saves\%DQ_GAME%\savestates"^)
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

:m_dump_reading
echo.
echo  First start of %GAME_NAME%: reading the structure of the game code from your APK ^(once only, 1 to 3 minutes;
echo  the first time, the free tool Il2CppDumper is downloaded from GitHub: internet needed once^)...
exit /b

:m_dump_failed
echo.
echo  The structure of the game code could not be read ^(no internet?^): plain menus this time, tried again at the next start.
exit /b

:m_ui_reading
echo  Reading the original window layout ^(once only, a few minutes^)...
exit /b

:m_ui_failed
echo.
echo  Reading failed: details in "%GAME_CACHE%\ui_generation.log" ^(plain menus this time^).
exit /b

:m_ui_plain
echo  Plain menus this time ^(the original windows are set up at the next start^).
exit /b

:m_game_error
echo.
echo  The game stopped on an error ^(code %1^): read the lines above ^(details in data\logs^).
exit /b
