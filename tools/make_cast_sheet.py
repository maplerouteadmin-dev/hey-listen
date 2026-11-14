"""Turn cast_data.json into the cast sheet and tag every line with its voice slot.

    python -I make_cast_sheet.py <script dir> <cast dir>

Voices are original designs: never imitate a real performer, including the game's own cast.
"""
import collections
import csv
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
script_dir, cast_dir = sys.argv[1:3]
cast = json.load(open(os.path.join(cast_dir, "cast_data.json"), encoding="utf-8"))
lines = [json.loads(l) for l in open(os.path.join(script_dir, "line_assignments.jsonl"), encoding="utf-8")]

# (voice, delivery, theme)
BRIEFS = {
    "Navi": ("Bright, small, airy young woman; high but not squeaky", "Quick and alert, urgent on warnings, fond under the nagging", "A glowing forest sprite: light, chiming, faint shimmer on the voice"),
    "Npc_Hylia_Malon:Child": ("Sweet, clear girl of about 10", "Sunny and unhurried, sing-song", "Ranch morning: warm, wholesome, a hint of folk-song lilt"),
    "Npc_Hylia_Malon:Adult": ("Warm young woman, clearly the same girl grown up", "Gentle, wistful, steady", "Ranch at dusk: a soft country warmth with quiet resilience"),
    "Npc_Hylia_Ingo": ("Reedy, nasal middle-aged man", "Sulky and grumbling, turns oily and shrill once he has power", "Resentful ranch hand: thin voice that strains when he blusters"),
    "Npc_Kokiri_Saria": ("Soft, gentle girl; older soul in a child's voice", "Patient, kind, quietly melancholy", "Forest meadow: airy, close, tender, like a song half-remembered"),
    "Npc_Hylia_049": ("Bright woman in her twenties", "Flustered and friendly, apologetic when she laughs", "Busy village life, a little breathless from chasing Cuccos"),
    "Npc_Hylia_Talon": ("Round, sleepy middle-aged man", "Slow and jolly, yawns through words, panics easily", "Ranch owner who would rather be napping: soft and plump-sounding"),
    "Npc_Hylia_Zelda:Child": ("Poised, articulate girl of about 10", "Earnest and formal, secretly anxious", "Royal courtyard: refined, clear, wise beyond her years"),
    "Npc_Hylia_Zelda:Adult": ("Composed, resonant young woman, same person grown", "Measured, sorrowful, regal", "Sage and princess: stately, luminous, slight sacred resonance"),
    "Npc_Hylia_Sheik": ("Low, androgynous, controlled young voice", "Terse and cool, every word weighed; a harp-like calm", "Shadowed Sheikah wanderer: close-miked, muffled by a face wrap"),
    "Npc_Zora_KingZora": ("Very deep, slow, plummy old man", "Ponderous, long pauses, pompous yet kind", "Vast, water-filled throne room: wet resonance and regal sluggishness"),
    "Npc_Kokiri_Mido": ("Bratty boy, pinched and loud", "Sneering, boastful, voice cracks when he loses face", "Self-appointed forest boss, small kid acting big"),
    "Npc_Kaepora": ("Elderly, sonorous, hooting male voice", "Long-winded professor, rising and falling in owl-like phrases", "Night forest owl: deep chest tone with a gentle hoot on phrase ends"),
    "Npc_Hylia_048": ("Hoarse, wheezing old man", "Greedy chuckle, leans in close, creepy-friendly", "Dusty ghost-trader's shop: dry, rasping, unsettling"),
    "Npc_Zora_Ruto:Child": ("Haughty, sharp little girl", "Imperious and sulky, softening when embarrassed", "Spoiled Zora princess: crisp with a watery lilt"),
    "Npc_Zora_Ruto:Adult": ("Elegant, confident young woman, same person grown", "Teasing, proud, warm beneath it", "Sage of Water: cool, flowing, gently reverberant"),
    "Npc_Hylia_012": ("Barrel-chested, booming foreman", "Bossy, blunt, proud of his work", "Dusty construction site: hearty and loud, used to shouting over hammers"),
    "Npc_Hylia_045": ("Papery, delighted old man", "Rambling, excitable, trails off into his own theories", "Eccentric lakeside scientist, slightly echoing laboratory"),
    "Npc_Goron_Darunia": ("Huge, gravelly, thunderous man", "Gruff and booming, big belly laugh, bursts of brotherly warmth", "Volcano chief: rock-deep rumble, heat and drums behind it"),
    "Npc_Hylia_Dampe_001": ("Croaky, raspy old man", "Mumbling and grim, sudden startling cackle", "Lonely gravedigger: dry, hollow, oddly endearing"),
    "Npc_Hylia_Dampe_002": ("Same croaky old man, now lighter and freer", "Teasing, playful, breathy", "A friendly ghost: airy with a spectral trail and soft echo"),
    "Npc_Hylia_023_Shop": ("Silky, theatrical man", "Honeyed and precise, smile audible, sudden cold menace", "Unnerving mask collector: intimate, too pleasant, smoothly wrong"),
    "Npc_Goron_Biggoron": ("Colossal, ultra-slow bass", "Drawn-out, drowsy, huge pauses", "Mountain-sized giant: sub-bass rumble with distant echo"),
    "Npc_Kokiri_Fado": ("Cheerful, sisterly girl", "Bouncy and quick, mock-stern scolding", "Sunny forest girl who looks after the other kids"),
    "Nabooru": ("Rich, confident contralto", "Wry, bold, relaxed swagger, fierce when roused", "Desert rebel thief: warm, sun-baked, dangerous charm"),
    "Enemy_Scrub_Business": ("Fast, wheedling, tinny man", "Salesman patter, ingratiating then snivelling", "Forest huckster speaking through a wooden snout"),
    "Enemy_Scrub_Deku": ("Small, squeaky, panicked voice", "Rapid and begging", "Wooden-snout nasal rasp, tiny and leafy"),
    "DekuTreeSprout": ("Bright, innocent small boy", "Eager, cheerful, a little formal", "New sapling: clean, green, faint woody warmth"),
    "GreatDekuTree": ("Ancient, slow, gentle bass", "Grandfatherly, patient, heavy with sorrow", "Giant living tree: creaking, deep hollow resonance"),
    "Npc_Hylia_Impa": ("Low, strong, weathered woman", "Blunt, disciplined, protective", "Sheikah guardian: firm, stoic, smoky warmth"),
    "Npc_SkullKid": ("Scratchy, impish child", "Mischievous giggle, jumpy, lonely underneath", "Lost Woods trickster: reedy, echoing between the trees"),
    "Rauru": ("Warm, wise elderly bass-baritone", "Calm, ceremonial, kindly", "Sage of Light in the Temple: wide sacred reverberation"),
    "Ganondorf": ("Commanding deep baritone", "Slow contempt and dark amusement", "Desert warlord: heavy, close, thunder at the edge"),
    "Koume": ("Cackling, shrill old woman with a hot edge", "Quick and gleeful, finishing Kotake's thoughts", "Fire witch: crackling, spitting energy"),
    "Kotake": ("Thin, hissing old woman with a cold edge", "Sly and needling, sing-song", "Ice witch: glassy, sibilant, chilled"),
    "Twinrova": ("Both witches layered in unison", "Gleeful, overlapping", "Fire and ice mixed: a hot voice and a cold voice as a duet"),
    "Narrator": ("Calm, storybook narrator", "Unhurried and reverent", "A legend being read aloud: warm, ancient, intimate"),
    "Npc_Goron_DaruniaJr": ("Small boy with a rocky rumble", "Excited hero-worship, shy", "A pint-sized Goron trying to sound like his father"),
    "Npc_Goron_Medigoron": ("Deep, gruff craftsman", "Short sentences, proud", "Hot forge: gritty and ringing"),
    "Npc_Pierre": ("Light, whimsical, sing-song man", "Theatrical and airy", "Wandering scarecrow musician, slightly hollow and rustling"),
    "Npc_Bonooru": ("Soft, straw-dry, kindly voice", "Dreamy, musical, slow", "Scarecrow in the fields: rustling and gentle"),
    "Npc_GuidePoe": ("Hollow, wavering ghostly man", "Slow, mournful, helpful", "Desert phantom: windblown, thin, echoing"),
    "Npc_Hylia_RunningMan": ("Lean, wiry, breathless man", "Quick and proud, always mid-stride", "Marathon runner: energetic, panting lightly"),
    "Npc_SkullDad": ("Rasping man forced through a curse", "Desperate, grateful, pained", "Cursed rich man: hollow, spidery, wet echo fading as he is healed"),
    "Npc_Hylia_014": ("Scruffy, boyish carpenter", "Lazy, teasing", "Carpenter crew member: laddish and dusty"),
    "Npc_Hylia_015": ("Scruffy, higher-pitched carpenter", "Earnest, excitable", "Carpenter crew member: eager and nervy"),
    "Npc_Hylia_016": ("Scruffy, dry-voiced carpenter", "Deadpan, slow", "Carpenter crew member: unimpressed"),
    "Npc_Hylia_013": ("Scruffy, loud carpenter", "Cocky, shouting", "Carpenter crew member: the loud one"),
    "Npc_Hylia_017": ("Whiny, entitled young man", "Sulking, petulant", "Spoiled son of a foreman"),
    "Npc_Hylia_020_Shop": ("Vain, sharp-tongued young man", "Condescending, then shrieks", "Conceited potion clerk"),
    "Npc_Hylia_019_Shop": ("Fussy, delicate man", "Nervy and precise", "Shooting-gallery operator who dislikes loud noises"),
    "Npc_Hylia_009": ("Mellow, musical older man", "Dreamy, grumbling when interrupted", "Windmill musician: droning and spinning"),
    "Npc_Zora_001": ("Clipped, cheerful coach", "Encouraging, brisk", "Zora diving instructor: bright and watery"),
    "GossipStone": ("Toneless, mineral whisper", "Flat, secretive", "Talking stone: granular, resonant, not quite human"),
    "Animal_Frog_Blue": ("Reedy, throaty baritone", "Mock-operatic croon", "Frog chorus member: bubbly and comical"),
    "Animal_Cow": ("Slow, sleepy, sweet voice", "Dozy and satisfied", "A contented cow"),
    "Npc_Dream": ("Faraway, distorted voices", "Slow and dreamlike", "A dream sequence, soft and swimming"),
    "Npc_Invisible_GerudoThief": ("Sharp woman's whisper", "Quick and furtive", "Unseen Gerudo thief in the dark"),
}
BRIEFS.update({
    "Obj_Spirit_PoeHyrule": ("Faint, wandering ghost", "Slow, sighing, sad", "Lost spirit: thin, windy, fading echo"),
    "Obj_Spirit_PoeFlat": ("Low, droning ghost brother", "Mournful and dragging", "Graveyard spirit tuned flat: heavy, sagging echo"),
    "Obj_Spirit_PoeSharp": ("High, keening ghost brother", "Nervy and strained", "Graveyard spirit tuned sharp: piercing, thin echo"),
    "NPC_Poe_Voice": ("Small, hollow ghost", "Short, sighing", "Field Poe: airy and echoing"),
    "NPC_Poe_Big_Voice": ("Large, hollow ghost", "Slow, groaning", "Big Poe: deep and cavernous"),
    "NpcSecurityGuard": ("Stiff adult man", "Formal, by-the-book", "Castle guard behind a helmet"),
    "Enemy_Scrub_Deku_Brothers": ("Three squeaky brothers, same family sound", "Rapid, tripping over each other", "Wooden-snout rasp, small and leafy"),
    "NPC_Scrub_Deku_TargetPractice": ("Small, squeaky, cocky voice", "Quick and challenging", "Wooden-snout rasp, small and leafy"),
    "Enemy_Scrub_ForestStage_Elder": ("Creaky old Deku voice", "Slow, stern, formal", "Forest stage elder: dry wooden creak"),
})
for i in range(1, 7):
    BRIEFS["Npc_GreatFairy_%03d" % i] = ("Huge, sensual, laughing woman", "Grand and teasing, sudden shrieks of laughter", "Great Fairy: fountain echo and cascading sparkle")

