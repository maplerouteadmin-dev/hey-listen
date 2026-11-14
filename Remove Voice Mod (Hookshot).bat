@echo off
title OoT Voices - remove from Hookshot
echo Takes the voice mod back out of the Hookshot game at A:\Games. Close Hookshot and its Builder first.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_voice_mod.ps1" -Action remove -GameDir "A:\Games" -Targets hookshot
echo.
pause
