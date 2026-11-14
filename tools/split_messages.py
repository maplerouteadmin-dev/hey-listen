"""Give each text box of a long message its own message, so each box can carry its own voice clip.

The game plays one clip per message and starts it again when the player moves to the next box, so a clip that
covers several boxes repeats. The game's own voiced lines are all one box long. This module:
  - shrinks message X to its first box and adds X__b2, X__b3, ... (MSBT inside the Mals SARC),
  - in every event flow, follows each "talk" event that shows X with new talk events showing X__b2, ...
    (BFEVFL: the event list is copied to the end of the file with the new events added, and the pointer
    table is rebuilt; nothing already in the file moves, so every other reference stays valid).
"""
import struct

# ---------------- MSBT (LBL1 + TXT2, UTF-8) ----------------

def label_hash(label, groups):
    h = 0
    for c in label.encode("utf-8"):
        h = (h * 0x492 + c) & 0xFFFFFFFF
    return h % groups


def read_msbt(d):
    """(header info, [(label, text bytes incl. final 0)] in message order)."""
    assert d[:8] == b"MsgStdBn" and d[8:10] == b"\xff\xfe"
    count = struct.unpack_from("<H", d, 0xE)[0]
    at, secs, order = 0x20, {}, []
    for _ in range(count):
        magic = d[at:at + 4].decode()
        size = struct.unpack_from("<I", d, at + 4)[0]
        secs[magic] = d[at + 0x10:at + 0x10 + size]
        order.append(magic)
        at = (at + 0x10 + size + 15) & ~15
    assert order == ["LBL1", "TXT2"], order
    lbl, txt = secs["LBL1"], secs["TXT2"]
    groups = struct.unpack_from("<I", lbl, 0)[0]
    labels = {}
    for g in range(groups):
        n, off = struct.unpack_from("<II", lbl, 4 + 8 * g)
        for _ in range(n):
            ln = lbl[off]
            labels[struct.unpack_from("<I", lbl, off + 1 + ln)[0]] = lbl[off + 1:off + 1 + ln].decode("utf-8")
            off += 1 + ln + 4
    n = struct.unpack_from("<I", txt, 0)[0]
    offs = list(struct.unpack_from("<%dI" % n, txt, 4)) + [len(txt)]
    msgs = [(labels[i], txt[offs[i]:offs[i + 1]]) for i in range(n)]
    return dict(head=d[:0x20], groups=groups), msgs


def write_msbt(info, msgs):
    groups = info["groups"]
    buckets = [[] for _ in range(groups)]
    for i, (label, _) in enumerate(msgs):
        buckets[label_hash(label, groups)].append((label, i))
    table = bytearray(struct.pack("<I", groups))
    names = bytearray()
    base = 4 + 8 * groups
    for b in buckets:
        table += struct.pack("<II", len(b), base + len(names))
        for label, i in b:
            raw = label.encode("utf-8")
            names += bytes([len(raw)]) + raw + struct.pack("<I", i)
    lbl = bytes(table + names)
    head = 4 + 4 * len(msgs)
    offs, pos = [], head
    for _, t in msgs:
        offs.append(pos)
        pos += len(t)
    txt = struct.pack("<I", len(msgs)) + struct.pack("<%dI" % len(msgs), *offs) + b"".join(t for _, t in msgs)

    def section(magic, body):
        s = magic + struct.pack("<I", len(body)) + b"\0" * 8 + body
        return s + b"\xab" * (-len(s) % 16)
    body = section(b"LBL1", lbl) + section(b"TXT2", txt)
    head = bytearray(info["head"])
    struct.pack_into("<I", head, 0x12, 0x20 + len(body))
    return bytes(head) + body


# ---------------- SARC ----------------

def sarc_hash(name, key):
    h = 0
    for c in name.encode("utf-8"):
        h = (h * key + (c if c < 0x80 else c - 0x100)) & 0xFFFFFFFF
    return h


def read_sarc(d):
    """(info, {name: bytes}) keeping the archive's order and alignment facts."""
    assert d[:4] == b"SARC"
    hdr = struct.unpack_from("<H", d, 4)[0]
    data_at = struct.unpack_from("<I", d, 0xC)[0]
    sfat = hdr
    n, key = struct.unpack_from("<HI", d, sfat + 6)
    nodes = sfat + 0xC
    sfnt = nodes + 16 * n
    names_at = sfnt + 8
    files, aligns = {}, []
    for i in range(n):
        h, attr, start, end = struct.unpack_from("<IIII", d, nodes + 16 * i)
        name_at = names_at + (attr & 0xFFFFFF) * 4
        name = d[name_at:d.index(b"\0", name_at)].decode("utf-8")
        files[name] = d[data_at + start:data_at + end]
        aligns.append(start)
    return dict(head=d[:hdr], key=key, data_at=data_at, starts=aligns), files