RACE = {
    "Hylia": "Hyrulean townsfolk: grounded, earthy, plain-spoken medieval",
    "Kokiri": "Forest child: light, airy and young, never adult-sounding",
    "Goron": "Goron: gravelly, deep-chested, hearty, rumbling rock under the voice",
    "Zora": "Zora: cool and fluid, soft consonants, faint watery resonance",
    "Gerudo": "Gerudo: confident, low and warm, desert-dry, commanding",
    "Poe": "Ghost: hollow, thin, echoing",
    "Scrub": "Deku: nasal wooden rasp, small and leafy",
}
AGE = [("Elderly_Man", "Elderly man"), ("Elderly_Woman", "Elderly woman"), ("MA_Man", "Middle-aged man"), ("MA_Woman", "Middle-aged woman"),
       ("Androgynous_Youth", "Androgynous youth"), ("Normal_Soldier", "Adult woman soldier"), ("Rookie_Soldier", "Young woman recruit"),
       ("Instructor", "Adult instructor"), ("Woman", "Adult woman"), ("Man", "Adult man"), ("Girl", "Young girl"), ("Boy", "Young boy")]
# The letters in crowd file names are read from Nintendo's naming, not stated anywhere, so they are marked as inferred.
CROWD = {"M": "Adult man", "W": "Adult woman", "B": "Young boy", "G": "Young girl", "BT": "Boy (timid or teen; inferred)", "GT": "Girl (timid or teen; inferred)",
         "X": "Older man (inferred)", "Y": "Older woman (inferred)", "M_Warrior": "Adult male fighter", "W_Warrior": "Adult female fighter"}


