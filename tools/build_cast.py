"""Assign every story line to one character and summarise the cast. Read-only on the .nup.

    python -I build_cast.py <script_extract.py> <file.nup> <script dir> <cast output dir>

Writes <script dir>/line_assignments.jsonl and <cast output dir>/cast_data.json.
Speaker order: the event's Speaker field, then the actor that performs the talk action, then the per-character file name.
"""
import collections
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
tool, nup_path, script_dir, cast_dir = sys.argv[1:5]
spec = importlib.util.spec_from_file_location("x", tool)
x = importlib.util.module_from_spec(spec)
spec.loader.exec_module(x)
nup = x.Nup(nup_path)
romfs = dict(nup.walk(nup.newest()["romfs"]))
dicts = x.load_dicts(nup, list(romfs.items()))

TALK_ACTIONS = {"EventTalk", "EventTalkIgnoreSameTalkAS", "EventPoeSpiritTalk", "EventTriggerBalloonMessage", "EventMiniGameDiggingHoleEntryBalloonMessage"}
NON_CHARACTER = {"SystemTextNPC"}
MERGE = {
    "Land_Kokiri_DekuTree_A_01": "GreatDekuTree", "Npc_DekuTreeChild": "DekuTreeSprout",
    "Enemy_DungeonBoss_Ganon_SecondHalfBattle": "Ganon", "Enemy_DungeonBoss_Ganon": "Ganon",
    "Enemy_DungeonBoss_Ganondorf": "Ganondorf", "Npc_Gerudo_Ganondorf": "Ganondorf",
    "Enemy_MiddleBoss_IronKnuckle_Nabooru": "Nabooru", "Npc_Gerudo_Nabooru": "Nabooru",
    "Npc_Hylia_Rauru_Ghost": "Rauru", "Npc_Hylia_Rauru": "Rauru",
    "Npc_KotakeKoume": "Twinrova", "Enemy_DungeonBoss_Twinrova": "Twinrova", "Enemy_DungeonBoss_Kotake": "Kotake", "Npc_Kotake": "Kotake",
    "Enemy_DungeonBoss_Koume": "Koume", "Npc_Koume": "Koume",
    "Enemy_DungeonBoss_PhantomGanon": "PhantomGanon", "Npc_Navi": "Navi", "Npc_Narrator": "Narrator",
    "Npc_Kaepora_DeathMountainTrail": "Npc_Kaepora", "Npc_SkullKid_Child_02": "Npc_SkullKid",
}
QUALIFIERS = re.compile(r"_(SacredForestMeadow|FireTemple|Kakariko|DeathMountainTrail|BottleShop)$")
ERA = re.compile(r"_(Child|Adult|child|adult)(?=_|$)")


def is_player(name):
    return name.startswith(("Player_", "Dm_Player"))


def canonical(name):
    """(character key, era) for an actor name."""
    name = re.sub(r"^Dm_", "", name)
    era = None
    m = ERA.search(name)
    if m:
        era = m.group(1).capitalize()
        name = name[:m.start()] + name[m.end():]
    name = QUALIFIERS.sub("", name)
    name = re.sub(r"_Ruto_001$", "_Ruto", name)
    name = re.sub(r"_Ingo_00\d$", "_Ingo", name)
    if name != "Npc_Invisible_GerudoThief":
        name = name.replace("Npc_Invisible_", "Npc_")
    name = re.sub(r"_(SecondTime|CallOcarina|LakeHylia|Voice)$", "", name) if not name.startswith("NPC_Poe") else name
    name = re.sub(r"_Event$", "", name) if name.startswith("Obj_Spirit") else name
    name = {"Npc_SkullKid_02": "Npc_SkullKid", "Npc_Zora_Ruto_002": "Npc_Zora_Ruto", "Enemy_Scrub_Business_Seed": "Enemy_Scrub_Business"}.get(name, name)
    return MERGE.get(name, name), era


