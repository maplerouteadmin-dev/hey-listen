"""Build a Fritchii mod folder that makes the game play our clips as its own voice lines. Read-only on the .nup.

    py -3.14 -I build_voice_mod.py <file.nup> <manifest.json> <mod dir> [--files PREFIX ...] [--lang USen]

<mod dir> becomes <mod dir>/romfs/... ; point it at %APPDATA%/eden/load/0400486024DEC000/<Mod Name>.
Per message file (EventFlowMsg/X) it writes:
  Voice/Resource/<lang>_EventFlowMsg-_X.bars.zs        bank: one AMTA + BWAV header per voiced message
  Voice/Resource/Stream/<lang>_EventFlowMsg-_X--<label>.bwav   the audio (encoded by bwav_encode.py)
and patches Voice/VoiceSettingInfo (Resources: murmur3 of "EventFlowMsg/X" -> bank) and the resource size table.
Messages the game already voices keep their official clip.
"""
import argparse
import collections
import hashlib
import importlib.util
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import zlib
from compression import zstd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import boxes  # noqa: E402
import byml7  # noqa: E402
import split_messages  # noqa: E402

VENV_PYTHON = r"A:\OotVoiceMod\qwen\venv\Scripts\python.exe"
SETTINGS = "Voice/VoiceSettingInfo.Product.111.byml.zs"
RSTB = "System/Resource/ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs"
BANK_RSTB_OVERHEAD = 608      # official banks list file size + 588..608
STUB = 0x80
# A file this mod never writes to, used by installers to check the target game matches
# the dump this mod was built from (same bytes on disk whether the mod is installed or not).
FINGERPRINT_FILE = "Pack/ZsDic.pack.zs"


def murmur3_32(data, seed=0):
    c1, c2, m = 0xcc9e2d51, 0x1b873593, 0xffffffff
    rot = lambda x, k: ((x << k) | (x >> (32 - k))) & m
    h, n = seed, len(data)
    for i in range(0, n - n % 4, 4):
        k = struct.unpack_from("<I", data, i)[0] * c1 & m
        h ^= rot(k, 15) * c2 & m
        h = (rot(h, 13) * 5 + 0xe6546b64) & m
    tail, k = data[n - n % 4:], 0
    for j, b in enumerate(tail):
        k |= b << (8 * j)
    if tail:
        h ^= rot(k * c1 & m, 15) * c2 & m
    h ^= n
    h ^= h >> 16; h = h * 0x85ebca6b & m; h ^= h >> 13; h = h * 0xc2b2ae35 & m; h ^= h >> 16
    return h


# ---------- text boxes ----------

PAGE_TAG = re.compile(r"\{0:4:[0-9a-f]*\}")
ANY_TAG = re.compile(r"\{/?\d+:\d+:?[0-9a-f]*\}")
BOX_LINES = 2       # the text box shows two lines; a third starts a new box (the game's own PageBreak clips are 3-line messages)


def text_boxes(raw):
    """The visible text of each text box a message fills, in order."""
    boxes = []
    for page in PAGE_TAG.split(raw):
        lines = [ANY_TAG.sub("", l).strip() for l in page.split("\n")]
        for i in range(0, len(lines), BOX_LINES):
            text = " ".join(l for l in lines[i:i + BOX_LINES] if l)
            if text:
                boxes.append(text)
    return boxes


# ---------- BARS ----------

def parse_bars(d):
    """{name: (amta bytes, bwav stub bytes)}"""
    n = struct.unpack_from("<I", d, 12)[0]
    pairs = [struct.unpack_from("<II", d, 0x10 + 4 * n + 8 * i) for i in range(n)]
    out = {}
    for i, (ao, wo) in enumerate(pairs):
        size = struct.unpack_from("<I", d, ao + 8)[0]
        name_at = ao + 0x24 + struct.unpack_from("<I", d, ao + 0x24)[0]
        name = d[name_at:d.index(b"\0", name_at)].decode()
        stub_size = struct.unpack_from("<H", d, wo + 0xE)[0] * 0x4C + 0x10
        out[name] = (d[ao:ao + size], d[wo:wo + stub_size])
    return out