def race_of(key):
    for token, name in (("Hylia", "Hylia"), ("Kokiri", "Kokiri"), ("Goron", "Goron"), ("Zora", "Zora"), ("Gerudo", "Gerudo"), ("Poe", "Poe"), ("Scrub", "Scrub"), ("Skull", "Hylia")):
        if token in key:
            return name
    return ""


def split_name(words):
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", words)


def auto_brief(key, voice_type, display, nickname):
    race = race_of(key)
    base = "Unusual voice"
    m = re.match(r"Crowd_\w+?_(M_Warrior|W_Warrior|BT|GT|M|W|B|G|X|Y)$", key)
    if m:
        base = CROWD[m.group(1)]
    else:
        for token, label in AGE:
            if voice_type and token in voice_type:
                base = label
                break
    temperament = "steady and everyday"
    if voice_type and "Spry" in voice_type:
        temperament = "energetic and upbeat"
    elif voice_type and "Quiet" in voice_type:
        temperament = "soft-spoken and reserved"
    if "Soldier" in key or (voice_type and "Soldier" in voice_type):
        temperament += ", drilled and on-duty"
    if race == "Goron" and voice_type and "Boy" in voice_type:
        base = "Adult male Goron"   # Nintendo's Goron_Boy type also covers grown shopkeepers and guards
    who = display or (split_name(nickname) if nickname else None)
    return (base + (" (%s)" % who if who else ""), temperament.capitalize(), RACE.get(race, "Matches the character's role and setting"))


