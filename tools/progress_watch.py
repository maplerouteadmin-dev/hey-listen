"""Print the pack's percentage now, or wait for the next 5% step and report it.

    python -I progress_watch.py          current percentage
    python -I progress_watch.py --wait   exits at the next multiple of 5%, or if generation has stopped unexpectedly
"""
import json
import re
import subprocess
import sys
import time

LINES = r"A:\OotVoiceMod\script\pack_boxes.jsonl"   # what Generate Whole Game.bat generates: one line per text box
MANIFEST = r"A:\OotVoiceMod\pack\manifest.json"
POLL_SECONDS = 60
DEAD_POLLS = 10


def wanted():
    keys = set()
    for line in open(LINES, encoding="utf-8"):
        row = json.loads(line)
        if re.search("[A-Za-z]", row.get("say") or row["text"]):   # wordless boxes stay silent on purpose
            keys.add((row["voice_slot"], row["text"]))
    return keys


def done_count(keys):
    for attempt in range(5):
        try:
            clips = json.load(open(MANIFEST, encoding="utf-8"))["clips"]
            return sum((c["slot"], c["text"]) in keys for c in clips)
        except (OSError, ValueError):
            time.sleep(2)
    return None


def running(needle):
    query = "Get-CimInstance Win32_Process | ForEach-Object { $_.Name + ' ' + $_.CommandLine }"
    return needle in subprocess.run(["powershell", "-NoProfile", "-Command", query], capture_output=True, text=True).stdout


def main():
    keys = wanted()
    done = done_count(keys)
    percent = 100 * done / len(keys)
    if "--wait" not in sys.argv:
        print("%.1f%% (%d of %d lines)" % (percent, done, len(keys)))
        return
    target = min(int(percent // 5 + 1) * 5, 100)
    dead = 0
    while True:
        time.sleep(POLL_SECONDS)
        count = done_count(keys)
        if count is None:
            continue
        percent = 100 * count / len(keys)
        if percent >= target:
            print("REACHED %d%%: now %.1f%% (%d of %d lines)" % (target, percent, count, len(keys)), flush=True)
            return
        dead = 0 if running("qwen_pack") or running("lichii.exe") else dead + 1
        if dead >= DEAD_POLLS:
            print("STOPPED: generation is not running, at %.1f%% (%d of %d lines)" % (percent, count, len(keys)), flush=True)
            return


if __name__ == "__main__":
    main()
