@echo off
title OoT Voices - generating
set TEMP=A:\OotVoiceMod\qwen\tmp
set TMP=A:\OotVoiceMod\qwen\tmp
set HF_HOME=A:\OotVoiceMod\qwen\hf
if exist "A:\OotVoiceMod\pack\STOP" del "A:\OotVoiceMod\pack\STOP"
echo Generating voices for the whole game. Finished lines are never redone.
echo It pauses by itself while the game is open, and restarts itself after a crash.
echo Close this window to stop, and double-click this file to carry on later.
echo Progress is written to A:\OotVoiceMod\pack\generation.log
:run
"A:\OotVoiceMod\qwen\venv\Scripts\python.exe" "%~dp0tools\qwen_pack.py" --lines "A:\OotVoiceMod\script\pack_boxes.jsonl" --areas all --batch 8 >> "A:\OotVoiceMod\pack\generation.log" 2>> "A:\OotVoiceMod\pack\generation.err"
if errorlevel 1 (
    echo Stopped with an error at %time%, restarting in 30 seconds...
    timeout /t 30 /nobreak >nul
    goto run
)
echo.
echo Generation has ended. The last lines of the log say why.
pause