slots = []
slot_of = {}
for c in cast:
    multi = len(c["voice_types"]) > 1
    eras = [e for e in ("Child", "Adult") if multi and c["eras"].get(e)]
    for era in eras or [None]:
        slot = c["key"] + (":" + era if era else "")
        voice_type = None
        if c["voice_types"]:
            for vt in c["voice_types"]:
                if era is None or era in vt:
                    voice_type = vt
                    break
        brief = BRIEFS.get(slot)
        authored = brief is not None
        if not brief:
            brief = auto_brief(c["key"], voice_type, c["display"], c["nickname"])
        slots.append(dict(slot=slot, key=c["key"], era=era or "", display=c["display"] or (split_name(c["nickname"]) if c["nickname"] else ""), voice_type=voice_type or "",
                          voice=brief[0], delivery=brief[1], theme=brief[2], authored=authored, cues=", ".join(c["top_cues"][:4]), official_character=c["official"] > 0))
    slot_of[c["key"]] = (eras, c["key"])

missing = [k for k in BRIEFS if k not in {s["slot"] for s in slots}]
print("briefs that matched no character:", missing)

counts = collections.defaultdict(collections.Counter)
tagged = 0
with open(os.path.join(script_dir, "line_assignments.jsonl"), "w", encoding="utf-8") as out:
    for a in lines:
        a["voice_slot"] = None
        if a["kind"] == "spoken":
            eras, key = slot_of[a["character"]]
            era = a["era"] if a["era"] in eras else (eras[0] if eras else None)
            a["voice_slot"] = key + (":" + era if era else "")
            counts[a["voice_slot"]]["lines"] += 1
            counts[a["voice_slot"]]["official"] += a["voiced"]
            counts[a["voice_slot"]]["to_voice"] += not a["voiced"]
            counts[a["voice_slot"]][a["source"]] += 1
            tagged += 1
        out.write(json.dumps(a, ensure_ascii=False) + "\n")
