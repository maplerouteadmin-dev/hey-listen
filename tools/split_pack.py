"""Split the generated clips into packs people can install separately.

    python -I split_pack.py [--out A:/OotVoiceMod/dist]

Story: everything on the main path (Kokiri Forest through Hyrule Castle, and every main story scene in both eras).
World: towns, side characters, signs, minigames and the rest.
Each pack is a folder with its own manifest.json (paths relative to that folder) and can be dropped into the player's packs folder.
Clips are hard-linked, not copied, so building the packs costs no extra space on the same drive. Safe to re-run while generation continues.
"""
import argparse
import json
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
MANIFEST = r"A:\OotVoiceMod\pack\manifest.json"
MENU_TEXT = r"A:\OotVoiceMod\script\menu_text.json"
PACKS = {
    "OoT-Voices-Story": ("Main story voices", lambda area: area[0] in "12345"),
    "OoT-Voices-World": ("Side characters, towns and everything else", lambda area: area[0] not in "12345"),
}


def place(source, target):
    if os.path.exists(target):
        return
    try:
        os.link(source, target)
    except OSError:   # another drive, or a file system without hard links
        shutil.copy2(source, target)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=r"A:\OotVoiceMod\dist")
    args = ap.parse_args()
    clips = json.load(open(MANIFEST, encoding="utf-8"))["clips"]
    for name, (title, wanted) in PACKS.items():
        folder = os.path.join(args.out, name)
        os.makedirs(folder, exist_ok=True)
        chosen, size = [], 0
        for clip in clips:
            if not wanted(clip["area"]) or not os.path.exists(clip["path"]):
                continue
            relative = os.path.join(os.path.basename(os.path.dirname(clip["path"])), os.path.basename(clip["path"]))
            os.makedirs(os.path.join(folder, os.path.dirname(relative)), exist_ok=True)
            place(clip["path"], os.path.join(folder, relative))
            size += os.path.getsize(clip["path"])
            chosen.append(dict(slot=clip["slot"], id=clip["id"], text=clip["text"], area=clip["area"], path=relative.replace("\\", "/")))
        with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(dict(pack=name, title=title, clips=chosen), f, ensure_ascii=False)
        if os.path.exists(MENU_TEXT):
            shutil.copy2(MENU_TEXT, os.path.join(folder, "menu_text.json"))
        print("%-18s %6d clips  %.2f GB  -> %s" % (name, len(chosen), size / 1e9, folder))


if __name__ == "__main__":
    main()
