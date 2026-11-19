@echo off
rem Debug mode of the port (dq456_pc/debug): the game is chosen here, then its launcher runs with --debug (overlay, pause, steps, speed: keys F2 to F7).
setlocal
set "GAME=%~1"
if not defined GAME (
  choice /c 456 /n /m "Debug: Dragon Quest IV, V or VI? [4/5/6] "
  if errorlevel 3 ( set "GAME=6" ) else if errorlevel 2 ( set "GAME=5" ) else ( set "GAME=4" )
) else shift
call "%~dp0launch_dq%GAME%.bat" --debug %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %errorlevel%
