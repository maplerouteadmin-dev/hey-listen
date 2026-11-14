"""Hookshot reads the game's resource size table from its own copy (<game>/prompts/rsizetable.zs), not from romfs,
so a modded file that grew is given too little memory and the game crashes at boot. This raises Hookshot's copy to
the mod's sizes, keeping every entry Hookshot changed itself.

    py -3.14 -I hookshot_rstb.py <hookshot table> <mod table> <output>
"""
import struct
import sys
from compression import zstd


def read(path):
    d = zstd.decompress(open(path, "rb").read())
    assert d[:6] == b"RESTBL", path
    ver, strsz, n, m = struct.unpack_from("<IIII", d, 6)
    table = dict(struct.unpack_from("<II", d, 22 + 8 * i) for i in range(n))
    return d, ver, strsz, m, table


def main():
    hook_path, mod_path, out_path = sys.argv[1:4]
    d, ver, strsz, m, hook = read(hook_path)
    _, _, _, _, mod = read(mod_path)
    names = d[22 + 8 * len(hook):]
    raised = added = 0
    for crc, size in mod.items():
        if crc not in hook:
            added += 1
        elif size > hook[crc]:
            raised += 1
        else:
            continue
        hook[crc] = size
    body = b"".join(struct.pack("<II", c, s) for c, s in sorted(hook.items()))
    out = d[:6] + struct.pack("<IIII", ver, strsz, len(hook), m) + body + names
    with open(out_path, "wb") as f:
        f.write(zstd.compress(out))
    print("Hookshot size table: %d entries raised, %d added" % (raised, added))


if __name__ == "__main__":
    main()
