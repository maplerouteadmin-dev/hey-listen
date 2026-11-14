"""Select the lines a player will meet after clearing the Deku Tree, as a child, in rough story order.

    python -I story_scope.py [--write]

--write saves A:/OotVoiceMod/script/pack_child.jsonl (one line per clip to generate).
Adult-only content stays out so the first pack is small enough to finish quickly.
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from assign_leftovers import assign

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LINES = r"A:\OotVoiceMod\script\line_assignments.jsonl"
LINKS = r"A:\OotVoiceMod\script\flow_links.jsonl"
FULL = "--full" in sys.argv   # include the adult era, after all child content
OUT = r"A:\OotVoiceMod\script\pack_full.jsonl" if FULL else r"A:\OotVoiceMod\script\pack_child.jsonl"

ADULT_SCENE = re.compile(r"^Dm_(ForestTemple|FireTemple|WaterTemple|ShadowTemple|SpiritTemple|SageRoom|Awake|FinalBattle|InsideGanonCastle|Ending|DesertColossus|Gerudo|MelodyGet_(Forest|Fire|Water|Shadow|Spilit|Shine))")
ADULT_NAMES = re.compile(r"_Adult|_adult")
ADULT_FILES = re.compile(r"^(SageOf|Get_StoneOf$|AllSage|Enemy_Scrub_Business_Dream)")
ORDER = [(r"^Dm_Kokiri|^Npc_Kokiri|^Npc_DekuTree", "1 Kokiri Forest"), (r"^NaviChat|^NaviHint|^NaviTips|^GossipStone", "2 Navi and Gossip Stones"),
         (r"^Dm_LostWood|^Npc_SkullKid|^Npc_Kaepora|^Dm_HrlField", "3 Lost Woods and Hyrule Field"), (r"^Dm_LonLon|Malon|Talon|Ingo", "4 Lon Lon Ranch"),
         (r"^Dm_HrlCastle|Zelda|Impa|Npc_Hylia_Soldier", "5 Hyrule Castle"), (r"^Npc_Hylia_", "6 Castle Town and Kakariko"),
         (r"^Dm_Goron|^Dm_DeathMt|^Dm_Dodongo|^Npc_Goron|Get_StoneOfFire", "7 Goron City"), (r"^Dm_Zora|^Dm_InsideJabu|^Npc_Zora|Get_StoneOfWater", "8 Zora's Domain")]


STORY_FILE = re.compile(r"^(Dm_(?!SY_)|Get_Stone|SageOf|AllSage|DoorOfTime)")
STORY_CAST = {"Navi", "Npc_Kokiri_Saria", "Npc_Kokiri_Mido", "GreatDekuTree", "DekuTreeSprout", "Npc_Kaepora", "Npc_Hylia_Zelda:Child", "Npc_Hylia_Zelda:Adult", "Npc_Hylia_Impa",
              "Npc_Hylia_Sheik", "Rauru", "Nabooru", "Ganondorf", "Koume", "Kotake", "Twinrova", "Npc_Goron_Darunia", "Npc_Goron_DaruniaJr", "Npc_Goron_Biggoron", "Npc_Zora_KingZora",
              "Npc_Zora_Ruto:Child", "Npc_Zora_Ruto:Adult", "Npc_Hylia_Malon:Child", "Npc_Hylia_Malon:Adult", "Npc_Hylia_Talon", "Npc_Hylia_Ingo", "Npc_SkullKid", "Narrator"}
OPTIONAL_LABEL = re.compile(r"^(Mask|Near|Terror|Fear|PlayOcarina|SongOfTheStorm)|_Mask|_Near|Repeat|Amiibo", re.I)
SIDE_FILE = re.compile(r"^(MiniGame|Minigame|SubEvent|Enemy_|Animal_|SignboardWood|HrlField_Note|RestrictedDoor|Diary_|Item_Event|Npc_Common|LinkSleepInBed|Bottle_Event)")


def is_story(row, file_name):
    """Scenes the plot passes through, and what its key characters say outside optional reactions."""
    label = row["id"].split(":", 1)[1]
    if OPTIONAL_LABEL.search(label) or SIDE_FILE.match(file_name):
        return False
    return bool(STORY_FILE.match(file_name)) or row["voice_slot"] in STORY_CAST


def area(file_name):
    for pattern, label in ORDER:
        if re.search(pattern, file_name):
            return label
    return "9 Everything else"


def main():
    pack = []
    skipped = collections.Counter()
    flow_actor = {}
    with open(LINKS, encoding="utf-8") as f:
        for line in f:
            link = json.loads(line)
            if link["actor"]:
                flow_actor.setdefault(link["message"], link["actor"])
    with open(LINES, encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            if FULL and a["kind"] in ("unassigned", "read_only", "system", "shared"):
                # These still have no speaker in the event data, so the hand-read rules decide.
                found = assign(a, flow_actor.get(a["id"]))
                if not found:
                    skipped["silent: menu choice, UI or sign title"] += 1
                    continue
                a.update(voice_slot=found["slot"], text=found["text"], say=found["say"], kind="spoken", voiced=False)
                skipped["recovered"] += 1
            if a["kind"] != "spoken" or a["voiced"] or not a["voice_slot"]:
                continue
            file_name = a["id"].split("/", 1)[1].split(":")[0]
            adult = a["era"] == "Adult" or ADULT_NAMES.search(file_name) or ADULT_SCENE.match(file_name) or ADULT_FILES.match(file_name)
            if adult and not FULL:
                skipped["adult"] += 1
                continue
            if not re.search("[A-Za-z]", a["text"]) or "<" in a["text"]:
                skipped["silent or has a variable"] += 1
                continue
            a["area"] = "A Adult era" if adult else area(file_name)
            if FULL and a["area"][0] in "6789A" and is_story(a, file_name):
                # Sorts straight after area 5, so the story comes before side characters.
                a["area"] = "5T Main story, adult era" if adult else "5S Main story, child era"
            pack.append(a)
    pack.sort(key=lambda a: (a["area"], a["voice_slot"], a["id"]))
    total = sum(len(a["text"]) for a in pack)
    print("lines %d, characters %d, voices %d, skipped %s" % (len(pack), total, len({a["voice_slot"] for a in pack}), dict(skipped)))
    by_area = collections.defaultdict(lambda: [0, 0, set()])
    for a in pack:
        row = by_area[a["area"]]
        row[0] += 1
        row[1] += len(a["text"])
        row[2].add(a["voice_slot"])
    for key in sorted(by_area):
        print("%-30s %5d lines %7d chars %3d voices" % (key, by_area[key][0], by_area[key][1], len(by_area[key][2])))
    if "--write" in sys.argv:
        with open(OUT, "w", encoding="utf-8") as g:
            for a in pack:
                g.write(json.dumps(a, ensure_ascii=False) + "\n")
        print("wrote", OUT)


if __name__ == "__main__":
    main()
