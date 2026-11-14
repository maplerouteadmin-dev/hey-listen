@echo off
title OoT Voices
echo Start the game whenever you like. Close this window to stop the voices.
echo.
python -I "%~dp0tools\voice_player.py" --manifest "A:\OotVoiceMod\pack\manifest.json"
pause