def make_amta(name, s):
    """One bank entry. Clips that read several text boxes get a "PageBreak" marker where each later box starts,
    laid out as in the game's own entries: u32 0, u32 count, then per marker (id, name offset from that field,
    sample position, length 0), then the marker names."""
    curve = s["curve"]
    breaks = s.get("breaks") or []
    head = bytearray(0x50)
    struct.pack_into("<4sHHIII", head, 0, b"AMTA", 0xFEFF, 0x0500, 0, 0, 0x34)
    raw_name = name.encode() + b"\0"
    body = bytearray(b"".join(struct.pack("<fI", v, p) for v, p in curve))
    if breaks:
        table_at = 0x50 + len(body) + 4
        struct.pack_into("<I", head, 0x14, table_at)
        body += struct.pack("<II", 0, len(breaks))
        entries_at = len(body)
        body += b"\0" * (16 * len(breaks))
        for i, pos in enumerate(breaks):
            text_at = len(body)
            field = entries_at + 16 * i + 4
            struct.pack_into("<IIII", body, entries_at + 16 * i, i, text_at - field, pos, 0)
            body += b"PageBreak\0"
    name_at = 0x50 + len(body)
    struct.pack_into("<III", head, 0x24, name_at - 0x24, zlib.crc32(name.encode()), 0x11)
    head[0x30:0x34] = bytes([1, 1, 0, 4])
    struct.pack_into("<I4fIHH", head, 0x34, 0x7F, s["peak"], s["rms"], s["db"], s["db2"], s["onset"], len(curve), 2)
    body = bytes(head) + bytes(body) + raw_name
    body += b"\0" * (-len(body) % 4)
    body = bytearray(body)
    struct.pack_into("<I", body, 8, len(body))
    return bytes(body)


def stub_from_stream(bwav):
    stub = bytearray(bwav[:0x5C])
    struct.pack_into("<I", stub, 0x1C, 0)       # a bank's copy holds no samples
    return bytes(stub)


def build_bars(entries):
    """entries: {name: (amta, stub)} -> BARS v1.2 bytes, laid out like the game's own."""
    items = sorted(entries.items(), key=lambda kv: zlib.crc32(kv[0].encode()))
    n = len(items)
    head = 0x10 + 12 * n
    amta_at = head + 4          # the game's banks leave 4 zero bytes after the offset table
    offsets, pos = [], amta_at
    for _, (amta, _) in items:
        offsets.append(pos)
        pos += len(amta)
    wav_at = pos + (-pos % 0x40)
    out = bytearray(wav_at)
    struct.pack_into("<4sIHHI", out, 0, b"BARS", 0, 0xFEFF, 0x0102, n)
    for i, (name, (amta, _)) in enumerate(items):
        struct.pack_into("<I", out, 0x10 + 4 * i, zlib.crc32(name.encode()))
        out[offsets[i]:offsets[i] + len(amta)] = amta
    for i, (_, (_, stub)) in enumerate(items):
        if i:
            out += b"\0" * (-len(out) % 0x40)
        struct.pack_into("<II", out, 0x10 + 4 * n + 8 * i, offsets[i], len(out))
        out += stub
    struct.pack_into("<I", out, 4, len(out))
    return bytes(out)


# ---------- resource size table ----------

