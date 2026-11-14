"""Generate the voice pack with Qwen3-TTS, resumable, in story order.

    python qwen_pack.py [--areas 1,2,3,4,5] [--batch 8] [--limit 0]

Each character is designed once from the cast sheet, and every line is cloned from that one reference, so a voice stays consistent.
Finished clips are never redone. Models unload whenever the game is open, so generation yields the GPU by itself.
Create A:/OotVoiceMod/pack/STOP to end it cleanly.
"""
import argparse
import csv
import gc
import hashlib
import json
import msvcrt
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TOOLS = os.path.dirname(os.path.abspath(__file__))
PACK_LINES = r"A:\OotVoiceMod\script\pack_child.jsonl"
PACK = r"A:\OotVoiceMod\pack"
SHEET = os.path.join(os.path.dirname(TOOLS), "cast", "cast_sheet.csv")
SAMPLES = os.path.join(os.path.dirname(TOOLS), "samples", "qwen")
DESIGN_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
CLONE_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
GAME = "lichii.exe"
READY_VOICES = {"Navi": "Navi", "Npc_Hylia_023_Shop": "Happy_Mask_Shopkeeper", "Npc_Zora_KingZora": "King_Zora"}
# Spoken English runs about 13 to 16 characters a second; far outside this, the take is broken.
MIN_SECONDS_PER_CHAR, MAX_SECONDS_PER_CHAR = 0.03, 0.22
TOKENS_PER_SECOND = 12   # the "12Hz" in the model's name


def game_running():
    """Whether to yield the GPU. A RUN_WITH_GAME file keeps generating anyway, e.g. while the game only compiles shaders."""
    if os.path.exists(os.path.join(PACK, "RUN_WITH_GAME")):
        return False
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + GAME, "/NH"], capture_output=True, text=True).stdout
    return GAME in out


def safe(name):
    return re.sub(r"[^\w-]+", "_", name)


def spoken(row):
    """What the voice reads, which can differ from the on-screen text used for matching."""
    return row.get("say") or row["text"]


def plausible(seconds, text):
    if seconds < 0.3:
        return False
    rate = seconds / max(len(text), 1)
    allowance = 1.6 / max(len(text), 1)   # short exclamations are slow per character
    return MIN_SECONDS_PER_CHAR <= rate <= MAX_SECONDS_PER_CHAR + allowance


