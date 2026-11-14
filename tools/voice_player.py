"""Play a voice clip when a known line of dialogue appears in the emulator. Read-only: it never writes to the game.

    python -I voice_player.py --manifest A:/OotVoiceMod/pack/manifest.json [--listen] [--target lichii.exe]

How it works: the game copies each line of dialogue, as UTF-8 with control codes, into a small patch of its memory just before showing it,
and a new conversation starts again at the same address. Only that patch is polled, several times a second, so the voice starts right away.
If the patch has moved, a slow background search of the game's memory finds it again and the place is remembered for next time.
--listen logs matches without sound, for checking detection.
"""
import argparse
import bisect
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import struct
import subprocess
import sys
import threading
import time
import winsound

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
PAGE_READWRITE = 0x04
MEM_MAPPED = 0x40000
CHUNK = 64 << 20
POLL_SECONDS = 0.1
WINDOW = 1 << 16
MIN_GUEST_BYTES = 4 << 30
KNOWN_OFFSETS = (0x356bfe000, 0x23bcfe000)   # where the patch has been on this build, as offsets into the game's memory
SEARCH_AFTER_SECONDS = 60        # search only after this long with no dialogue seen
MAX_WINDOWS = 6
ENTRY_HEADER = re.compile(rb"\x03\x0e[\x00-\xff]{4}[\x00-\xff]{2}\x00{6}", re.S)
# Only the true start of a message: the end of a longer old message can linger after a shorter new one.
ENTRY_START = re.compile(rb"\x03\x0e[\x00-\xff]{4}[\x00-\xff]{2}\x00{6}|\x00(?=\x0e\x03\x00\x00\x00)", re.S)
MENU_TEXT = r"A:\OotVoiceMod\script\menu_text.json"
LOG_NAME = "player.log"
PREFIX_MIN_CHARS = 12            # a first page shorter than this is too common to name one message


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p), ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD),
                ("RegionSize", ctypes.c_size_t), ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
kernel32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
kernel32.VirtualQueryEx.restype = ctypes.c_size_t
kernel32.CloseHandle.argtypes = [wt.HANDLE]


def normalise(text):
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"').replace("\u2014", "-")
    return re.sub(r"\s+", " ", re.sub(r"\s*\n\s*", " ", text)).strip()


class Index:
    def __init__(self, manifest, menu_text=()):
        self.exact = {}
        for clip in manifest["clips"]:
            self.exact.setdefault(normalise(clip["text"]), []).append(clip)
        self.keys = sorted(self.exact)
        self.menu = {normalise(t) for t in menu_text}   # Link's answer choices also pass through the same memory
        self.last_slot = None

    def find(self, text):
        """The clip for a message. When several characters share a line, prefer whoever is already talking.
        The game copies a long message one page at a time, so the first page of a known message also counts:
        its clip covers the whole message. Later pages rarely begin a message, so they stay silent."""
        key = normalise(text)
        if not key or key in self.menu:
            return None
        clips = self.exact.get(key)
        if not clips and len(key) >= PREFIX_MIN_CHARS:
            i = bisect.bisect_left(self.keys, key)
            clips = []
            while i < len(self.keys) and self.keys[i].startswith(key):
                clips += self.exact[self.keys[i]]
                i += 1
        if not clips:
            return None
        return next((c for c in clips if c["slot"] == self.last_slot), clips[0])


def load_packs(where):
    """One manifest file, or a folder holding installed packs (each a subfolder with its own manifest.json)."""
    files = [where] if os.path.isfile(where) else sorted(
        os.path.join(where, d, "manifest.json") for d in os.listdir(where) if os.path.isfile(os.path.join(where, d, "manifest.json")))
    clips, menu_text = [], set()
    for path in files:
        folder = os.path.dirname(os.path.abspath(path))
        with open(path, encoding="utf-8") as f:
            for clip in json.load(f)["clips"]:
                clip["path"] = os.path.join(folder, clip["path"])   # absolute paths stay as they are
                clips.append(clip)
        menu = os.path.join(folder, "menu_text.json")
        if os.path.exists(menu):
            menu_text.update(json.load(open(menu, encoding="utf-8")))
    if os.path.exists(MENU_TEXT):
        menu_text.update(json.load(open(MENU_TEXT, encoding="utf-8")))
    return dict(clips=clips), menu_text


