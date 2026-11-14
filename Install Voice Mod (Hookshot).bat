@echo off
title OoT Voices - install into Hookshot
echo Copies the built voice mod into the Hookshot game at A:\Games. Close Hookshot and its Builder first.
echo After a Hookshot update rebuilds the game, run this again.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_voice_mod.ps1" -Stage "A:\OotVoiceMod\mod_stage\OoT Voices" -GameDir "A:\Games" -Targets hookshot
echo.
pause
