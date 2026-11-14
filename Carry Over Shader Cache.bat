@echo off
title OoT - carry over shader cache
echo Copies OoT's built shaders from the old Fritchii data folder into the new one.
echo Close Fritchii before running this.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\carry_shader_cache.ps1"
echo.
pause
