"""Join script text, event flows and official voice banks into one table. Read-only on the .nup.

    python -I build_line_table.py <script_extract.py> <file.nup> <script dir> [--lang USen]

Writes <script dir>/line_table_<lang>.jsonl (one message per line) and flow_links.jsonl (raw message references).
"""
import argparse
import collections
import importlib.util
import json
import os
import re
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ap = argparse.ArgumentParser()
ap.add_argument("tool")
ap.add_argument("nup")
ap.add_argument("out")
ap.add_argument("--lang", default="USen")
args = ap.parse_args()
spec = importlib.util.spec_from_file_location("x", args.tool)
x = importlib.util.module_from_spec(spec)
spec.loader.exec_module(x)
nup = x.Nup(args.nup)
romfs = dict(nup.walk(nup.newest()["romfs"]))
dicts = x.load_dicts(nup, list(romfs.items()))

SYSTEM_ACTORS = {"GameSystemActor", "EventSystemActor", "GameDataActor", "UISystemActor", "EventCamera", "PostProcessingActor",
                 "VoicePlayActor", "Npc_EventStarter", "EventWorldManagerController", "Player_Event", ""}


class Flow:
    def __init__(self, data):
        self.b = data

    def q(self, at):
        return struct.unpack_from("<Q", self.b, at)[0]

    def h(self, at):
        return struct.unpack_from("<H", self.b, at)[0]

    def s(self, at):
        b = self.b
        if at <= 0 or at + 2 >= len(b):
            return None
        n = self.h(at)
        if n > 512 or at + 2 + n >= len(b) or b[at + 2 + n] != 0:
            return None
        try:
            return b[at + 2:at + 2 + n].decode("utf-8")
        except UnicodeDecodeError:
            return None

    def dic_names(self, dic):
        if dic <= 0 or self.b[dic:dic + 4] != b"DIC ":
            return []
        count = struct.unpack_from("<I", self.b, dic + 4)[0]
        return [self.s(self.q(dic + 0x18 + i * 0x10 + 8)) for i in range(count)]

    def item_value(self, item):
        kind = self.b[item]
        if kind == 5:
            return self.s(self.q(item + 0x10))
        if kind == 2:
            return struct.unpack_from("<i", self.b, item + 0x10)[0]
        if kind == 3:
            return bool(struct.unpack_from("<i", self.b, item + 0x10)[0])
        if kind == 4:
            return round(struct.unpack_from("<f", self.b, item + 0x10)[0], 3)
        return None

    def container(self, at):
        """{param name: value}"""
        if at <= 0 or at + 0x10 >= len(self.b) or self.b[at] != 1:
            return {}
        count = self.h(at + 2)
        names = self.dic_names(self.q(at + 8))
        out = {}
        for i in range(min(count, len(names))):
            out[names[i]] = self.item_value(self.q(at + 0x10 + i * 8))
        return out

    def action_names(self, actor_at):
        table, count = self.q(actor_at + 0x18), self.h(actor_at + 0x30)
        for stride in (0x10, 8, 0x18):
            names = [self.s(self.q(table + i * stride)) for i in range(count)]
            if count and all(names):
                return names
        return [None] * count

    def links(self):
        """Every (message id, speaker param, actor, action) in the file."""
        found = []
        num_flow, num_time = self.h(0x20), self.h(0x22)
        if num_flow:
            flow = self.q(self.q(0x28))
            actors_at, events_at = self.q(flow + 0x28), self.q(flow + 0x30)
            actor_names = [self.s(self.q(actors_at + i * 0x38)) for i in range(self.h(flow + 0x10))]
            actions = [self.action_names(actors_at + i * 0x38) for i in range(len(actor_names))]
            for i in range(self.h(flow + 0x16)):
                ev = events_at + i * 0x30
                if self.b[ev + 8] != 0:
                    continue
                actor, action = self.h(ev + 0xC), self.h(ev + 0xE)
                params = self.container(self.q(ev + 0x10))
                message = next((v for v in params.values() if isinstance(v, str) and v.startswith(("EventFlowMsg/", "NpcTerrorMsg/"))), None)
                if message:
                    name = actor_names[actor] if actor < len(actor_names) else None
                    act = actions[actor][action] if actor < len(actions) and action < len(actions[actor]) else None
                    found.append(dict(message=message, speaker=params.get("Speaker"), actor=name, action=act, kind="flow"))
        if num_time:
            refs = collections.defaultdict(list)
            for at in range(0, len(self.b) - 8, 8):
                refs[self.q(at)].append(at)
            for at in range(0, len(self.b) - 8, 8):
                target = self.q(at)
                text = self.s(target) if 0 < target < len(self.b) else None
                if not text or not text.startswith(("EventFlowMsg/", "NpcTerrorMsg/")):
                    continue
                item = at - 0x10
                for slot in refs.get(item, []):
                    for back in range(0, 0x100, 8):
                        c = slot - 0x10 - back
                        if c >= 0 and self.b[c] == 1 and self.h(c + 2) > back // 8 and self.q(c + 8) and self.b[self.q(c + 8):self.q(c + 8) + 4] == b"DIC ":
                            params = self.container(c)
                            if params.get("MessageId") == text:
                                found.append(dict(message=text, speaker=params.get("Speaker"), actor=None, action=None, kind="timeline",
                                                  show_name=params.get("IsShowingSpeakerName")))
                            break
        return found


