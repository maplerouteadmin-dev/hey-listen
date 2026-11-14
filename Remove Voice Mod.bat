@echo off
title OoT Voices - removing the mod
echo Takes the voice mod back out of Fritchii/eden.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_voice_mod.ps1" -Action remove -Targets emulator
echo.
pause