FILE_RULES = [(r"^(NaviChat|NaviHint)", "Navi"), (r"^GossipStone", "GossipStone"), (r"^Enemy_Scrub", "Enemy_Scrub_Business"), (r"^HitTargetOfDekuScrub", "Enemy_Scrub_Deku")]
READ_ONLY = re.compile(r"^(Signboard|.*_Note_|Diary_|RestrictedDoor|LinkSleepInBed)")
LABEL_RULES = [(r"^Enemy_Scrub_Deku", "Enemy_Scrub_Deku"), (r"^Enemy_Scrub_Business", "Enemy_Scrub_Business")]

rows = [json.loads(l) for l in open(os.path.join(script_dir, "line_table_USen.jsonl"), encoding="utf-8")]
assign = []
stats = collections.Counter()
for r in rows:
    name = r["file"].split("/", 1)[1]
    speaker = source = None
    if r["speakers"]:
        speaker, source = r["speakers"][0], "speaker_field"
    elif r["actors"] and set(r["actions"]) & TALK_ACTIONS:
        speaker, source = r["actors"][0], "talk_actor"
    elif name.startswith("Npc_") or name.startswith("Npc"):
        speaker, source = name, "file_name"
    elif re.match(r"^NPC_(Hylia|Goron|Zora|Kokiri|Gerudo)_\w+$", name):
        speaker, source = name.replace("NPC_", "Crowd_", 1), "crowd_file"
    else:
        for pat, who in FILE_RULES:
            if re.match(pat, name):
                speaker, source = who, "file_rule"
                break
        if not speaker:
            for pat, who in LABEL_RULES:
                if re.match(pat, r["label"]):
                    speaker, source = who, "label_rule"
                    break
    if not r["text"]:
        kind = "empty"
    elif READ_ONLY.match(name):
        kind = "read_only"
    elif speaker and is_player(speaker):
        kind = "link_silent"
    elif speaker in NON_CHARACTER:
        kind = "system"
    elif speaker == "Npc_Common_Msg":
        kind = "shared"
    elif speaker:
        kind = "spoken"
    else:
        kind = "unassigned"
    key, era = canonical(speaker) if speaker and kind == "spoken" else (speaker, None)
    stats[kind] += 1
    stats["src:" + str(source)] += kind == "spoken"
    assign.append(dict(id=r["id"], character=key if kind == "spoken" else None, source_actor=speaker, era=era, source=source, kind=kind,
                       voiced=r["voiced"], cues=r["cues"], text=r["text"]))
with open(os.path.join(script_dir, "line_assignments.jsonl"), "w", encoding="utf-8") as g:
    for a in assign:
        g.write(json.dumps(a, ensure_ascii=False) + "\n")
print({k: v for k, v in stats.items()})

# Nintendo's voice type for every actor pack that declares one.
voice_types = {}
for path in romfs:
    if not (path.startswith("Pack/Actor/") and path.endswith(".pack.zs")):
        continue
    actor = path.split("/")[-1][:-8]
    if not actor.startswith(("Npc", "Dm_Npc", "Enemy_DungeonBoss", "Enemy_Scrub", "Land_Kokiri_DekuTree")):
        continue
    pack = x.parse_sarc(x.unzs(nup.read(romfs[path]), dicts))
    own = None
    for name, data in pack.items():
        if name.startswith("Component/VoiceParam/"):
            data = x.unzs(data, dicts)
            m = re.search(rb"Voice/VoiceTypeInfo/([\w.-]+?)\.game__sound", data)
            if m:
                stem = name.split("/")[-1].split(".")[0]
                if stem == actor or own is None or stem == actor.replace("_Adult", "_Child"):
                    own = m.group(1).decode()
    if own:
        voice_types[actor] = own
print("actors with voice types", len(voice_types))

names = {}
for line in open(os.path.join(script_dir, "script_USen.jsonl"), encoding="utf-8"):
    r = json.loads(line)
    if r["file"].startswith("ActorMsg/") and r["label"].endswith("_Name"):
        names[r["label"][:-5]] = re.sub(r"\{/?\d+:\d+:?[0-9a-f]*\}", "", r["text"])

