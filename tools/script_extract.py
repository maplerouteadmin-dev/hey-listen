"""Pull the dialogue script out of an Ocarina of Time (Switch 2) .nup, read-only.

    python -I script_extract.py survey  <file.nup>
    python -I script_extract.py extract <file.nup> <output dir> [--lang USen]

Nothing in the .nup is changed. Output: <output dir>/msbt/<archive path>, and script_<lang>.jsonl with one line per message.
.nup layout credit: Hookshot's nx2/nup.py. Needs Python 3.14 (compression.zstd).
"""
import argparse
import collections
import json
import os
import struct
import sys
from compression import zstd

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


class Nup:
    def __init__(self, path):
        self.f = open(path, "rb")
        head = self.f.read(0x80)
        if head[:4] != b"NUP\x01":
            sys.exit("not a NUP package")
        toc = self.f.read(0x30)
        if toc[:4] != b"TOC\x01":
            sys.exit("no TOC")
        title_count, self.dir_count, self.file_count, strings_off, strings_size = struct.unpack_from("<IQQQQ", toc, 4)
        dirs_at = 0x80 + 0x30 + 0x40 * title_count
        files_at = dirs_at + 24 * self.dir_count
        kids_at = files_at + 80 * self.file_count
        strings_at = 0x80 + strings_off
        self.f.seek(0)
        meta = self.f.read(strings_at + strings_size)
        self.strings = meta[strings_at:strings_at + strings_size]
        self.titles = []
        for i in range(title_count):
            tid, root, exefs, romfs, version = struct.unpack_from("<QIIII", meta, 0xb0 + 0x40 * i)
            self.titles.append(dict(id=tid, root=root, exefs=exefs, romfs=romfs, version=version))
        self.dirs = [struct.unpack_from("<4I", meta, dirs_at + 24 * i) for i in range(self.dir_count)]
        self.files = []
        for i in range(self.file_count):
            at = files_at + 80 * i
            name_off, name_len, size, data_off, stored = struct.unpack_from("<IIQQQ", meta, at)
            self.files.append((name_off, name_len, size, data_off, stored, meta[at + 64]))
        self.kids = struct.unpack_from("<%dI" % ((strings_at - kids_at) // 4), meta, kids_at)

    def name(self, off, length):
        return self.strings[off:off + length].decode("utf-8")

    def walk(self, directory, prefix=""):
        _, _, first, count = self.dirs[directory]
        for kid in self.kids[first:first + count]:
            if kid < self.dir_count:
                yield from self.walk(kid, prefix + self.name(*self.dirs[kid][:2]) + "/")
            else:
                record = self.files[kid - self.dir_count]
                yield prefix + self.name(record[0], record[1]), record

    def newest(self):
        return max(self.titles, key=lambda t: t["version"])

    def read(self, record):
        """The file as the game sees it (a .zs file stays zstd)."""
        self.f.seek(record[3])
        if record[5] == 1:
            return zstd.decompress(self.f.read(record[4]))
        return self.f.read(record[2])


def parse_sarc(data):
    if data[:4] != b"SARC":
        sys.exit("not a SARC")
    header_size = struct.unpack_from("<H", data, 4)[0]
    data_at = struct.unpack_from("<I", data, 0xC)[0]
    count = struct.unpack_from("<H", data, header_size + 6)[0]
    nodes = header_size + 0xC
    names = nodes + 16 * count + 8
    files = {}
    for i in range(count):
        _, attrs, start, end = struct.unpack_from("<4I", data, nodes + 16 * i)
        if attrs & 0x01000000:
            at = names + (attrs & 0xFFFF) * 4
            name = data[at:data.index(b"\0", at)].decode("utf-8")
        else:
            name = "(unnamed %d)" % i
        files[name] = data[data_at + start:data_at + end]
    return files


def load_dicts(nup_file, romfs):
    for path, record in romfs:
        if path == "Pack/ZsDic.pack.zs":
            sarc = parse_sarc(zstd.decompress(nup_file.read(record)))
            return {n: zstd.ZstdDict(d) for n, d in sarc.items() if n.endswith(".zsdic")}
    sys.exit("no Pack/ZsDic.pack.zs")


def unzs(data, dicts):
    if data[:4] != ZSTD_MAGIC:
        return data
    try:
        return zstd.decompress(data)
    except zstd.ZstdError:
        pass
    for candidate in dicts.values():
        try:
            return zstd.decompress(data, zstd_dict=candidate)
        except zstd.ZstdError:
            continue
    sys.exit("no dictionary fits")


def parse_msbt(data):
    if data[:8] != b"MsgStdBn":
        raise ValueError("not MSBT")
    endian = "<" if data[8:10] == b"\xff\xfe" else ">"
    encoding = data[0xC]
    section_count = struct.unpack_from(endian + "H", data, 0xE)[0]
    at = 0x20
    sections = {}
    for _ in range(section_count):
        magic = data[at:at + 4].decode("ascii")
        size = struct.unpack_from(endian + "I", data, at + 4)[0]
        sections[magic] = data[at + 0x10:at + 0x10 + size]
        at += 0x10 + size
        at = (at + 15) & ~15
    labels = {}
    lbl = sections.get("LBL1")
    if lbl:
        groups = struct.unpack_from(endian + "I", lbl, 0)[0]
        for g in range(groups):
            count, off = struct.unpack_from(endian + "II", lbl, 4 + 8 * g)
            for _ in range(count):
                n = lbl[off]
                name = lbl[off + 1:off + 1 + n].decode("utf-8")
                labels[struct.unpack_from(endian + "I", lbl, off + 1 + n)[0]] = name
                off += 1 + n + 4
    txt = sections["TXT2"]
    count = struct.unpack_from(endian + "I", txt, 0)[0]
    offsets = list(struct.unpack_from(endian + "%dI" % count, txt, 4)) + [len(txt)]
    messages = []
    attrs = []
    atr = sections.get("ATR1")
    atr_count = atr_size = 0
    if atr and len(atr) >= 8:
        atr_count, atr_size = struct.unpack_from(endian + "II", atr, 0)
    for i in range(count):
        text, tags = decode_text(txt[offsets[i]:offsets[i + 1]], endian, encoding)
        attr = ""
        if atr_size and i < atr_count:
            raw = atr[8 + i * atr_size:8 + (i + 1) * atr_size]
            attr = raw.hex()
            if atr_size == 4:   # an offset to a UTF-16 string in the same section
                str_at = struct.unpack(endian + "I", raw)[0]
                end = str_at
                while end + 1 < len(atr) and atr[end:end + 2] != b"\0\0":
                    end += 2
                attr = atr[str_at:end].decode("utf-16-le" if endian == "<" else "utf-16-be", "replace")
        messages.append(dict(index=i, label=labels.get(i, ""), text=text, tags=tags, attr=attr))
    return messages


def decode_text(blob, endian, encoding):
    """Text with control tags shown as {g:t:hexparams}. encoding 1 is UTF-16, 0 is UTF-8 (this game)."""
    if encoding == 0:
        return decode_utf8(blob, endian)
    if encoding != 1:
        raise ValueError("unexpected encoding %d" % encoding)
    out = []
    tags = []
    at = 0
    while at + 2 <= len(blob):
        c = struct.unpack_from(endian + "H", blob, at)[0]
        at += 2
        if c == 0:
            break
        if c == 0x0E:
            group, kind, size = struct.unpack_from(endian + "HHH", blob, at)
            at += 6
            params = blob[at:at + size].hex()
            at += size
            tags.append([group, kind, params])
            out.append("{%d:%d:%s}" % (group, kind, params))
        elif c == 0x0F:
            group, kind = struct.unpack_from(endian + "HH", blob, at)
            at += 4
            out.append("{/%d:%d}" % (group, kind))
        else:
            out.append(chr(c))
    return "".join(out), tags


def decode_utf8(blob, endian):
    """0x0E, u16 group, u16 type, u16 param size, params; 0x0F, u16 group, u16 type; 0 ends the message."""
    out = []
    tags = []
    run = bytearray()

    def flush():
        if run:
            out.append(run.decode("utf-8", "replace"))
            run.clear()

    at = 0
    while at < len(blob):
        c = blob[at]
        at += 1
        if c == 0:
            break
        if c == 0x0E:
            flush()
            group, kind, size = struct.unpack_from(endian + "HHH", blob, at)
            at += 6
            params = blob[at:at + size]
            at += size
            tags.append([group, kind, params.hex()])
            out.append("{%d:%d:%s}" % (group, kind, params.hex()))
        elif c == 0x0F:
            flush()
            group, kind = struct.unpack_from(endian + "HH", blob, at)
            at += 4
            out.append("{/%d:%d}" % (group, kind))
        else:
            run.append(c)
    flush()
    return "".join(out), tags


def tag_name(params_hex, endian="<"):
    """A tag whose params are u16 length + string + NUL, else None."""
    raw = bytes.fromhex(params_hex)
    if len(raw) < 3:
        return None
    n = struct.unpack_from(endian + "H", raw, 0)[0]
    if n + 3 != len(raw):
        return None
    return raw[2:2 + n].decode("utf-8", "replace")


def survey(args):
    nup = Nup(args.nup)
    title = nup.newest()
    romfs = list(nup.walk(title["romfs"]))
    print("titles:", [(hex(t["id"]), t["version"]) for t in nup.titles], "romfs files:", len(romfs))
    print("--- Mals")
    for path, record in romfs:
        if path.startswith("Mals/"):
            print(path, record[2])
    voice = [(p, r) for p, r in romfs if p.startswith("Voice/")]
    print("--- Voice files:", len(voice), "bytes:", sum(r[2] for _, r in voice))
    tree = collections.Counter("/".join(p.split("/")[:4]) for p, _ in voice)
    for key, n in tree.most_common(30):
        print(n, key)
    print("sample:", [p for p, _ in voice[:12]])
    event = collections.Counter(os.path.splitext(p)[1] for p, _ in romfs if p.startswith("Event/"))
    print("--- Event extensions:", event.most_common(10))
    print("--- Npc packs:", sum(1 for p, _ in romfs if p.startswith("Pack/Actor/Npc")))


def extract(args):
    nup = Nup(args.nup)
    romfs = list(nup.walk(nup.newest()["romfs"]))
    dicts = load_dicts(nup, romfs)
    print("dictionaries:", sorted(dicts))
    target = [(p, r) for p, r in romfs if p.startswith("Mals/" + args.lang + ".")]
    if not target:
        sys.exit("no Mals archive for " + args.lang)
    os.makedirs(args.out, exist_ok=True)
    jsonl = os.path.join(args.out, "script_%s.jsonl" % args.lang)
    totals = collections.Counter()
    with open(jsonl, "w", encoding="utf-8") as out:
        for path, record in target:
            print("archive:", path, record[2])
            sarc = parse_sarc(unzs(nup.read(record), dicts))
            for name, data in sorted(sarc.items()):
                dst = os.path.join(args.out, "msbt", *name.split("/"))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "wb") as g:
                    g.write(data)
                if not name.endswith(".msbt"):
                    totals["non-msbt"] += 1
                    continue
                try:
                    messages = parse_msbt(data)
                except (ValueError, KeyError, struct.error) as error:
                    print("  failed", name, error)
                    totals["failed"] += 1
                    continue
                totals["msbt"] += 1
                for m in messages:
                    m["file"] = name
                    out.write(json.dumps(m, ensure_ascii=False) + "\n")
                    totals["messages"] += 1
    print(dict(totals), "->", jsonl)


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("survey")
    s.add_argument("nup")
    e = sub.add_parser("extract")
    e.add_argument("nup")
    e.add_argument("out")
    e.add_argument("--lang", default="USen")
    args = ap.parse_args()
    {"survey": survey, "extract": extract}[args.cmd](args)


if __name__ == "__main__":
    main()
