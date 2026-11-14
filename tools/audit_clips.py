"""Listen to every finished clip with speech recognition and flag those that do not say their script line.

    python audit_clips.py [--limit 40] [--once]

Runs on the CPU at low priority, so it can share the PC with generation, and pauses while the game is open.
Results go to A:/OotVoiceMod/pack/audit.jsonl, one per clip, and are never repeated unless the clip changes.
Without --once it keeps going until generation has finished and every clip has been heard.
"""
import argparse
import ctypes
import difflib
import json
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PACK = r"A:\OotVoiceMod\pack"
MANIFEST = os.path.join(PACK, "manifest.json")
RESULTS = os.path.join(PACK, "audit.jsonl")
LINES = r"A:\OotVoiceMod\script\pack_full.jsonl"
MODEL = "small.en"
THREADS = 3
GAME = "lichii.exe"
GOOD_MATCH = 0.72           # names are often misheard, so an exact match is not expected
SHORT_WORDS = 3             # recognition is unreliable on one-to-three word lines; those are only flagged if nothing similar is heard
VOCABULARY = ("Link, Navi, Saria, Mido, Kokiri, Hyrule, Deku Tree, Zelda, Impa, Malon, Talon, Ingo, Epona, Darunia, Goron, gowo, goro, Ruto, "
              "Zora, Jabu-Jabu, Gerudo, Nabooru, Ganondorf, Sheik, Rauru, Kakariko, Dampé, Poe, rupees, ocarina, Lon Lon, Kaepora Gaebora")
BELOW_NORMAL = 0x4000


def running(name):
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + name, "/NH"], capture_output=True, text=True).stdout
    return name in out


def generating():
    query = "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | ForEach-Object { $_.CommandLine }"
    out = subprocess.run(["powershell", "-NoProfile", "-Command", query], capture_output=True, text=True).stdout
    return "qwen_pack" in out


FILLER = {"hm", "hmm", "huh", "ha", "hah", "heh", "ah", "aah", "oh", "ooh", "whoa", "woah", "agh", "akk", "eh", "um", "uh", "mm", "ow", "yah", "hyah", "wah", "eek", "gah"}
SAME = {"kinda": "kind of", "gonna": "going to", "wanna": "want to", "gotta": "got to", "ya": "you", "yer": "your", "'em": "them", "okay": "ok"}


def words(text):
    """Comparable words: spelling of grunts and casual contractions varies, so neither should count against a clip."""
    raw = re.sub(r"[^a-z0-9' ]+", " ", text.lower().replace("-", " ").replace("é", "e").replace("’", "'")).split()
    return [part for w in raw if w.strip("'") not in FILLER for part in SAME.get(w, w.strip("'")).split()]


def similarity(expected, heard):
    return difflib.SequenceMatcher(None, words(expected), words(heard), autojunk=False).ratio()


def verdict(score, expected):
    if not words(expected):
        return True   # only grunts, which recognition cannot judge
    limit = 0.34 if len(words(expected)) <= SHORT_WORDS else GOOD_MATCH
    return score >= limit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), BELOW_NORMAL)
    from faster_whisper import WhisperModel
    model = WhisperModel(MODEL, device="cpu", compute_type="int8", cpu_threads=THREADS)
    spoken = {}
    for line in open(LINES, encoding="utf-8"):
        row = json.loads(line)
        if row.get("say"):
            spoken[(row["voice_slot"], row["text"])] = row["say"]
    done = {}
    if os.path.exists(RESULTS):
        for line in open(RESULTS, encoding="utf-8"):
            r = json.loads(line)
            done[r["path"]] = r["mtime"]
    heard_seconds = spent = checked = flagged = 0
    while True:
        for attempt in range(10):
            try:
                clips = json.load(open(MANIFEST, encoding="utf-8"))["clips"]
                break
            except (OSError, ValueError):
                time.sleep(2)
        todo = [c for c in clips if os.path.exists(c["path"]) and done.get(c["path"]) != os.path.getmtime(c["path"])]
        if args.limit:
            todo = todo[:max(args.limit - checked, 0)]
        print("%d clips to check, %d checked so far" % (len(todo), len(done)), flush=True)
        for clip in todo:
            while running(GAME):
                time.sleep(15)
            expected = spoken.get((clip["slot"], clip["text"]), clip["text"])
            t = time.time()
            segments, info = model.transcribe(clip["path"], language="en", beam_size=3, vad_filter=False, condition_on_previous_text=False,
                                              initial_prompt=VOCABULARY, word_timestamps=False)
            heard = " ".join(s.text.strip() for s in segments).strip()
            spent += time.time() - t
            heard_seconds += info.duration
            checked += 1
            score = similarity(expected, heard)
            ok = verdict(score, expected)
            flagged += not ok
            record = dict(ok=ok, score=round(score, 3), slot=clip["slot"], area=clip["area"], seconds=round(info.duration, 1), expected=expected, heard=heard,
                          path=clip["path"], mtime=os.path.getmtime(clip["path"]))
            with open(RESULTS, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            done[clip["path"]] = record["mtime"]
            if checked % 50 == 0 or args.limit:
                print("%d heard, %d flagged, %.1fx realtime%s" % (checked, flagged, heard_seconds / max(spent, 0.1), "" if ok else " | FLAG %.2f %s | heard: %s" % (score, expected[:70], heard[:70])), flush=True)
        if args.once or args.limit:
            break
        if not generating() and not todo:
            break
        if not todo:
            time.sleep(120)
    print("audit finished: %d heard, %d flagged" % (checked, flagged), flush=True)


if __name__ == "__main__":
    main()
