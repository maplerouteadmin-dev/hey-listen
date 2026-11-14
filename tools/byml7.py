"""Minimal BYML v7 (little-endian) reader and writer, enough for Voice/VoiceSettingInfo.

read(data) -> Python values: dict (string keys), Hash32Map/Hash64Map (int keys), list, str, bytes, bool, int, float, None.
write(value) -> bytes. Typed numbers keep their BYML type through the U32/I64/U64/F64 wrappers.
"""
import struct


class U32(int): pass
class I64(int): pass
class U64(int): pass
class F64(float): pass
class Hash32Map(dict): pass
class Hash64Map(dict): pass


STR, BIN, BIN_ALIGNED = 0xA0, 0xA1, 0xA2
ARRAY, DICT, STRTAB = 0xC0, 0xC1, 0xC2
HASH32, HASH64 = 0x20, 0x21
BOOL, INT, FLOAT, UINT, INT64, UINT64, DOUBLE, NULL = 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xFF
CONTAINERS = {ARRAY, DICT, HASH32, HASH64}
BIG = {INT64, UINT64, DOUBLE}


def _strtab(d, at):
    if not at:
        return []
    assert d[at] == STRTAB, hex(d[at])
    n = int.from_bytes(d[at + 1:at + 4], "little")
    offs = struct.unpack_from("<%dI" % (n + 1), d, at + 4)
    return [d[at + offs[i]:at + offs[i + 1]].split(b"\0", 1)[0].decode("utf-8") for i in range(n)]


def read(d):
    assert d[:2] == b"YB", "not little-endian BYML"
    version, keys_at, strs_at, root_at = struct.unpack_from("<HIII", d, 2)
    assert version == 7, version
    keys, strs = _strtab(d, keys_at), _strtab(d, strs_at)

    def value(kind, raw):
        if kind in CONTAINERS:
            return node(raw)
        if kind == STR:
            return strs[raw]
        if kind == BOOL:
            return bool(raw)
        if kind == INT:
            return struct.unpack("<i", struct.pack("<I", raw))[0]
        if kind == UINT:
            return U32(raw)
        if kind == FLOAT:
            return struct.unpack("<f", struct.pack("<I", raw))[0]
        if kind == INT64:
            return I64(struct.unpack_from("<q", d, raw)[0])
        if kind == UINT64:
            return U64(struct.unpack_from("<Q", d, raw)[0])
        if kind == DOUBLE:
            return F64(struct.unpack_from("<d", d, raw)[0])
        if kind == NULL:
            return None
        if kind == BIN:
            n = struct.unpack_from("<I", d, raw)[0]
            return bytes(d[raw + 4:raw + 4 + n])
        raise ValueError("unsupported BYML node 0x%02x" % kind)

    def node(at):
        kind = d[at]
        n = int.from_bytes(d[at + 1:at + 4], "little")
        if kind == ARRAY:
            types = d[at + 4:at + 4 + n]
            vals_at = at + 4 + ((n + 3) & ~3)
            return [value(types[i], struct.unpack_from("<I", d, vals_at + 4 * i)[0]) for i in range(n)]
        if kind == DICT:
            out = {}
            for i in range(n):
                e = at + 4 + 8 * i
                k = int.from_bytes(d[e:e + 3], "little")
                out[keys[k]] = value(d[e + 3], struct.unpack_from("<I", d, e + 4)[0])
            return out
        if kind in (HASH32, HASH64):
            hw = 4 if kind == HASH32 else 8
            stride = hw + 4
            out = Hash32Map() if kind == HASH32 else Hash64Map()
            types_at = at + 4 + stride * n
            for i in range(n):
                e = at + 4 + stride * i
                h = int.from_bytes(d[e:e + hw], "little")
                out[h] = value(d[types_at + i], struct.unpack_from("<I", d, e + hw)[0])
            return out
        raise ValueError("unsupported BYML container 0x%02x at 0x%x" % (kind, at))

    return node(root_at) if root_at else None


