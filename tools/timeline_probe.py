"""Follow one cutscene message back to the character that speaks it. Read-only.

    python -I timeline_probe.py <script_extract.py> <file.nup> [flow]
"""
import collections
import importlib.util
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
spec = importlib.util.spec_from_file_location("x", sys.argv[1])
x = importlib.util.module_from_spec(spec)
spec.loader.exec_module(x)
nup = x.Nup(sys.argv[2])
romfs = dict(nup.walk(nup.newest()["romfs"]))
dicts = x.load_dicts(nup, list(romfs.items()))
name = sys.argv[3] if len(sys.argv) > 3 else "Dm_Goron_0020"
b = x.unzs(nup.read(romfs["Event/EventFlow/%s.bfevfl.zs" % name]), dicts)


def q(at):
    return struct.unpack_from("<Q", b, at)[0]


def h(at):
    return struct.unpack_from("<H", b, at)[0]


def s(at):
    if at <= 0 or at + 2 >= len(b):
        return None
    n = h(at)
    if n > 256 or at + 2 + n >= len(b) or b[at + 2 + n] != 0:
        return None
    try:
        return b[at + 2:at + 2 + n].decode("utf-8")
    except UnicodeDecodeError:
        return None


refs = collections.defaultdict(list)
for at in range(0, len(b) - 8, 8):
    refs[q(at)].append(at)

tl = q(q(0x38))
na, nact, nclip = h(tl + 0x14), h(tl + 0x16), h(tl + 0x18)
print("counts actors", na, "actions", nact, "clips", nclip, "oneshots", h(tl + 0x1c), "x", h(tl + 0x1e))
actors = q(tl + 0x28)
print("actors", [s(q(actors + i * 0x38)) for i in range(na)])
for off in (0x30, 0x38, 0x40, 0x48, 0x50, 0x58):
    print("tl+%02x" % off, hex(q(tl + off)))

done = 0
for loc in [a for a in range(0, len(b) - 8, 8) if (t := s(q(a)) if 0 < q(a) < len(b) else None) and t.startswith("EventFlowMsg/")]:
    if done == 3:
        break
    done += 1
    item = loc - 0x10
    print("--- msg", s(q(loc)), "item", hex(item), "type", b[item], "refs to item", [hex(r) for r in refs[item]])
    for r in refs[item]:
        for back in range(0, 0x80, 8):
            c = r - 0x10 - back
            count = h(c + 2)
            if b[c] == 1 and count == back // 8 + 1 or (b[c] == 0 and count == back // 8 + 1):
                print(" container", hex(c), "type", b[c], "count", count, "item names ptr", hex(q(c + 8)), "refs", [hex(z) for z in refs[c]])
                for z in refs[c]:
                    for row in range(-0x30, 0x30, 0x10):
                        print("   z%+04x" % row, b[z + row:z + row + 0x10].hex(" "))
                break