class Models:
    def __init__(self, torch, cls):
        self.torch, self.cls, self.design, self.clone = torch, cls, None, None
        self.prompts = {}

    def wait_for_game(self):
        if game_running():
            self.release()
            print("game open, GPU released, waiting", flush=True)
            while game_running():
                time.sleep(15)
            print("game closed, resuming", flush=True)

    def ensure_design(self):
        self.wait_for_game()
        if self.clone is not None:
            self.clone = None
            self.prompts = {}
            gc.collect()
            self.torch.cuda.empty_cache()
        if self.design is None:
            self.design = self.cls.from_pretrained(DESIGN_MODEL, device_map="cuda:0", dtype=self.torch.bfloat16)

    def ensure(self):
        """Only the clone model: both together overflow a 12 GB card once batches run."""
        self.wait_for_game()
        if self.design is not None:
            self.design = None
            gc.collect()
            self.torch.cuda.empty_cache()
            self.torch.cuda.reset_peak_memory_stats()
        if self.clone is None:
            self.clone = self.cls.from_pretrained(CLONE_MODEL, device_map="cuda:0", dtype=self.torch.bfloat16)

    def release(self):
        self.design = self.clone = None
        self.prompts = {}
        gc.collect()
        self.torch.cuda.empty_cache()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--areas", default="1,2,3,4,5", help="Comma-separated area numbers, or 'all'")
    ap.add_argument("--lines", default=PACK_LINES, help="Line list made by story_scope.py")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    os.makedirs(PACK, exist_ok=True)
    # Two runs at once would overflow the GPU and overwrite each other's manifest.
    lock = open(os.path.join(PACK, "generating.lock"), "w")
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print("Generation is already running.", flush=True)
        return
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    areas = tuple(args.areas.split(","))
    sheet = {row["slot"]: row for row in csv.DictReader(open(SHEET, encoding="utf-8-sig"))}
    overrides = os.path.join(os.path.dirname(SHEET), "voice_overrides.json")
    if os.path.exists(overrides):   # descriptions changed after listening
        for slot, voice in json.load(open(overrides, encoding="utf-8")).items():
            sheet[slot]["voice"] = voice
    rows = []
    seen = set()
    say_path = os.path.join(os.path.dirname(SHEET), "say_overrides.json")
    say_overrides = json.load(open(say_path, encoding="utf-8")) if os.path.exists(say_path) else {}
    for line in open(args.lines, encoding="utf-8"):
        row = json.loads(line)
        if row["id"] in say_overrides:   # words the model can actually say, e.g. a grunt spelled out longer
            row["say"] = say_overrides[row["id"]]
        if not re.search("[A-Za-z]", spoken(row)):
            continue   # a box like "..." is a pause, left silent on purpose
        key = (row["voice_slot"], row["text"])
        if (args.areas == "all" or row["area"].split()[0] in areas) and key not in seen:
            seen.add(key)
            rows.append(row)
    if args.limit:
        rows = rows[:args.limit]
    manifest_path = os.path.join(PACK, "manifest.json")
    done = {}
    if os.path.exists(manifest_path):
        done = {(c["slot"], c["text"]): c for c in json.load(open(manifest_path, encoding="utf-8"))["clips"]}
    flagged_path = os.path.join(PACK, "flagged.jsonl")
    todo = [r for r in rows if (r["voice_slot"], r["text"]) not in done]
    print("%d lines to generate, %d already done" % (len(todo), len(done)), flush=True)
    models = Models(torch, Qwen3TTSModel)
    audio_secs = gen_secs = chars = lines_done = 0

    def reference(slot, models):
        """The locked reference clip for a voice, designing it the first time."""
        folder = os.path.join(PACK, safe(slot))
        os.makedirs(folder, exist_ok=True)
        wav, txt = os.path.join(folder, "reference.wav"), os.path.join(folder, "reference.txt")
        if not os.path.exists(wav):
            ready = READY_VOICES.get(slot)
            if ready:
                import shutil
                shutil.copy(os.path.join(SAMPLES, ready, "design_0.wav"), wav)
                shutil.copy(os.path.join(SAMPLES, ready, "ref.txt"), txt)
            else:
                info = sheet[slot]
                pool = sorted({spoken(r) for r in rows if r["voice_slot"] == slot and 60 <= len(spoken(r)) <= 170}, key=lambda t: -len(t))
                ref_text = " ".join(pool[:2]) if pool else "Hello there. It is good to see you again. Come in, come in, there is so much I want to tell you."
                instruct = "%s. %s. %s. A character in a fantasy adventure game, clean studio recording." % (info["voice"].rstrip("."), info["delivery"].rstrip("."), info["theme"].rstrip("."))
                torch.manual_seed(int(hashlib.sha1(slot.encode()).hexdigest()[:8], 16))
                wavs, sr = models.design.generate_voice_design(text=ref_text, language="English", instruct=instruct)
                sf.write(wav, wavs[0], sr)
                with open(txt, "w", encoding="utf-8") as f:
                    f.write(ref_text)
                print("designed %s (%.0f s)" % (slot, len(wavs[0]) / sr), flush=True)
        return wav, open(txt, encoding="utf-8").read()

    def speak(texts, prompt):
        """Clips for these lines, or None for a line that cannot fit in memory. Long batches split in half when the card fills up."""
        # A take that never stops would otherwise run to the model's limit of nearly three minutes.
        longest = max(len(t) for t in texts) * MAX_SECONDS_PER_CHAR + 3.6
        try:
            return models.clone.generate_voice_clone(text=texts, language=["English"] * len(texts), voice_clone_prompt=prompt, max_new_tokens=int(longest * TOKENS_PER_SECOND))
        except (torch.cuda.OutOfMemoryError, torch.AcceleratorError) as error:
            if "out of memory" not in str(error).lower():
                raise
        # Outside the except block, so the failed attempt's tensors are really released.
        gc.collect()
        torch.cuda.empty_cache()
        print("out of memory, splitting a batch of %d" % len(texts), flush=True)
        if len(texts) == 1:
            return [None], 24000
        first, sr = speak(texts[:len(texts) // 2], prompt)
        second, sr = speak(texts[len(texts) // 2:], prompt)
        return first + second, sr

    # Area by area, so the part of the game the player reaches next finishes first.
    groups = {}
    for row in todo:
        groups.setdefault((row["area"], row["voice_slot"]), []).append(row)
    current_area = None
    # Voices listed in priority_slots.json go first within their area, e.g. the town the player is in right now.
    priority_path = os.path.join(os.path.dirname(SHEET), "priority_slots.json")
    priority = json.load(open(priority_path, encoding="utf-8")) if os.path.exists(priority_path) else []
    rank = lambda item: (item[0][0], priority.index(item[0][1]) if item[0][1] in priority else len(priority), item[0][1])
    for (area, slot), lines in sorted(groups.items(), key=rank):
        if area != current_area:
            current_area = area
            # Voices are designed per area, so the next part of the game does not wait for the whole cast.
            for voice in sorted({key[1] for key in groups if key[0] == area}):
                if os.path.exists(os.path.join(PACK, "STOP")):
                    print("STOP file found, ending", flush=True)
                    return
                if not os.path.exists(os.path.join(PACK, safe(voice), "reference.wav")) and voice not in READY_VOICES:
                    models.ensure_design()
                    reference(voice, models)
        lines = sorted(lines, key=lambda r: len(r["text"]))
        for start in range(0, len(lines), args.batch):
            if os.path.exists(os.path.join(PACK, "STOP")):
                print("STOP file found, ending", flush=True)
                return
            models.ensure()
            if slot not in models.prompts:
                models.prompts = {}   # only the current voice stays on the GPU
                gc.collect()
                torch.cuda.empty_cache()
                wav, ref_text = reference(slot, models)
                models.prompts[slot] = models.clone.create_voice_clone_prompt(ref_audio=wav, ref_text=ref_text, x_vector_only_mode=False)
            prompt = models.prompts[slot]
            group = lines[start:start + args.batch]
            texts = [spoken(r) for r in group]
            torch.manual_seed(start + 11)
            t = time.time()
            wavs, sr = speak(texts, prompt)
            gen_secs += time.time() - t
            for row, audio in zip(group, wavs):
                if audio is None:
                    continue   # not in the manifest, so a re-run tries it again
                seconds = len(audio) / sr
                if not plausible(seconds, spoken(row)):
                    torch.manual_seed(start + 500)
                    retry, sr = speak([spoken(row)], prompt)
                    audio = retry[0]
                    if audio is None:
                        continue
                    seconds = len(audio) / sr
                    if not plausible(seconds, spoken(row)):
                        with open(flagged_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps(dict(id=row["id"], slot=slot, seconds=round(seconds, 1), text=row["text"]), ensure_ascii=False) + "\n")
                        continue
                name = hashlib.sha1(row["text"].encode("utf-8")).hexdigest()[:14] + ".wav"
                path = os.path.join(PACK, safe(slot), name)
                sf.write(path, audio, sr, subtype="PCM_16")
                done[(slot, row["text"])] = dict(slot=slot, id=row["id"], text=row["text"], path=path, area=row["area"])
                audio_secs += seconds
                chars += len(row["text"])
                lines_done += 1
            with open(manifest_path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(dict(clips=list(done.values())), f, ensure_ascii=False)
            for attempt in range(20):
                try:
                    os.replace(manifest_path + ".tmp", manifest_path)
                    break
                except PermissionError:   # the player is reading it at this moment
                    time.sleep(0.5)
            print("%s %d/%d | total %d lines, %.1f chars/s, %.2fx realtime, VRAM peak %.1f GB" % (slot, min(start + args.batch, len(lines)), len(lines), lines_done, chars / gen_secs, audio_secs / gen_secs, torch.cuda.max_memory_allocated() / 1e9), flush=True)
    print("pack finished: %d clips in manifest" % len(done), flush=True)


if __name__ == "__main__":
    main()