cast = {}
for a in assign:
    if a["kind"] != "spoken":
        continue
    c = cast.setdefault(a["character"], dict(key=a["character"], actors=collections.Counter(), eras=collections.Counter(), lines=0, official=0, to_voice=0, cues=collections.Counter(), samples=[]))
    c["lines"] += 1
    c["official"] += a["voiced"]
    c["to_voice"] += not a["voiced"]
    c["actors"][a["source_actor"]] += 1
    c["eras"][a["era"] or "-"] += 1
    c["cues"].update(re.sub(r"(_\d+)$", "", q) for q in a["cues"])
    c.setdefault("nick", collections.Counter()).update(q.split("_")[0] for q in a["cues"] if "_" in q and not re.match(r"^(Talk|Question|Surprise|Laugh|Think|Sad|Happy|Notice|Greeting|Attention|Angry|Hungry)", q) and not q.split("_")[1].isdigit())
    if len(c["samples"]) < 6 and 20 < len(a["text"]) < 170 and "<" not in a["text"]:
        c["samples"].append(a["text"])

all_actors = set(voice_types)
for c in cast.values():
    types = collections.Counter()
    display = None
    for actor, n in c["actors"].items():
        for candidate in (actor, re.sub(r"^Dm_", "", actor), QUALIFIERS.sub("", actor), actor.replace("Npc_Zora_KingZora_child", "Npc_Zora_KingZora_child")):
            if candidate in voice_types:
                types[voice_types[candidate]] += n
                break
        else:
            stem = ERA.sub("", re.sub(r"^Dm_", "", actor))
            for a2 in sorted(all_actors):
                if ERA.sub("", a2) == stem:
                    types[voice_types[a2]] += n
                    break
        for candidate in (actor, re.sub(r"^Dm_", "", actor), QUALIFIERS.sub("", actor)):
            display = display or names.get(candidate)
    c["voice_types"] = dict(types)
    c["display"] = display
    c["top_cues"] = [k for k, _ in c["cues"].most_common(5)]
    nick = c.pop("nick", None)
    c["nickname"] = nick.most_common(1)[0][0] if nick else None
    c["actors"] = dict(c["actors"])
    c["eras"] = dict(c["eras"])
    del c["cues"]

ordered = sorted(cast.values(), key=lambda c: -c["lines"])
os.makedirs(cast_dir, exist_ok=True)
json.dump(ordered, open(os.path.join(cast_dir, "cast_data.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("characters", len(ordered), "spoken", sum(c["lines"] for c in ordered), "to voice", sum(c["to_voice"] for c in ordered), "chars still needing type", sum(not c["voice_types"] for c in ordered))
print("voice type families", collections.Counter(re.sub(r"_?\d+$", "", next(iter(c["voice_types"]))) for c in ordered if c["voice_types"]).most_common(40))
print("no voice type:", [(c["key"], c["lines"]) for c in ordered if not c["voice_types"]][:45])
print("multi type:", [(c["key"], c["voice_types"]) for c in ordered if len(c["voice_types"]) > 1][:30])
print("kinds", collections.Counter(a["kind"] for a in assign))
print("keys", [c["key"] for c in ordered])
print("nicknames", {c["key"]: c["nickname"] for c in ordered if c["nickname"] and not c["display"]})
split = [(c["key"], c["official"], c["to_voice"]) for c in ordered if c["official"]]
print("officially voiced characters", len(split), "their unvoiced lines", sum(s[2] for s in split), split)
fully_silent = [c for c in ordered if not c["official"]]
print("characters with no official voice", len(fully_silent), "lines", sum(c["to_voice"] for c in fully_silent))
# How often does a per-character file name agree with an event flow that names the actor directly?
agree = mismatch = 0
wrong = collections.Counter()
for r, a in zip(rows, assign):
    file_name = r["file"].split("/", 1)[1]
    if file_name.startswith("Npc_") and a["source"] == "talk_actor":
        if canonical(file_name)[0] == canonical(a["source_actor"])[0]:
            agree += 1
        else:
            mismatch += 1
            wrong[(file_name, a["source_actor"])] += 1
print("file name vs flow actor: agree", agree, "differ", mismatch, wrong.most_common(14))
unassigned = collections.Counter(a["id"].split(":")[0].split("/")[1] for a in assign if a["kind"] == "unassigned")
print("unassigned files", unassigned.most_common(50))
