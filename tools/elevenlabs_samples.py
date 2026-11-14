"""Make a small ElevenLabs test for three contrasting characters, within a hard credit cap.

    python -I elevenlabs_samples.py --dry-run
    python -I elevenlabs_samples.py [--max-credits 7000] [--pick Navi=1]

The key comes from ELEVENLABS_API_KEY or oot_voice_mod/.elevenlabs_key and is never printed.
Designs are original voices. Finished clips are reused on a re-run, so a re-run spends nothing on them.
"""
import argparse
import base64
import html
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "samples", "elevenlabs")
LINES = r"A:\OotVoiceMod\script\line_assignments.jsonl"
API = "https://api.elevenlabs.io"
MODELS = [("eleven_v4", True), ("eleven_multilingual_v2", False)]
LAST_HEADERS = {}

CAST = {
    "Navi": dict(slot="Navi", description="A bright, small, airy young woman's voice for a tiny glowing fairy guide in a fantasy game. High but never squeaky, quick and alert, urgent when warning and fond underneath the nagging. Light and chiming, with clear diction.", lines=[
        ("EventFlowMsg/Dm_Kokiri_0060:Dm_Kokiri_0060_0011", "[happy]"),
        ("EventFlowMsg/Dm_FireTemple_0020:Dm_FireTemple_0020_0013", "[excited]"),
        ("EventFlowMsg/Dm_InsideGanonCastle_0005:Dm_InsideGanonCastle_0005_0000", "[worried]"),
        ("EventFlowMsg/Dm_Kokiri_0145:Dm_Kokiri_0145_0027", "[thoughtful]"),
        ("EventFlowMsg/Dm_Zora_0010:Dm_Zore_0010_0008", "[surprised]"),
        ("EventFlowMsg/Dm_MelodyGet_Forest:Dm_MelodyGet_Forest_0024", "[sad]")]),
    "Happy Mask Shopkeeper": dict(slot="Npc_Hylia_023_Shop", description="A silky, theatrical middle-aged man's voice for an unnerving travelling mask collector in a fantasy game. Honeyed and precise, the smile always audible, intimate and too pleasant, capable of sudden cold menace.", lines=[
        ("EventFlowMsg/Npc_Hylia_023_Shop_Child:Talk_51", "[smoothly]"),
        ("EventFlowMsg/Npc_Hylia_023_Shop_Child:Mask_02", "[chuckles]"),
        ("EventFlowMsg/Npc_Hylia_023_Shop_Child:Talk_03", "[mischievously]"),
        ("EventFlowMsg/Npc_Hylia_023_Shop_Child:Talk_14", "[angry]"),
        ("EventFlowMsg/Npc_Hylia_023_Shop_Child:Talk_33", "[shouts]"),
        ("EventFlowMsg/Npc_Hylia_023_Shop_Child:Mask_100_02", "[panicked]")]),
    "King Zora": dict(slot="Npc_Zora_KingZora", description="A very deep, slow, plummy old man's voice for the enormous king of an aquatic fantasy people. Ponderous with long pauses, pompous yet kind, with a wet, resonant, gently gurgling quality.", lines=[
        ("EventFlowMsg/Get_StoneOfWater:StoneOfWater_Talk_10", "[pompously]"),
        ("EventFlowMsg/Get_StoneOfWater:StoneOfWater_Talk_17", "[sad]"),
        ("EventFlowMsg/Dm_Zora_0010:Dm_Zore_0010_0011", "[crying]"),
        ("EventFlowMsg/Dm_Zora_0010:Dm_Zore_0010_0022", "[flustered]"),
        ("EventFlowMsg/SageOfWater:KingZora_Talk_48", "[laughs]"),
        ("EventFlowMsg/Get_StoneOfWater:StoneOfWater_ShowRutoLetterBySide_00", "[curious]")]),
}


def api_key():
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        for name in (".elevenlabs_key", ".elevenlabs_key.txt"):
            path = os.path.join(HERE, name)
            if os.path.exists(path):
                with open(path, encoding="utf-8-sig") as f:
                    key = f.read().strip()
                break
    if not key:
        sys.exit("No API key found. Save it in oot_voice_mod/.elevenlabs_key and run again.")
    return key


