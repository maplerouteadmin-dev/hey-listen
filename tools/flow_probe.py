"""Check the event-flow layout on real files before trusting it. Read-only.

    python -I flow_probe.py <script_extract.py> <file.nup> [flow name ...]
"""
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


def q(b, at):
    return struct.unpack_from("<Q", b, at)[0]


def h(b, at):
    return struct.unpack_from("<H", b, at)[0]


def s(b, at):
    if at <= 0 or at + 2 >= len(b):
        return None
    n = h(b, at)
    if n > 256 or at + 2 + n >= len(b) or b[at + 2 + n] != 0:
        return None
    try:
        return b[at + 2:at + 2 + n].decode("utf-8")
    except UnicodeDecodeError:
        return None


for name in sys.argv[3:] or ["Dm_Goron_0020", "Animal_Cow_LinkHouse", "Npc_Hylia_Malon_Child"]:
    path = "Event/EventFlow/%s.bfevfl.zs" % name
    if path not in romfs:
        print("missing", name)
        continue
    b = x.unzs(nup.read(romfs[path]), dicts)
    print("###", name, len(b), b[:0x48].hex(" "))
    num_flow = h(b, 0x20)
    print("flowcharts", num_flow, "timelines", h(b, 0x22))
    if not num_flow:
        tl = q(b, q(b, 0x38))
        print("timeline at", hex(tl), b[tl:tl + 4])
        for row in range(0, 0x90, 0x10):
            print("  +%02x" % row, b[tl + row:tl + row + 0x10].hex(" "))
        refs = []
        for at in range(0, len(b) - 8, 8):
            target = q(b, at)
            text = s(b, target) if 0 < target < len(b) else None
            if text and text.startswith("EventFlowMsg/"):
                refs.append((hex(at), text))
        print("message refs", len(refs), refs[:4])
        at = int(refs[0][0], 16)
        for row in range(-0x60, 0x40, 0x10):
            print("  ref%+04x" % row, b[at + row:at + row + 0x10].hex(" "))
        continue
    flow = q(b, q(b, 0x28))
    print("flow at", hex(flow), b[flow:flow + 4], b[flow:flow + 0x60].hex(" "))
    print("num a/a/q/e:", [h(b, flow + 0x10 + i * 2) for i in range(5)])
    actors_at, events_at = q(b, flow + 0x28), q(b, flow + 0x30)
    print("name", s(b, q(b, flow + 0x20)), "actors_at", hex(actors_at), "events_at", hex(events_at))
    na, ne = h(b, flow + 0x10), h(b, flow + 0x16)
    for stride in (0x38, 0x40, 0x48, 0x50):
        got = [s(b, q(b, actors_at + i * stride)) for i in range(na)]
        print("actor stride", hex(stride), got[:14])
    print("first events")
    for stride in (0x28, 0x30):
        print(" stride", hex(stride), [(s(b, q(b, events_at + i * stride)), b[events_at + i * stride + 8]) for i in range(min(ne, 8))])
    print(" event0", b[events_at:events_at + 0x28].hex(" "))
