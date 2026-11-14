"""Speakers for lines the event data could not attribute: hand-read rules by file and label.

assign(row, flow_actor) returns {"slot", "text", "say"} or None when the line should stay silent.
"text" is what appears on screen (used for matching); "say" is what the voice reads.
"""
import re

NAVI = "Navi"
RUTO = "Npc_Zora_Ruto:Child"
ZELDA = "Npc_Hylia_Zelda:Child"
NARRATOR = "Narrator"
GERUDO_GUARD = "Crowd_Gerudo_W_Warrior"
POE, BIG_POE = "NPC_Poe_Voice", "NPC_Poe_Big_Voice"
COMMON_RACE = [("Npc_Zora", "Crowd_Zora_M"), ("Npc_Goron", "Crowd_Goron_M"), ("Npc_Gerudo", "Crowd_Gerudo_W"), ("Npc_Hylia_W", "Crowd_Hylia_W"),
               ("Npc_Hylia_M", "Crowd_Hylia_M"), ("Npc_Hylia_X", "Crowd_Hylia_X"), ("Npc_Hylia_Y", "Crowd_Hylia_Y"), ("Npc_Hylia_B", "Crowd_Hylia_B"),
               ("Npc_Hylia_G", "Crowd_Hylia_G"), ("Npc_Kokiri_GT", "Crowd_Kokiri_GT"), ("Npc_Kokiri", "Crowd_Kokiri_BT"),
               ("Npc_SkullKid", "Npc_SkullKid"), ("Npc_DekuTreeChild", "DekuTreeSprout")]

# (file, label pattern, voice); first match wins. A file with no rule stays silent.
RULES = [
    ("AllSage", "", NAVI), ("DoorOfTime", "", NAVI), ("NaviTips", "", NAVI), ("LinkSleepInBed", "", NAVI),
    ("HountedWasteland_Field_Restart", "", NAVI), ("Get_StoneOfForest", "", NAVI),
    ("HrlField_Note_00", "", NAVI),
    ("Animal_Cow", "^Talk_0[12]$", NAVI), ("Animal_Cow", "", "Animal_Cow"),
    ("Bottle_Event", "Talk_02", NARRATOR), ("Bottle_Event", "Talk_03", RUTO),
    ("Diary_Hylia_Dampe_Adult", "^Talk_0[1-4]$", "Npc_Hylia_Dampe_002"), ("Diary_Hylia_Dampe_Child", "^Talk_0[1-3]$", "Npc_Hylia_Dampe_001"),
    ("Diary_Hylia_Dampe_Adult", "", NAVI), ("Diary_Hylia_Dampe_Child", "", NAVI),
    ("Dm_DeathMtTrail_0025", "", NARRATOR), ("Dm_ZoraFountain_0030", "", NARRATOR), ("Dm_InsideJabu_Jabu_0030", "", NARRATOR),
    ("Item_Event", "", NARRATOR), ("StoneBirdStatue", "", NARRATOR),
    ("Dm_FairyFountain_Din", "", "Npc_GreatFairy_002"),
    ("Dm_Gerudo_0010", "", GERUDO_GUARD),
    ("Dm_Gerudo_0020", "_001[67]$", "Npc_Hylia_013"), ("Dm_Gerudo_0020", "_001[89]$", "Npc_Hylia_014"),
    ("Dm_Gerudo_0020", "_002[01]$", "Npc_Hylia_015"), ("Dm_Gerudo_0020", "_002[23]$", "Npc_Hylia_016"),
    ("Dm_HrlCastle_0050", "", ZELDA), ("Dm_InsideJabu_Jabu_0050", "", RUTO),
    ("Dm_MelodyGet_Epona", "", "Npc_Hylia_Malon:Child"), ("Dm_MelodyGet_Saria", "", "Npc_Kokiri_Saria"), ("Dm_MelodyGet_Zelda", "", ZELDA), ("Dm_MelodyGet_Time", "", ZELDA),
    ("Dm_MelodyGet_Sun", "", NAVI),
    ("Dm_MelodyGet_Fire", "", "Npc_Hylia_Sheik"), ("Dm_MelodyGet_Forest", "", "Npc_Hylia_Sheik"), ("Dm_MelodyGet_Shadow", "", "Npc_Hylia_Sheik"),
    ("Dm_MelodyGet_Shine", "", "Npc_Hylia_Sheik"), ("Dm_MelodyGet_Spilit", "", "Npc_Hylia_Sheik"), ("Dm_MelodyGet_Water", "", "Npc_Hylia_Sheik"),
    ("Dm_SY_Ocarina", "^Talk_104$", NAVI), ("Dm_SY_Ocarina", "^Talk_([3-9][0-9])$", "Npc_Kokiri_Saria"),
    ("Enemy_Event", "^Enemy_SkullKid", "Npc_SkullKid"), ("Enemy_Event", "^SharpFlat", "Obj_Spirit_PoeSharp"),
    ("Enemy_Event", "^PoeMask(_\\d\\d$|[012]_)", POE), ("Enemy_Event", "^PoeMask", BIG_POE),
    ("Enemy_Event", "^PoeSpiritNear|^Obj_Spirit_Poe", POE),
    ("Get_StoneOfFire", "^(PlayOcarina|Mask)", "Npc_Goron_Darunia"), ("Get_StoneOfFire", "", NAVI),
    ("Get_StoneOfWater", "_Ruto_", RUTO), ("Get_StoneOfWater", "_Talk_99", "Npc_Hylia_Impa"), ("Get_StoneOfWater", "", "Npc_Zora_KingZora"),
    ("MiniGame_Diving", "", "Npc_Zora_001"),
    ("MiniGame_Fishing", "^(Talk|Near|Mask|Terror)", "Npc_Hylia_Fishman_001"),
    ("MiniGame_HorseRace", "", "Npc_Hylia_Malon:Adult"),
    ("Minigame_CatchCucco", "", "Npc_Hylia_049"),
    ("Npc_Bonooru", "", "Npc_Bonooru"), ("Npc_Pierre", "", "Npc_Pierre"), ("Npc_SkullKid_Child_02", "", "Npc_SkullKid"),
    ("RestrictedDoor", "_Market_Navi_", NAVI), ("RestrictedDoor", "_Market_(01|10)$", "Npc_Hylia_022_Shop"), ("RestrictedDoor", "_Market_(02|12)$", "Npc_Hylia_020_Shop"),
    ("RestrictedDoor", "_Market_(03|14)$", "Npc_Hylia_019_Shop"), ("RestrictedDoor", "_Market_04$", "Npc_Hylia_023_Shop"),
    ("RestrictedDoor", "_Market_(05|17|19|20)$", "Npc_Hylia_018_Shop"), ("RestrictedDoor", "_Market_2[12]$", "Npc_Hylia_021_Shop"),
    ("RestrictedDoor", "_GerudoFortress_", GERUDO_GUARD), ("RestrictedDoor", "_Common_", "Crowd_Hylia_W"),
    ("SageOfFire", "^DungeonWarp", NAVI), ("SageOfFire", "", "Npc_Goron_DaruniaJr"),
    ("SageOfForest", "^(NaviRepeat|DungeonWarp)", NAVI), ("SageOfForest", "", "Npc_Kokiri_Mido"),
    ("SageOfShadow", "", NAVI),
    ("SageOfSpirit", "^(Talk_(19|20|22)$|DungeonWarp)", NAVI), ("SageOfSpirit", "", "Nabooru"),
    ("SageOfWater", "^Near_01$", "Npc_Zora_KingZora"), ("SageOfWater", "", NAVI),
    ("SubEvent_ForestStage", "", "Enemy_Scrub_ForestStage_Elder"),
]


