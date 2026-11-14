"""Apply the boy voice styles chosen by ear: back up the old clips and queue the lines again. Run only while generation is stopped.

    python -I redo_boys.py
"""
import json
import os
import re
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
PACK = r"A:\OotVoiceMod\pack"
BACKUP = r"A:\OotVoiceMod\pack_backup\boys_before_restyle"
SAMPLES = os.path.join(ROOT, "samples", "boys")
A = "A real ten-year-old boy, unmistakably male, with a scruffy, slightly husky playground voice and a lower chest tone. Not feminine, not breathy, not a woman imitating a child"
C = "A small, sturdy boy with a low, gravelly little voice and a blunt, boyish way of talking. Definitely a boy, never girlish or sing-song"
# Takes already heard and approved are kept as they are; the others are designed from the same chosen description.
HEARD = {"Npc_Kokiri_006": ("A", 0), "Npc_Kokiri_005": ("C", 2), "Npc_Kokiri_008": ("A", 0), "Npc_Kokiri_Mido": ("C", 2)}
DESIGN = {"Npc_Kokiri_001_Shop": "A", "Npc_Kokiri_002": "C", "Npc_Kokiri_003": "A", "Npc_Kokiri_004": "C", "Npc_Kokiri_007": "A",
          "Crowd_Kokiri_BT": "C", "Npc_Hylia_030": "A", "Crowd_Hylia_B": "C"}


def safe(name):
    return re.sub(r"[^\w-]+", "_", name)


def short(text):
    """The same trim the listening samples used."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out = sentences[0]
    for s in sentences[1:]:
        if len(out) + len(s) > 130:
            break
        out += " " + s
    return out


def main():
    if os.path.exists(BACKUP):
        sys.exit("Backup already exists, so this has already been applied: " + BACKUP)
    os.makedirs(BACKUP)
    style = {slot: value[0] for slot, value in HEARD.items()}
    style.update(DESIGN)
    with open(os.path.join(ROOT, "cast", "voice_overrides.json"), "w", encoding="utf-8") as f:
        json.dump({slot: (A if letter == "A" else C) for slot, letter in style.items()}, f, ensure_ascii=False, indent=1)
    path = os.path.join(PACK, "manifest.json")
    shutil.copy(path, os.path.join(BACKUP, "manifest.json"))
    manifest = json.load(open(path, encoding="utf-8"))
    before = len(manifest["clips"])
    manifest["clips"] = [c for c in manifest["clips"] if c["slot"] not in style]
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)
    os.replace(path + ".tmp", path)
    for slot in style:
        folder = os.path.join(PACK, safe(slot))
        ref_text = None
        if os.path.isdir(folder):
            if slot in HEARD:
                ref_text = short(open(os.path.join(folder, "reference.txt"), encoding="utf-8").read())
            shutil.move(folder, os.path.join(BACKUP, safe(slot)))
        if slot in HEARD:
            os.makedirs(folder)
            shutil.copy(os.path.join(SAMPLES, "%s_%d.wav" % (safe(slot), HEARD[slot][1])), os.path.join(folder, "reference.wav"))
            with open(os.path.join(folder, "reference.txt"), "w", encoding="utf-8") as f:
                f.write(ref_text)
    print("voices restyled: %d, clips queued again: %d, clips kept: %d" % (len(style), before - len(manifest["clips"]), len(manifest["clips"])))


if __name__ == "__main__":
    main()
