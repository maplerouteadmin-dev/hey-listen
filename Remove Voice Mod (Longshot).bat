@echo off
title OoT Voices - remove from Longshot
echo Takes the voice mod back out of the Longshot game at A:\Games\longshot. Close Longshot and its Launcher first.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_voice_mod.ps1" -Action remove -GameDir "A:\Games\longshot" -Targets longshot
echo.
pause