def _kind(v):
    if isinstance(v, bool): return BOOL
    if isinstance(v, U32): return UINT
    if isinstance(v, I64): return INT64
    if isinstance(v, U64): return UINT64
    if isinstance(v, int): return INT
    if isinstance(v, F64): return DOUBLE
    if isinstance(v, float): return FLOAT
    if isinstance(v, str): return STR
    if isinstance(v, bytes): return BIN
    if v is None: return NULL
    if isinstance(v, Hash32Map): return HASH32
    if isinstance(v, Hash64Map): return HASH64
    if isinstance(v, dict): return DICT
    if isinstance(v, list): return ARRAY
    raise TypeError(type(v))


def write(root):
    keys, strs = set(), set()

    def collect(v):
        if isinstance(v, (Hash32Map, Hash64Map)):
            for x in v.values(): collect(x)
        elif isinstance(v, dict):
            keys.update(v); [collect(x) for x in v.values()]
        elif isinstance(v, list):
            [collect(x) for x in v]
        elif isinstance(v, str):
            strs.add(v)
    collect(root)
    keys, strs = sorted(keys, key=lambda s: s.encode()), sorted(strs, key=lambda s: s.encode())
    kidx, sidx = {k: i for i, k in enumerate(keys)}, {s: i for i, s in enumerate(strs)}
    out = bytearray(0x10)

    def align(n=4):
        out.extend(b"\0" * (-len(out) % n))

    def strtab(items):
        if not items:
            return 0
        align()
        at = len(out)
        enc = [s.encode() + b"\0" for s in items]
        head = 4 + 4 * (len(items) + 1)
        offs, pos = [], head
        for e in enc:
            offs.append(pos); pos += len(e)
        offs.append(pos)
        out.extend(bytes([STRTAB]) + len(items).to_bytes(3, "little") + struct.pack("<%dI" % len(offs), *offs) + b"".join(enc))
        return at

    keys_at, strs_at = strtab(keys), strtab(strs)
    align()
    big_done, pending = {}, []

    def scalar(v):
        k = _kind(v)
        if k == STR: return sidx[v]
        if k == BOOL: return int(v)
        if k == INT: return struct.unpack("<I", struct.pack("<i", v))[0]
        if k == UINT: return int(v)
        if k == FLOAT: return struct.unpack("<I", struct.pack("<f", v))[0]
        if k == NULL: return 0
        return None   # needs its own data

    def place(v):
        """Write a container or big value now and return its offset."""
        k = _kind(v)
        align(8 if k in BIG else 4)
        at = len(out)
        if k in BIG:
            out.extend(struct.pack({INT64: "<q", UINT64: "<Q", DOUBLE: "<d"}[k], v))
            return at
        if k == BIN:
            out.extend(struct.pack("<I", len(v)) + v)
            return at
        if k == ARRAY:
            out.extend(bytes([ARRAY]) + len(v).to_bytes(3, "little") + bytes(_kind(x) for x in v))
            align()
            slots = len(out)
            out.extend(b"\0" * 4 * len(v))
            for i, x in enumerate(v):
                pending.append((slots + 4 * i, x))
            return at
        if k == DICT:
            items = sorted(v.items(), key=lambda kv: kv[0].encode())
            out.extend(bytes([DICT]) + len(items).to_bytes(3, "little"))
            for key, x in items:
                e = len(out)
                out.extend(kidx[key].to_bytes(3, "little") + bytes([_kind(x)]) + b"\0\0\0\0")
                pending.append((e + 4, x))
            return at
        if k in (HASH32, HASH64):
            hw = 4 if k == HASH32 else 8
            items = sorted(v.items())
            out.extend(bytes([k]) + len(items).to_bytes(3, "little"))
            for h, x in items:
                e = len(out)
                out.extend(h.to_bytes(hw, "little") + b"\0\0\0\0")
                pending.append((e + hw, x))
            out.extend(bytes(_kind(x) for _, x in items))
            align()
            return at
        raise TypeError(k)

    root_at = place(root)
    while pending:
        slot, v = pending.pop(0)
        raw = scalar(v)
        if raw is None:
            raw = place(v)
        struct.pack_into("<I", out, slot, raw)
    align()
    struct.pack_into("<2sHIII", out, 0, b"YB", 7, keys_at, strs_at, root_at)
    return bytes(out)