def call(method, path, key, body=None, raw=False):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={"xi-api-key": key, "Content-Type": "application/json"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=180) as res:
                payload = res.read()
                LAST_HEADERS.clear()
                LAST_HEADERS.update({k.lower(): v for k, v in res.headers.items()})
            return payload if raw else json.loads(payload)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:500]
            if error.code != 429 or attempt == 5:
                sys.exit("ElevenLabs refused %s %s: HTTP %d %s" % (method, path.split("?")[0], error.code, detail))
            print("rate limited, waiting %d seconds" % (10 * (attempt + 1)), flush=True)
            time.sleep(10 * (attempt + 1))


def used(key):
    sub = call("GET", "/v1/user/subscription", key)
    return sub["character_count"], sub["character_limit"]


def load_lines():
    wanted = {i for c in CAST.values() for i, _ in c["lines"]}
    found = {}
    with open(LINES, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row["id"] in wanted:
                found[row["id"]] = row
    missing = wanted - set(found)
    if missing:
        sys.exit("Lines not found: %s" % sorted(missing))
    return found


def safe(name):
    return name.replace(" ", "_")


def write_page(manifest):
    parts = ["<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Voice Samples</title>",
             "<style>:root{color-scheme:light dark}body{font:16px system-ui;max-width:900px;margin:24px auto;padding:0 16px}h2{margin-top:32px}.r{padding:10px 0;border-top:1px solid #8884}.t{margin-bottom:6px}.m{font-size:13px;opacity:.7;margin-top:6px}audio{width:100%;height:36px}</style>",
             "<h1>ElevenLabs voice samples</h1>"]
    for name, data in manifest.items():
        parts.append("<h2>%s</h2><p>%s</p>" % (html.escape(name), html.escape(CAST[name]["description"])))
        for i, preview in enumerate(data["previews"]):
            parts.append("<div class=r><div class=m>Design option %d%s</div><audio controls preload=none src='%s'></audio></div>" % (i, " (used below)" if i == data["pick"] else "", html.escape(preview)))
        for row in data["clips"]:
            parts.append("<div class=r><div class=t>%s</div>" % html.escape(row["text"]))
            for model, path in row["audio"].items():
                parts.append("<div class=m>%s</div><audio controls preload=none src='%s'></audio>" % (html.escape(model), html.escape(path)))
            parts.append("</div>")
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write("".join(parts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-credits", type=int, default=7000)
    ap.add_argument("--design-api", action="store_true", help="Design voices through the API (paid plans only)")
    ap.add_argument("--pick", action="append", default=[], help="Character=option, for example Navi=1")
    args = ap.parse_args()
    lines = load_lines()
    picks = {}
    for item in args.pick:
        name, value = item.rsplit("=", 1)
        if name not in CAST:
            sys.exit("Unknown character %s" % name)
        picks[name] = int(value)

    total = 0
    for name, c in CAST.items():
        chars = sum(len(lines[i]["text"]) for i, _ in c["lines"])
        total += chars * len(MODELS)
        print("%-24s %d lines, %d characters per model" % (name, len(c["lines"]), chars))
    print("text to generate: %d characters across %d models; cap %d credits" % (total, len(MODELS), args.max_credits))
    if args.dry_run:
        return

    key = api_key()
    os.makedirs(OUT, exist_ok=True)
    start, limit = used(key)
    print("account: %d of %d credits used" % (start, limit))
    # Free accounts cannot design voices through the API, so voices saved on the website are used by name.
    account = {v["name"].strip(): v["voice_id"] for v in call("GET", "/v1/voices", key)["voices"]}
    missing = ["OoT " + n for n in CAST if "OoT " + n not in account]
    if missing and not args.design_api:
        sys.exit("Nothing spent. Save these voices on the ElevenLabs website first: %s" % ", ".join(missing))
    available = limit - start
    if min(args.max_credits, available) < total:
        sys.exit("Stopping before spending anything: %d characters needed, %d allowed." % (total, min(args.max_credits, available)))

    state_path = os.path.join(OUT, "voices.json")
    state = json.load(open(state_path, encoding="utf-8")) if os.path.exists(state_path) else {}
    manifest = {}
    measured = {m: [0, 0] for m, _ in MODELS}
    measured_missing = []
    for name, c in CAST.items():
        folder = os.path.join(OUT, safe(name))
        os.makedirs(folder, exist_ok=True)
        entry = state.setdefault(name, {})
        web_voice = account.get("OoT " + name)
        if web_voice:
            entry.update(voice_id=web_voice, pick=0, previews=[])
        if "previews" not in entry:
            sample = " ".join(lines[i]["text"] for i, _ in c["lines"][:3])[:900]
            result = call("POST", "/v1/text-to-voice/design?output_format=mp3_44100_128", key, dict(voice_description=c["description"], model_id="eleven_ttv_v3", text=sample, seed=7))
            entry["previews"] = []
            for i, preview in enumerate(result["previews"]):
                with open(os.path.join(folder, "design_option_%d.mp3" % i), "wb") as g:
                    g.write(base64.b64decode(preview["audio_base_64"]))
                entry["previews"].append(preview["generated_voice_id"])
            json.dump(state, open(state_path, "w", encoding="utf-8"), indent=1)
            print("%s: %d design options" % (name, len(entry["previews"])))
        pick = 0 if web_voice else picks.get(name, entry.get("pick", 0))
        if entry.get("pick") != pick or "voice_id" not in entry:
            if "voice_id" in entry:
                call("DELETE", "/v1/voices/%s" % entry["voice_id"], key)
            created = call("POST", "/v1/text-to-voice", key, dict(voice_name="OoT test - " + name, voice_description=c["description"], generated_voice_id=entry["previews"][pick]))
            entry["voice_id"], entry["pick"] = created["voice_id"], pick
            entry["clips_for_pick"] = pick
            json.dump(state, open(state_path, "w", encoding="utf-8"), indent=1)
        rows = []
        for n, (line_id, tag) in enumerate(c["lines"]):
            text = lines[line_id]["text"]
            audio = {}
            for model, tagged in MODELS:
                file_name = "pick%d_%02d_%s.mp3" % (pick, n, model)
                path = os.path.join(folder, file_name)
                if not os.path.exists(path):
                    spent = sum(m[0] for m in measured.values())
                    if spent + 3 * len(text) > args.max_credits:
                        write_page(manifest)
                        sys.exit("Stopped at the %d credit cap after spending %d." % (args.max_credits, spent))
                    body = dict(text=(tag + " " + text) if tagged else text, model_id=model, seed=7, voice_settings=dict(stability=0.5))
                    if not tagged:
                        body["voice_settings"].update(similarity_boost=0.75)
                    clip = call("POST", "/v1/text-to-speech/%s?output_format=mp3_44100_128" % entry["voice_id"], key, body, raw=True)
                    if "character-cost" not in LAST_HEADERS:
                        measured_missing.append(file_name)
                    measured[model][0] += int(LAST_HEADERS.get("character-cost", 3 * len(body["text"])))
                    measured[model][1] += len(body["text"])
                    time.sleep(1.5)
                    with open(path, "wb") as g:
                        g.write(clip)
                audio[model] = "%s/%s" % (safe(name), file_name)
            rows.append(dict(text=("%s %s" % (tag, text)), audio=audio))
        manifest[name] = dict(pick=pick, clips=rows, previews=["%s/design_option_%d.mp3" % (safe(name), i) for i in range(len(entry["previews"]))])
        print("%s done, %d credits counted so far" % (name, sum(m[0] for m in measured.values())), flush=True)
    write_page(manifest)
    for model, (credits, chars) in measured.items():
        print("%s: %d credits for %d characters (%.2f per character)" % (model, credits, chars, credits / chars if chars else 0))
    if measured_missing:
        print("no cost header on %d clips; those were counted at 3 credits per character" % len(measured_missing))
    time.sleep(5)
    print("finished: %d credits spent; open %s" % (used(key)[0] - start, os.path.join(OUT, "index.html")))


if __name__ == "__main__":
    main()