def rstb_set(d, sizes):
    """sizes: {path without .zs: size}. Returns a new table with those entries added or raised."""
    ver, strsz, n, m = struct.unpack_from("<IIII", d, 6)
    table = dict(struct.unpack_from("<II", d, 22 + 8 * i) for i in range(n))
    names_at = 22 + 8 * n
    names = d[names_at:names_at + (strsz + 4) * m]
    named = {d[names_at + (strsz + 4) * i:names_at + (strsz + 4) * i + strsz].split(b"\0")[0].decode() for i in range(m)}
    for path, size in sizes.items():
        assert path not in named, "path lives in the name table: " + path
        crc = zlib.crc32(path.encode())
        table[crc] = max(table.get(crc, 0), size)
    body = b"".join(struct.pack("<II", c, s) for c, s in sorted(table.items()))
    return d[:6] + struct.pack("<IIII", ver, strsz, len(table), m) + body + names


# ---------- main ----------


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def zs_dict(data, dicts):
    """The dictionary a .zs file was compressed with, or None for plain zstd."""
    try:
        zstd.decompress(data)
        return None
    except zstd.ZstdError:
        pass
    return next(d for d in dicts.values() if _fits(data, d))


def write_zs(path, data, zdict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(zstd.compress(data, zstd_dict=zdict) if zdict else zstd.compress(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nup")
    ap.add_argument("manifest")
    ap.add_argument("mod")
    ap.add_argument("--lines", default=r"A:\OotVoiceMod\script\pack_boxes.jsonl", help="One line per text box (make_box_lines.py)")
    ap.add_argument("--full-lines", default=r"A:\OotVoiceMod\script\pack_full.jsonl", help="One line per message, for older whole-message clips")
    ap.add_argument("--line-table", default=r"A:\OotVoiceMod\script\line_table_USen.jsonl")
    ap.add_argument("--flow-links", default=r"A:\OotVoiceMod\script\flow_links.jsonl")
    ap.add_argument("--files", nargs="*", default=[], help="Only message files starting with these, e.g. EventFlowMsg/Npc_Kokiri_")
    ap.add_argument("--no-split", action="store_true", help="Never split messages into one per box")
    ap.add_argument("--joined", action="store_true", help="Voice multi-box messages that cannot be split with one joined clip (they replay at each box)")
    ap.add_argument("--lang", default="USen")
    args = ap.parse_args()

    spec = importlib.util.spec_from_file_location("x", os.path.join(HERE, "script_extract.py"))
    x = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(x)
    nup = x.Nup(args.nup)
    romfs = dict(nup.walk(nup.newest()["romfs"]))
    dicts = x.load_dicts(nup, list(romfs.items()))

    def original(path):
        return x.unzs(nup.read(romfs[path]), dicts)

    base = os.path.dirname(os.path.abspath(args.manifest))
    clip = {(c["slot"], c["text"]): os.path.join(base, c["path"]) for c in json.load(open(args.manifest, encoding="utf-8"))["clips"]}
    full = {r["id"]: r for r in load_jsonl(args.full_lines)}
    raw_text = {r["id"]: r["raw"] for r in load_jsonl(args.line_table)}
    links = collections.defaultdict(list)
    for r in load_jsonl(args.flow_links):
        links[r["message"]].append(r)

    def talk_only(mid):
        refs = links.get(mid, [])
        return bool(refs) and all(l["kind"] == "flow" and l.get("action") in split_messages.TALK_ACTIONS for l in refs)

    messages = {}
    for r in load_jsonl(args.lines):
        mid = r.get("message", r["id"])
        if not mid.startswith("EventFlowMsg/") or (args.files and not mid.startswith(tuple(args.files))):
            continue
        m = messages.setdefault(mid, dict(slot=r["voice_slot"], boxes=[]))
        m["boxes"].append((r.get("box", 1), r["id"], r["text"]))

    # Long messages that become one message per box: shown only by talk events, and every box voiced.
    want_split = {}
    for mid, m in messages.items():
        m["boxes"].sort()
        if len(m["boxes"]) < 2 or args.no_split or not talk_only(mid) or mid not in raw_text:
            continue
        if all(clip.get((m["slot"], t)) for _, _, t in m["boxes"]) and len(boxes.split(raw_text[mid])) == len(m["boxes"]):
            want_split[mid] = [i for _, i, _ in m["boxes"][1:]]
    # Check each flow that shows them really has those talk events, before changing anything.
    flows = collections.defaultdict(dict)
    for mid in want_split:
        for l in links[mid]:
            flows[l["flow"]][mid] = want_split[mid]
    found = collections.Counter()
    for flow in flows:
        path = "Event/EventFlow/%s.bfevfl.zs" % flow
        if path not in romfs:
            continue
        f = split_messages.Flow(original(path))
        for fc in f.flowcharts():
            for _, _, _, mid in f.talk_events(fc):
                if mid in want_split:
                    found[mid] += 1
    split = {mid: ids for mid, ids in want_split.items() if found[mid] == len(links[mid])}

    romfs_out = os.path.join(args.mod, "romfs")
    stream_dir = os.path.join(romfs_out, "Voice", "Resource", "Stream")
    os.makedirs(stream_dir, exist_ok=True)
    jobs = []
    counts = collections.Counter()

    def job(mid, **extra):
        msg_file, label = mid.split(":", 1)
        name = "%s_%s--%s" % (args.lang, msg_file.replace("/", "-_"), label)
        jobs.append(dict(out=os.path.join(stream_dir, name + ".bwav"), name=name, file=msg_file, **extra))

    for mid, m in messages.items():
        slot, bx = m["slot"], m["boxes"]
        if len(bx) == 1:
            wav = clip.get((slot, bx[0][2]))
            if wav:
                job(mid, wav=wav)
                counts["one box"] += 1
            continue
        parts = [clip.get((slot, t)) for _, _, t in bx]
        if mid in split:
            for (_, box_id, _), wav in zip(bx, parts):
                job(box_id, wav=wav)
            counts["split into boxes"] += 1
        elif talk_only(mid):
            counts["talk, waiting for box clips"] += 1    # silent until every box is voiced, so nothing repeats
        elif not args.joined:
            # Shown outside talk events (shops, cutscenes, code), so it cannot be split; the game restarts one
            # clip at every new box and the PageBreak markers have not stopped that, so the line plays twice.
            counts["multi-box outside talk, left silent"] += 1
        elif all(parts):
            job(mid, parts=parts)
            counts["joined, exact page breaks"] += 1
        else:
            whole = full.get(mid)
            wav = whole and clip.get((whole["voice_slot"], whole["text"]))
            if wav:
                job(mid, wav=wav, pages=[len(boxes.visible(b)) for b in boxes.split(raw_text.get(mid, ""))])
                counts["whole clip, estimated page breaks"] += 1
    if not jobs:
        sys.exit("no clips selected")

    with tempfile.TemporaryDirectory() as tmp:
        jobs_path, res_path = os.path.join(tmp, "jobs.json"), os.path.join(tmp, "results.json")
        json.dump(jobs, open(jobs_path, "w", encoding="utf-8"))
        print("encoding %d clips..." % len(jobs), flush=True)
        subprocess.run([VENV_PYTHON, "-I", os.path.join(HERE, "bwav_encode.py"), jobs_path, res_path], check=True)
        results = json.load(open(res_path, encoding="utf-8"))

    rstb_old = original(RSTB)
    ver, strsz, n, _ = struct.unpack_from("<IIII", rstb_old, 6)
    rstb_table = dict(struct.unpack_from("<II", rstb_old, 22 + 8 * i) for i in range(n))
    rstb_sizes = {}

    def grew(path, new_len):
        """Size-table entry for a replaced file: its old entry plus however much it grew."""
        key = path[:-3] if path.endswith(".zs") else path
        old = rstb_table.get(zlib.crc32(key.encode()))
        if old:
            rstb_sizes[key] = old + max(0, new_len - len(original(path))) + 256

    if split:
        # Box 1 stays under the old label; later boxes are new messages chained after it.
        mals = "Mals/%s.Product.110.sarc.zs" % args.lang
        info, files = split_messages.read_sarc(original(mals))
        by_msbt = collections.defaultdict(list)
        for mid in split:
            msg_file, label = mid.split(":", 1)
            by_msbt[msg_file + ".msbt"].append((label, boxes.split(raw_text[mid])))
        for name, edits in by_msbt.items():
            head, msgs = split_messages.read_msbt(files[name])
            index = {label: i for i, (label, _) in enumerate(msgs)}
            for label, parts in edits:
                msgs[index[label]] = (label, boxes.encode(parts[0]))
                for k, part in enumerate(parts[1:], 2):
                    msgs.append((label + boxes.SUFFIX % k, boxes.encode(part)))
            files[name] = split_messages.write_msbt(head, msgs)
        data = split_messages.write_sarc(info, files)
        write_zs(os.path.join(romfs_out, mals), data, zs_dict(nup.read(romfs[mals]), dicts))
        grew(mals, len(data))
        events = 0
        for flow, plan in flows.items():
            plan = {mid: ids for mid, ids in plan.items() if mid in split}
            path = "Event/EventFlow/%s.bfevfl.zs" % flow
            if not plan or path not in romfs:
                continue
            data, added = split_messages.split_flow(original(path), plan)
            if added:
                write_zs(os.path.join(romfs_out, path), data, zs_dict(nup.read(romfs[path]), dicts))
                grew(path, len(data))
                events += added
        print("split %d messages: %d message files, %d talk events added" % (len(split), len(by_msbt), events))

    settings = byml7.read(original(SETTINGS))
    resources = settings["Resources"]
    per_file = collections.defaultdict(dict)
    for r in results:
        per_file[r["file"]][r["name"]] = (make_amta(r["name"], r), stub_from_stream(open(r["out"], "rb").read()))
    official_kept = 0
    for msg_file, entries in per_file.items():
        bank_short = msg_file.replace("/", "-_")
        path = "Voice/Resource/%s_%s.bars.zs" % (args.lang, bank_short)
        if path in romfs:   # the game already voices some of this file: keep its clips
            for name, entry in parse_bars(original(path)).items():
                if name in entries:
                    os.remove(os.path.join(stream_dir, name + ".bwav"))
                    official_kept += 1
                entries[name] = entry
        data = build_bars(entries)
        write_zs(os.path.join(romfs_out, path), data, None)
        rstb_sizes[path[:-3]] = len(data) + BANK_RSTB_OVERHEAD
        key = murmur3_32(msg_file.encode())
        if bank_short not in resources.get(key, []):
            resources[key] = resources.get(key, []) + [bank_short]
    new_settings = byml7.write(settings)
    assert byml7.read(new_settings) == settings
    write_zs(os.path.join(romfs_out, SETTINGS), new_settings, zs_dict(nup.read(romfs[SETTINGS]), dicts))
    grew(SETTINGS, len(new_settings))
    write_zs(os.path.join(romfs_out, RSTB), rstb_set(rstb_old, rstb_sizes), None)

    title = nup.newest()
    mod_info = dict(
        game_id="%016X" % title["id"],
        game_version=title["version"],
        fingerprint_file=FINGERPRINT_FILE,
        fingerprint_sha256=hashlib.sha256(nup.read(romfs[FINGERPRINT_FILE])).hexdigest(),
    )
    json.dump(mod_info, open(os.path.join(args.mod, "mod_info.json"), "w", encoding="utf-8"), indent=1)

    print(", ".join("%s %d" % kv for kv in counts.items()))
    print("banks %d, clips %d, official clips kept %d -> %s" % (len(per_file), len(results) - official_kept, official_kept, romfs_out))


def _fits(data, d):
    try:
        zstd.decompress(data, zstd_dict=d)
        return True
    except zstd.ZstdError:
        return False


if __name__ == "__main__":
    main()
