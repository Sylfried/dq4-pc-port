@echo off
rem Dragon Quest VI - PC port: the shared launcher (tools\launch_game.bat) run for this game.
setlocal
set "DQ_GAME=dq6"
set "GAME_NAME=Dragon Quest VI"
call "%~dp0tools\launch_game.bat" %*
exit /b %errorlevel%
