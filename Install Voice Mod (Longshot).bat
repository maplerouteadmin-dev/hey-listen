@echo off
title OoT Voices - install into Longshot
echo Copies the built voice mod into the Longshot game at A:\Games\longshot. Close Longshot and its Launcher first.
echo After a Longshot update rebuilds the game, run this again.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_voice_mod.ps1" -Stage "A:\OotVoiceMod\mod_stage\OoT Voices" -GameDir "A:\Games\longshot" -Targets longshot
echo.
pause
