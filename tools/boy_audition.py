"""Try stronger voice descriptions for the Kokiri boys, beside the current voice, for listening.

    python boy_audition.py     writes samples/boys/index.html
"""
import csv
import hashlib
import html
import os
import re
import shutil
import sys

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
OUT = os.path.join(ROOT, "samples", "boys")
PACK = r"A:\OotVoiceMod\pack"
SLOTS = {"Npc_Kokiri_006": "Swordsman boy, energetic", "Npc_Kokiri_005": "Everyday boy", "Npc_Kokiri_008": "Quiet, hardworking boy", "Npc_Kokiri_Mido": "Mido, the bratty boss"}
STYLES = {
    "A: rough schoolboy": "A real ten-year-old boy, unmistakably male, with a scruffy, slightly husky playground voice and a lower chest tone. Not feminine, not breathy, not a woman imitating a child.",
    "B: older boy": "A twelve-year-old boy, clearly male, with a lower, slightly rough boyish voice just before it breaks. Plain and natural, not cute, not feminine.",
    "C: gruff little boy": "A small, sturdy boy with a low, gravelly little voice and a blunt, boyish way of talking. Definitely a boy, never girlish or sing-song.",
}


def safe(name):
    return re.sub(r"[^\w-]+", "_", name)


def short(text):
    """About one or two sentences, so every take is quick to compare."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out = sentences[0]
    for s in sentences[1:]:
        if len(out) + len(s) > 130:
            break
        out += " " + s
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    sheet = {row["slot"]: row for row in csv.DictReader(open(os.path.join(ROOT, "cast", "cast_sheet.csv"), encoding="utf-8-sig"))}
    model = Qwen3TTSModel.from_pretrained("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", device_map="cuda:0", dtype=torch.bfloat16)
    sections = []
    for slot, label in SLOTS.items():
        folder = os.path.join(PACK, safe(slot))
        current = safe(slot) + "_current.wav"
        shutil.copy(os.path.join(folder, "reference.wav"), os.path.join(OUT, current))
        text = short(open(os.path.join(folder, "reference.txt"), encoding="utf-8").read())
        rows = ['<div class="take"><b>Current voice</b><audio controls preload="none" src="%s"></audio></div>' % current]
        for number, (style, description) in enumerate(STYLES.items()):
            instruct = "%s %s. A character in a fantasy adventure game, clean studio recording." % (description, sheet[slot]["delivery"].rstrip("."))
            torch.manual_seed(int(hashlib.sha1((slot + style).encode()).hexdigest()[:8], 16))
            wavs, sr = model.generate_voice_design(text=text, language="English", instruct=instruct)
            name = "%s_%d.wav" % (safe(slot), number)
            sf.write(os.path.join(OUT, name), wavs[0], sr, subtype="PCM_16")
            print("%s %s: %.1f s" % (slot, style, len(wavs[0]) / sr), flush=True)
            rows.append('<div class="take"><b>%s</b><audio controls preload="none" src="%s"></audio></div>' % (html.escape(style), name))
        sections.append("<section><h2>%s</h2><p>%s</p>%s</section>" % (html.escape(label), html.escape(text), "".join(rows)))
    page = """<!doctype html><meta charset="utf-8"><title>Kokiri Boy Voices</title><style>
body{font-family:system-ui,sans-serif;max-width:720px;margin:32px auto;padding:0 16px;background:#14201a;color:#e8efe9}
section{background:#1e2e26;border-radius:10px;padding:16px;margin:16px 0}h2{margin:0 0 4px;font-size:18px}p{color:#b6c6bb;margin:0 0 12px}
.take{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:6px 0}audio{width:320px;max-width:60%}</style>
<h1>Kokiri boy voices</h1><p>Each row reads the same line. Pick the style letter that sounds most like a boy.</p>""" + "".join(sections)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print("done", flush=True)


if __name__ == "__main__":
    main()