def spoken_form(text):
    """Remove what a voice should not read aloud: stage directions, snores and diary date stamps."""
    text = re.sub(r"\*\w+\*|\bZzz\b\.*", " ", text)
    text = re.sub(r"Month [^,]+, Day \S", " ", text)
    return re.sub(r"\s+", " ", text.replace("・", " ")).strip().lstrip(". ")


def result(slot, text, say=None):
    say = spoken_form(say or text)
    if not re.search(r"[A-Za-z]{2}", say):
        return None
    return {"slot": slot, "text": text, "say": say}


def assign(row, flow_actor=None):
    file_name, label = row["id"].split("/", 1)[1].split(":", 1)
    text = row["text"]
    kind = row["kind"]
    if kind == "shared":
        for key, slot in COMMON_RACE:
            if key in label:
                return result(slot, text)
        return result("Crowd_Hylia_M", text)
    if file_name == "SignboardWood":
        # Only signs with something to read, not bare place names, arrows or the deliberately worn-away tomb plaques.
        if not re.search(r"[.!?]", text) or re.search("[←→↑↓]", text) or text.count("—") >= 3:
            return None
        shown = re.sub(r"([a-zé])([A-Z])", r"\1 \2", text)
        return result(NARRATOR, shown, re.sub(r"([a-zé])([A-Z])", r"\1. \2", text))
    if re.fullmatch(r"\d+", label):
        return None   # numbered labels are the player's menu choices
    if kind not in ("unassigned", "read_only", "system"):
        return None
    shown = re.sub(r"(Month [^,]+, Day \S)(?=\S)", r"\1 ", text)
    if flow_actor == "Npc_Navi":
        return result(NAVI, shown)
    for name, pattern, slot in RULES:
        if name == file_name and re.search(pattern, label):
            return result(slot, shown)
    return None