def write_sarc(info, files, align=16):
    key = info["key"]
    items = sorted(files.items(), key=lambda kv: sarc_hash(kv[0], key))
    names = bytearray()
    name_off = {}
    for name, _ in items:
        name_off[name] = len(names) // 4
        names += name.encode("utf-8") + b"\0"
        names += b"\0" * (-len(names) % 4)
    hdr = len(info["head"])
    sfat = struct.pack("<4sHHI", b"SFAT", 0xC, len(items), key)
    nodes = bytearray()
    data = bytearray()
    for name, blob in items:
        data += b"\0" * (-len(data) % align)
        nodes += struct.pack("<IIII", sarc_hash(name, key), 0x01000000 | name_off[name], len(data), len(data) + len(blob))
        data += blob
    sfnt = struct.pack("<4sHH", b"SFNT", 8, 0) + names
    meta = bytes(info["head"]) + sfat + bytes(nodes) + sfnt
    data_at = len(meta) + (-len(meta) % info.get("data_align", 8))
    out = bytearray(meta + b"\0" * (data_at - len(meta)) + data)
    struct.pack_into("<II", out, 8, len(out), data_at)
    return bytes(out)


# ---------------- BFEVFL ----------------

EVENT_SIZE = 0x30
TALK_ACTIONS = {"EventTalk", "EventTalkIgnoreSameTalkAS"}


class Flow:
    def __init__(self, d):
        self.d = bytearray(d)
        assert self.d[:8] == b"BFEVFL\0\0"
        self.relt = self.u32(0x18)
        self.ptrs = self.read_relt()

    def u16(self, a): return struct.unpack_from("<H", self.d, a)[0]
    def u32(self, a): return struct.unpack_from("<I", self.d, a)[0]
    def u64(self, a): return struct.unpack_from("<Q", self.d, a)[0]

    def string(self, a):
        """The string at a, or None where no valid string is (used to probe table layouts)."""
        if a <= 0 or a + 2 >= len(self.d):
            return None
        n = self.u16(a)
        if n > 512 or a + 2 + n >= len(self.d) or self.d[a + 2 + n] != 0:
            return None
        try:
            return self.d[a + 2:a + 2 + n].decode("utf-8")
        except UnicodeDecodeError:
            return None

    def read_relt(self):
        r = self.relt
        assert self.d[r:r + 4] == b"RELT"
        nsec = self.u32(r + 8)
        ptrs = set()
        entries = r + 0x10 + 0x18 * nsec
        for s in range(nsec):
            _, _, _, first, count = struct.unpack_from("<QIIII", self.d, r + 0x10 + 0x18 * s)
            for k in range(first, first + count):
                base, mask = struct.unpack_from("<II", self.d, entries + 8 * k)
                for b in range(32):
                    if mask >> b & 1:
                        ptrs.add(base + 8 * b)
        return ptrs

    def flowcharts(self):
        n = self.u16(0x20)
        arr = self.u64(0x28)
        return [self.u64(arr + 8 * i) for i in range(n)] if n else []

    def container(self, at):
        """{name: item address}"""
        if not at or self.d[at] != 1:
            return {}
        count, dic = self.u16(at + 2), self.u64(at + 8)
        names = [self.string(self.u64(dic + 0x18 + 0x10 * i + 8)) for i in range(self.u32(dic + 4))]
        return {names[i]: self.u64(at + 0x10 + 8 * i) for i in range(min(count, len(names)))}

    def item_value(self, item):
        kind = self.d[item]
        if kind == 5:
            return self.string(self.u64(item + 0x10))
        if kind in (2, 3):
            return struct.unpack_from("<i", self.d, item + 0x10)[0]
        return None

    def talk_events(self, fc):
        """[(event index, event address, container address, message id)] for talk events."""
        actors_at, events_at = self.u64(fc + 0x28), self.u64(fc + 0x30)
        n_actors, n_events = self.u16(fc + 0x10), self.u16(fc + 0x16)
        actions = []
        for a in range(n_actors):
            at = actors_at + 0x38 * a
            table, count = self.u64(at + 0x18), self.u16(at + 0x30)
            names = None
            for stride in (0x10, 8, 0x18):
                cand = [self.string(self.u64(table + i * stride)) if table + i * stride + 8 <= len(self.d) else None for i in range(count)]
                if all(cand):
                    names = cand
                    break
            actions.append(names or [None] * count)
        found = []
        for i in range(n_events):
            ev = events_at + EVENT_SIZE * i
            if self.d[ev + 8] != 0:
                continue
            actor, action = self.u16(ev + 0xC), self.u16(ev + 0xE)
            name = actions[actor][action] if actor < len(actions) and action < len(actions[actor]) else None
            if name not in TALK_ACTIONS:
                continue
            c = self.u64(ev + 0x10)
            items = self.container(c)
            if "MessageId" in items:
                found.append((i, ev, c, self.item_value(items["MessageId"])))
        return found