links = collections.defaultdict(list)
flows = [p for p in romfs if p.startswith("Event/EventFlow/") and p.endswith(".bfevfl.zs")]
failed = 0
with open(os.path.join(args.out, "flow_links.jsonl"), "w", encoding="utf-8") as raw:
    for path in flows:
        try:
            found = Flow(x.unzs(nup.read(romfs[path]), dicts)).links()
        except (struct.error, IndexError) as error:
            failed += 1
            print("failed", path, error)
            continue
        flow_name = path.split("/")[-1].split(".")[0]
        for link in found:
            link["flow"] = flow_name
            links[link["message"]].append(link)
            raw.write(json.dumps(link, ensure_ascii=False) + "\n")
print("flows", len(flows), "failed", failed, "distinct messages referenced", len(links))

voiced = set()
pattern = re.compile(rb"%s_([A-Za-z]+)-_?([\w-]+?)--([\w]+)" % args.lang.encode())
for path in romfs:
    if path.startswith("Voice/Resource/%s_" % args.lang):
        for m in pattern.finditer(x.unzs(nup.read(romfs[path]), dicts)):
            group, name, label = m.group(1).decode(), m.group(2).decode(), m.group(3).decode()
            voiced.add("%s/%s:%s" % (group, name.replace("-", "/"), label))
print("official voice clips", len(voiced), "sample", sorted(voiced)[:3])

cue_re = re.compile(r"\{4:0:([0-9a-f]+)\}")
var_re = re.compile(r"\{2:\d+:([0-9a-f]*)\}")
any_tag = re.compile(r"\{/?\d+:\d+:?[0-9a-f]*\}")


def clean(text):
    def var(m):
        raw = bytes.fromhex(m.group(1))
        if len(raw) >= 2:
            n = struct.unpack_from("<H", raw)[0]
            return "<%s>" % raw[2:2 + n].decode("utf-8", "replace")
        return "<var>"

    plain = var_re.sub(var, text)
    plain = any_tag.sub("", plain)
    # A page break is only a tag, so sentences on either side of one touch once it is removed.
    plain = re.sub(r"([.!?…\"])([A-Z])", r"\1 \2", plain)
    return re.sub(r"\s+", " ", plain).strip()


def cues(text):
    out = []
    for hexed in cue_re.findall(text):
        name = x.tag_name(hexed)
        if name:
            out.append(name)
    return out


table = os.path.join(args.out, "line_table_%s.jsonl" % args.lang)
src = os.path.join(args.out, "script_%s.jsonl" % args.lang)
count = collections.Counter()
with open(table, "w", encoding="utf-8") as out, open(src, encoding="utf-8") as lines:
    for line in lines:
        row = json.loads(line)
        if not row["file"].startswith(("EventFlowMsg/", "NpcTerrorMsg/")):
            continue
        message = row["file"][:-5] + ":" + row["label"]
        found = links.get(message, [])
        rec = dict(id=message, file=row["file"][:-5], label=row["label"], text=clean(row["text"]), raw=row["text"], cues=cues(row["text"]),
                   voiced=message in voiced,
                   speakers=sorted({l["speaker"] for l in found if isinstance(l.get("speaker"), str) and l["speaker"]}),
                   actors=sorted({l["actor"] for l in found if l.get("actor") and l["actor"] not in SYSTEM_ACTORS}),
                   actions=sorted({l["action"] for l in found if l.get("action")}),
                   flows=sorted({l["flow"] for l in found}))
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        count["lines"] += 1
        count["voiced"] += rec["voiced"]
        count["has_flow"] += bool(found)
        count["has_speaker"] += bool(rec["speakers"])
        count["has_actor"] += bool(rec["actors"])
        count["empty"] += not rec["text"]
print(dict(count), "->", table)
