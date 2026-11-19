@echo off
rem Dragon Quest V - PC port: the shared launcher (tools\launch_game.bat) run for this game.
setlocal
set "DQ_GAME=dq5"
set "GAME_NAME=Dragon Quest V"
call "%~dp0tools\launch_game.bat" %*
exit /b %errorlevel%
