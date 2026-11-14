"""Make the same voice test as elevenlabs_samples.py with Qwen3-TTS, locally and for free.

    python qwen_samples.py [--takes 1] [--force]

Step 1 designs each character once from its written description, three options each.
Step 2 clones option 0 (or --pick Name=n) for every line, so a character keeps one voice across all lines.
Run this with the game closed: it needs the GPU's memory.
"""
import argparse
import html
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
OUT = os.path.join(os.path.dirname(TOOLS), "samples", "qwen")
LINES = r"A:\OotVoiceMod\script\line_assignments.jsonl"
DESIGN_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
CLONE_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"

# The same characters, descriptions and lines as the ElevenLabs test, so the two can be compared directly.
source = open(os.path.join(TOOLS, "elevenlabs_samples.py"), encoding="utf-8").read()
CAST = eval(source[source.index("CAST = {") + 7:source.index("\n\n\ndef api_key")])

# Plain-English delivery directions used in place of ElevenLabs' bracket tags.
DIRECTION = {
    "[happy]": "cheerful and warm", "[excited]": "excited and urgent", "[worried]": "worried and frightened", "[thoughtful]": "thoughtful and quiet",
    "[surprised]": "startled and surprised", "[sad]": "sad and disappointed", "[smoothly]": "smooth and pleasant", "[chuckles]": "amused, with a soft chuckle",
    "[mischievously]": "sly and mischievous", "[angry]": "cold and furious", "[shouts]": "shouting angrily", "[panicked]": "panicked and horrified",
    "[pompously]": "grand and pompous", "[crying]": "weeping and distraught", "[flustered]": "flustered and rushed", "[laughs]": "laughing heartily", "[curious]": "curious and puzzled",
}


def safe(name):
    return name.replace(" ", "_")


def load_lines():
    wanted = {i for c in CAST.values() for i, _ in c["lines"]}
    found = {}
    with open(LINES, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row["id"] in wanted:
                found[row["id"]] = row["text"]
    missing = wanted - set(found)
    if missing:
        sys.exit("Lines not found: %s" % sorted(missing))
    return found


def report_vram(torch, label):
    print("%s: %.1f GB in use, peak %.1f GB" % (label, torch.cuda.memory_allocated() / 1e9, torch.cuda.max_memory_allocated() / 1e9), flush=True)


def write_page(rows):
    parts = ["<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Local Voice Samples</title>",
             "<style>:root{color-scheme:light dark}body{font:16px system-ui;max-width:900px;margin:24px auto;padding:0 16px}h2{margin-top:32px}.r{padding:10px 0;border-top:1px solid #8884}.t{margin-bottom:6px}.m{font-size:13px;opacity:.7;margin-top:6px}audio{width:100%;height:36px}</style>",
             "<h1>Qwen3-TTS local voice samples</h1>"]
    for name, data in rows.items():
        parts.append("<h2>%s</h2><p>%s</p>" % (html.escape(name), html.escape(CAST[name]["description"])))
        for i in range(3):
            parts.append("<div class=r><div class=m>Design option %d%s</div><audio controls preload=none src='%s/design_%d.wav'></audio></div>" % (i, " (used below)" if i == data["pick"] else "", safe(name), i))
        for row in data["clips"]:
            parts.append("<div class=r><div class=t>%s</div><audio controls preload=none src='%s'></audio></div>" % (html.escape(row[0]), html.escape(row[1])))
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write("".join(parts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pick", action="append", default=[], help="Character=option")
    ap.add_argument("--force", action="store_true", help="Redo line clips")
    ap.add_argument("--dtype", default="bfloat16", choices=["bfloat16", "float16"])
    args = ap.parse_args()
    picks = {}
    for item in args.pick:
        name, value = item.rsplit("=", 1)
        picks[name] = int(value)
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    if not torch.cuda.is_available():
        sys.exit("CUDA is not available")
    free = torch.cuda.mem_get_info()[0] / 1e9
    print("GPU memory free: %.1f GB" % free, flush=True)
    if free < 6:
        sys.exit("Only %.1f GB of GPU memory free. Close the game first." % free)
    lines = load_lines()
    dtype = getattr(torch, args.dtype)
    os.makedirs(OUT, exist_ok=True)

    # Step 1: design.
    need_design = [n for n in CAST if not all(os.path.exists(os.path.join(OUT, safe(n), "design_%d.wav" % i)) for i in range(3))]
    if need_design:
        t = time.time()
        model = Qwen3TTSModel.from_pretrained(DESIGN_MODEL, device_map="cuda:0", dtype=dtype)
        print("design model loaded in %.0f s" % (time.time() - t), flush=True)
        report_vram(torch, "design model")
        for name in need_design:
            folder = os.path.join(OUT, safe(name))
            os.makedirs(folder, exist_ok=True)
            ref_text = " ".join(lines[i] for i, _ in CAST[name]["lines"][:2])
            with open(os.path.join(folder, "ref.txt"), "w", encoding="utf-8") as f:
                f.write(ref_text)
            for option in range(3):
                torch.manual_seed(1000 + option)
                wavs, sr = model.generate_voice_design(text=ref_text, language="English", instruct=CAST[name]["description"])
                sf.write(os.path.join(folder, "design_%d.wav" % option), wavs[0], sr)
                print("%s design %d: %.1f s of audio" % (name, option, len(wavs[0]) / sr), flush=True)
        report_vram(torch, "after design")
        del model
        torch.cuda.empty_cache()

    # Step 2: one locked voice per character, every line cloned from it.
    t = time.time()
    model = Qwen3TTSModel.from_pretrained(CLONE_MODEL, device_map="cuda:0", dtype=dtype)
    print("clone model loaded in %.0f s" % (time.time() - t), flush=True)
    report_vram(torch, "clone model")
    results = {}
    audio_secs = gen_secs = chars = 0
    for name, cast in CAST.items():
        folder = os.path.join(OUT, safe(name))
        pick = picks.get(name, 0)
        ref_text = open(os.path.join(folder, "ref.txt"), encoding="utf-8").read()
        prompt = model.create_voice_clone_prompt(ref_audio=os.path.join(folder, "design_%d.wav" % pick), ref_text=ref_text, x_vector_only_mode=False)
        clips = []
        for n, (line_id, tag) in enumerate(cast["lines"]):
            text = lines[line_id]
            file_name = "pick%d_%02d.wav" % (pick, n)
            path = os.path.join(folder, file_name)
            if args.force or not os.path.exists(path):
                torch.manual_seed(7 + n)
                t = time.time()
                wavs, sr = model.generate_voice_clone(text=text, language="English", voice_clone_prompt=prompt)
                gen_secs += time.time() - t
                sf.write(path, wavs[0], sr)
                audio_secs += len(wavs[0]) / sr
                chars += len(text)
            clips.append((text, "%s/%s" % (safe(name), file_name)))
        results[name] = dict(pick=pick, clips=clips)
        print("%s done" % name, flush=True)
        write_page(results)
    report_vram(torch, "finished")
    if gen_secs:
        print("generation: %.0f s for %.0f s of audio (%.2fx realtime), %d characters, %.1f characters per second" % (gen_secs, audio_secs, audio_secs / gen_secs, chars, chars / gen_secs))
        print("full script estimate: %.1f hours for 1,010,124 characters, one take" % (1010124 / (chars / gen_secs) / 3600))


if __name__ == "__main__":
    main()
