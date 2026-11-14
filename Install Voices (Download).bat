@echo off
title OoT Voices - download and install
echo This downloads the voice pack from GitHub and installs it into whichever of
echo Hookshot, Longshot, or an emulator (Fritchii/eden) it finds on this PC.
echo The main story cast is included by default; it will ask before fetching more.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_voice_mod.ps1"
echo.
pause