for s in slots:
    n = counts[s["slot"]]
    s.update(lines=n["lines"], official=n["official"], to_voice=n["to_voice"])
    certain = n["speaker_field"] + n["talk_actor"]
    s["attribution"] = "confirmed" if n["lines"] and certain / n["lines"] >= 0.5 else ("crowd_file_inferred" if n["crowd_file"] else "file_name")
slots.sort(key=lambda s: -s["to_voice"])

with open(os.path.join(cast_dir, "cast_sheet.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["slot", "display", "era", "voice_type", "voice", "delivery", "theme", "lines", "official", "to_voice", "attribution", "authored", "official_character", "cues", "key"])
    w.writeheader()
    w.writerows(slots)

authored = [s for s in slots if s["authored"]]
with open(os.path.join(cast_dir, "cast_sheet.md"), "w", encoding="utf-8") as f:
    f.write("# Ocarina of Time voice cast\n\nVoices are original designs and never imitate a real performer. "
            "`To voice` is lines with no official audio. The full %d-voice cast is in `cast_sheet.csv`.\n\n" % len(slots))
    f.write("| Character | Voice | Delivery | Theme | To voice | Official |\n|---|---|---|---|--:|--:|\n")
    for s in authored:
        name = (s["display"] or s["key"]) + (" (%s)" % s["era"].lower() if s["era"] else "")
        f.write("| %s | %s | %s | %s | %d | %d |\n" % (name, s["voice"], s["delivery"], s["theme"], s["to_voice"], s["official"]))

print("voice slots", len(slots), "authored", len(authored), "auto", len(slots) - len(authored), "tagged lines", tagged)
print("lines to voice", sum(s["to_voice"] for s in slots), "official", sum(s["official"] for s in slots))
print("attribution", collections.Counter(s["attribution"] for s in slots), "lines:", {k: sum(s["to_voice"] for s in slots if s["attribution"] == k) for k in ("confirmed", "file_name", "crowd_file_inferred")})
print("chars", sum(len(a["text"]) for a in lines if a["voice_slot"] and not a["voiced"]))
print("split official/unvoiced slots", sum(1 for s in slots if s["official_character"] and s["to_voice"]), "their lines", sum(s["to_voice"] for s in slots if s["official_character"]))
print("no-type autos", [s["slot"] for s in slots if not s["authored"] and not s["voice_type"]][:30])
print("generic voice label", collections.Counter(s["voice"].split(" (")[0] for s in slots if not s["authored"]).most_common(20))
