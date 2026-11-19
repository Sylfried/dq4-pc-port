@echo off
rem Dragon Quest IV - PC port: the shared launcher (tools\launch_game.bat) run for this game.
setlocal
set "DQ_GAME=dq4"
set "GAME_NAME=Dragon Quest IV"
call "%~dp0tools\launch_game.bat" %*
exit /b %errorlevel%