def find_pid(name):
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + name, "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    m = re.search(r'^"[^"]+","(\d+)"', out, re.M)
    return int(m.group(1)) if m else None


def read(handle, address, size):
    buffer = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t(0)
    if not kernel32.ReadProcessMemory(handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(got)) and got.value == 0:
        return b""
    return buffer.raw[:got.value]


def guest_memory(handle):
    """The emulator's large mapping holding the game's memory, as (base, size, spans).
    The mapping can show up as several regions (Fritchii splits it), so regions are grouped by their allocation;
    offsets are from the allocation's start, and spans lists the readable (offset, size) parts."""
    address = 0
    mbi = MBI()
    groups = {}
    while kernel32.VirtualQueryEx(handle, ctypes.c_void_p(address), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        size, base = mbi.RegionSize, mbi.BaseAddress or 0
        if mbi.State == MEM_COMMIT and mbi.Protect == PAGE_READWRITE and mbi.Type == MEM_MAPPED:
            groups.setdefault(mbi.AllocationBase or base, []).append((base, size))
        address = base + size
        if address >= 0x7FFFFFFFFFFF:
            break
    if not groups:
        return 0, 0, []
    alloc, regions = max(groups.items(), key=lambda kv: sum(s for _, s in kv[1]))
    if sum(s for _, s in regions) < MIN_GUEST_BYTES:
        return 0, 0, []
    return alloc, max(b + s for b, s in regions) - alloc, [(b - alloc, s) for b, s in regions]


def strip_codes(raw):
    """Visible text of a UTF-8 message, without its control codes."""
    out = bytearray()
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == 0:
            break
        if c == 0x0e:
            if i + 7 > len(raw):
                break
            i += 7 + struct.unpack_from("<H", raw, i + 5)[0]
        elif c == 0x0f:
            i += 5
        else:
            out.append(c)
            i += 1
    return out.decode("utf-8", "ignore")


def lines_in(data, index):
    """Known lines in a block of memory, as {position: clip}."""
    found = {}
    for m in ENTRY_START.finditer(data):
        clip = index.find(strip_codes(data[m.end():m.end() + 1500]))
        if clip:
            found[m.end()] = clip
    return found


def search(handle, base, spans, index, pause, results):
    """Find where live dialogue is now. Slow, so it runs beside the polling."""
    offsets = set()
    for start, length in spans:
        for offset in range(start, start + length, CHUNK):
            data = read(handle, base + offset, min(CHUNK + 2000, start + length - offset))
            for m in ENTRY_HEADER.finditer(data):
                if index.find(strip_codes(data[m.end():m.end() + 1500])):
                    offsets.add((offset + m.end()) & ~0xFFF)
            time.sleep(pause)
    results.append(offsets)


class Log:
    def __init__(self, folder):
        self.path = os.path.join(folder, LOG_NAME)
        open(self.path, "w", encoding="utf-8").close()

    def __call__(self, message):
        print(message, flush=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + message + "\n")


class Watch:
    """A patch of memory and the lines it held last time."""
    def __init__(self, handle, address, index):
        self.handle, self.address, self.index = handle, address, index
        self.data = read(handle, address, WINDOW)
        self.lines = lines_in(self.data, index)

    def poll(self):
        """The newest line that has just appeared here, or None."""
        data = read(self.handle, self.address, WINDOW)
        if not data or data == self.data:
            return None
        lines = lines_in(data, self.index)
        fresh = [(at, clip) for at, clip in lines.items() if at not in self.lines or self.lines[at]["text"] != clip["text"]]
        self.data, self.lines = data, lines
        return max(fresh, key=lambda pair: pair[0])[1] if fresh else None


def play_session(handle, pid, index, args, log, memory_file, target):
    base, size, spans = 0, 0, []
    while not size:
        if find_pid(target) != pid:
            return
        base, size, spans = guest_memory(handle)
        if not size:
            time.sleep(2)
    offsets = list(KNOWN_OFFSETS)
    if os.path.exists(memory_file):
        offsets = json.load(open(memory_file, encoding="utf-8")) + offsets
    watches = {o: Watch(handle, base + o, index) for o in dict.fromkeys(offsets) if o + WINDOW <= size}
    log("game memory found: %.1f GB, watching %d place(s), %d lines ready" % (size / 1e9, len(watches), len(index.keys)))
    start = time.time()
    last_line = last_search = start
    results, searcher, tick = [], None, 0
    while not args.seconds or time.time() - start < args.seconds:
        newest = None
        for watch in watches.values():
            newest = watch.poll() or newest
        now = time.time()
        if newest:
            last_line = now
            index.last_slot = newest["slot"]
            log("%s | %s" % (newest.get("slot", ""), normalise(newest["text"])[:70]))
            if not args.listen:
                winsound.PlaySound(newest["path"], winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        if results:
            found = results.pop()
            added = [o for o in found if o not in watches and o + WINDOW <= size]
            for o in added[:MAX_WINDOWS - len(watches)]:
                watches[o] = Watch(handle, base + o, index)
            if added:
                log("dialogue found at a new place, now watching %d" % len(watches))
                with open(memory_file, "w", encoding="utf-8") as f:
                    json.dump(list(watches)[-MAX_WINDOWS:], f)
            searcher, last_search = None, time.time()
        if searcher is None and now - last_line > SEARCH_AFTER_SECONDS and now - last_search > SEARCH_AFTER_SECONDS:
            searcher = threading.Thread(target=search, args=(handle, base, spans, index, args.scan_pause, results), daemon=True)
            searcher.start()
        tick += 1
        if tick % 50 == 0 and find_pid(target) != pid:
            log("game closed")
            return
        time.sleep(POLL_SECONDS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, help="A manifest.json, or a folder of installed packs")
    ap.add_argument("--target", default="lichii.exe")
    ap.add_argument("--listen", action="store_true")
    ap.add_argument("--seconds", type=float, default=0, help="Stop after this long (0 runs until closed)")
    ap.add_argument("--scan-pause", type=float, default=0.03, help="Seconds rested between memory chunks while searching")
    args = ap.parse_args()
    folder = os.path.abspath(args.manifest) if os.path.isdir(args.manifest) else os.path.dirname(os.path.abspath(args.manifest))
    log = Log(folder)
    memory_file = os.path.join(folder, "live_text.json")
    while True:
        pid = find_pid(args.target)
        if not pid:
            log("Waiting for %s to start..." % args.target)
        while not pid:
            time.sleep(3)
            pid = find_pid(args.target)
        # Loaded each session, so clips made since the last game, and packs added since, are included.
        manifest, menu_text = load_packs(args.manifest)
        index = Index(manifest, menu_text)
        log("%d clips loaded" % len(manifest["clips"]))
        handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not handle:
            sys.exit("Could not open process %d" % pid)
        try:
            play_session(handle, pid, index, args, log, memory_file, args.target)
        finally:
            winsound.PlaySound(None, winsound.SND_PURGE)
            kernel32.CloseHandle(handle)
        if args.seconds:
            return


if __name__ == "__main__":
    main()