def split_flow(data, splits):
    """splits: {message id: [id of box 2, id of box 3, ...]}. Returns (new bytes, events added) or (data, 0)."""
    f = Flow(data)
    d = f.d
    end = f.relt
    out = bytearray(d[:end])
    ptrs = {p for p in f.ptrs if p < end}

    def align(n):
        out.extend(b"\0" * (-len(out) % n))

    def add_string(s):
        align(2)
        at = len(out)
        raw = s.encode("utf-8")
        out.extend(struct.pack("<H", len(raw)) + raw + b"\0")
        return at

    def put_ptr(at, value):
        struct.pack_into("<Q", out, at, value)
        ptrs.add(at)

    added = 0
    for fc in f.flowcharts():
        talks = [t for t in f.talk_events(fc) if t[3] in splits]
        if not talks:
            continue
        old_at, n = f.u64(fc + 0x30), f.u16(fc + 0x16)
        extra = sum(len(splits[t[3]]) for t in talks)
        if n + extra > 0xFFFF:
            continue
        # The event list, copied with room for the new events.
        align(8)
        new_at = len(out)
        out.extend(d[old_at:old_at + EVENT_SIZE * n])
        out.extend(b"\0" * (EVENT_SIZE * extra))
        for k in range(0, EVENT_SIZE * n, 8):
            if old_at + k in ptrs:
                ptrs.add(new_at + k)
        next_index = n
        for idx, ev, cont, msg in talks:
            items = f.container(cont)
            count = f.u16(cont + 2)
            boxes = splits[msg]
            chain = list(range(next_index, next_index + len(boxes)))
            next_index += len(boxes)

            def new_item(kind_from, value):
                """A copy of an item with a new value (str for string items, int for bool/int items)."""
                align(8)
                at = len(out)
                out.extend(d[kind_from:kind_from + 0x18])
                if isinstance(value, str):
                    s = add_string(value)
                    put_ptr(at + 0x10, s)
                else:
                    struct.pack_into("<i", out, at + 0x10, value)
                return at

            def new_container(changes):
                align(8)
                at = len(out)
                out.extend(d[cont:cont + 0x10 + 8 * count])
                ptrs.add(at + 8)
                for k in range(count):
                    ptrs.add(at + 0x10 + 8 * k)
                names = list(items)
                for name, value in changes.items():
                    if name in items:
                        slot = at + 0x10 + 8 * names.index(name)
                        item = new_item(items[name], value)
                        struct.pack_into("<Q", out, slot, item)
                return at

            keep_open = {"IsCloseDialog": 0}
            if "ChoiceNumber" in items and f.item_value(items["ChoiceNumber"]):
                keep_open["ChoiceNumber"] = 0
            first = new_container(keep_open)
            new_ev = new_at + EVENT_SIZE * idx
            orig_next = f.u16(ev + 0xA)
            struct.pack_into("<H", out, new_ev + 0xA, chain[0])
            struct.pack_into("<Q", out, new_ev + 0x10, first)
            for j, (box_id, ev_index) in enumerate(zip(boxes, chain)):
                last = j == len(boxes) - 1
                changes = {"MessageId": box_id, "ASName": ""}
                if not last:
                    changes.update(keep_open)
                params = new_container(changes)
                name = add_string("VoiceBox_%d_%d" % (idx, j + 2))
                e = new_at + EVENT_SIZE * ev_index
                out[e:e + EVENT_SIZE] = d[ev:ev + EVENT_SIZE]
                put_ptr(e, name)
                struct.pack_into("<H", out, e + 0xA, orig_next if last else chain[j + 1])
                put_ptr(e + 0x10, params)
                for k in range(0x18, EVENT_SIZE, 8):
                    struct.pack_into("<Q", out, e + k, 0)
                    ptrs.discard(e + k)
            added += len(boxes)
        struct.pack_into("<H", out, fc + 0x16, next_index)
        struct.pack_into("<Q", out, fc + 0x30, new_at)
    if not added:
        return data, 0
    data_end = len(out)
    align(8)
    relt_at = len(out)
    entries = []
    for p in sorted(ptrs):
        if entries and p - entries[-1][0] < 8 * 32 and (p - entries[-1][0]) % 8 == 0:
            entries[-1][1] |= 1 << ((p - entries[-1][0]) // 8)
        else:
            entries.append([p, 1])
    out.extend(struct.pack("<4sIII", b"RELT", relt_at, 1, 0))
    out.extend(struct.pack("<QIIII", 0, 0, data_end, 0, len(entries)))
    for base, mask in entries:
        out.extend(struct.pack("<II", base, mask))
    struct.pack_into("<II", out, 0x18, relt_at, len(out))
    return bytes(out), added
