@echo off
title OoT Voices - checking clips
set TEMP=A:\OotVoiceMod\qwen\tmp
set TMP=A:\OotVoiceMod\qwen\tmp
set HF_HOME=A:\OotVoiceMod\audit\hf
echo Listening to every finished clip and comparing it with its script line.
echo It pauses while the game is open. Close this window to stop, and double-click this file to carry on.
"A:\OotVoiceMod\audit\venv\Scripts\python.exe" -I "%~dp0tools\audit_clips.py" >> "A:\OotVoiceMod\pack\audit.log" 2>&1
echo.
echo The check has ended. Results are in A:\OotVoiceMod\pack\audit.jsonl
pause
