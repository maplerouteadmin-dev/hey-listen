"""Split a message into the text boxes the game shows, so each box can be its own message with its own voice clip.

Message text is in the form script_extract.py writes: UTF-8 with tags shown as {group:type:hexparams} and {/group:type}.
A box ends at a page-break tag {0:4:} or after BOX_LINES lines (the box shows two lines; a third starts a new box,
which is where the game's own voiced lines put their PageBreak marker).
"""
import re
import struct

BOX_LINES = 2
TOKEN = re.compile(r"\{(\d+):(\d+):([0-9a-f]*)\}|\{/(\d+):(\d+)\}|\n|[^{\n]+|\{")
PAGE_BREAK = (0, 4)
# Tags that set how later text looks or runs; a later box starts with the latest of each again.
CARRY = {(0, 2), (0, 3)}
SUFFIX = "__b%d"     # label of box n (n >= 2): <label>__b2, <label>__b3, ...


def tokens(raw):
    for m in TOKEN.finditer(raw):
        if m.group(1) is not None:
            yield ("tag", int(m.group(1)), int(m.group(2)), m.group(3))
        elif m.group(4) is not None:
            yield ("end", int(m.group(4)), int(m.group(5)), "")
        else:
            yield ("text", 0, 0, m.group(0))


def split(raw):
    """The raw text of each box, in order. A message that fits one box comes back unchanged as a single item."""
    boxes, current, lines, carried = [], [], 1, {}
    has_text = False

    def close():
        nonlocal current, lines, has_text
        if has_text:
            boxes.append("".join(current))
        elif boxes and current:
            boxes[-1] += "".join(current)   # trailing tags belong to the box before
        current, lines, has_text = [carried[k] for k in sorted(carried)] if boxes or has_text else [], 1, False

    for kind, g, t, value in tokens(raw):
        if kind == "tag" and (g, t) == PAGE_BREAK:
            close()
            continue
        if kind == "text" and value == "\n":
            if lines >= BOX_LINES:
                close()
                continue
            lines += 1
            current.append("\n")
            continue
        text = "{%d:%d:%s}" % (g, t, value) if kind == "tag" else "{/%d:%d}" % (g, t) if kind == "end" else value
        if kind == "tag" and (g, t) in CARRY:
            carried[(g, t)] = text
        if kind == "text" and value.strip():
            has_text = True
        current.append(text)
    if has_text or not boxes:
        boxes.append("".join(current))
    elif current:
        boxes[-1] += "".join(current)
    return boxes


def encode(raw, endian="<"):
    """Raw text back to the game's UTF-8 message bytes, ending in 0."""
    out = bytearray()
    for kind, g, t, value in tokens(raw):
        if kind == "tag":
            params = bytes.fromhex(value)
            out += b"\x0e" + struct.pack(endian + "HHH", g, t, len(params)) + params
        elif kind == "end":
            out += b"\x0f" + struct.pack(endian + "HH", g, t)
        else:
            out += value.encode("utf-8")
    return bytes(out) + b"\0"


VAR = re.compile(r"\{2:\d+:([0-9a-f]*)\}")
ANY = re.compile(r"\{/?\d+:\d+:?[0-9a-f]*\}")


def visible(raw):
    """What a box says, as the line lists write it (same rules as build_line_table.clean)."""
    def var(m):
        b = bytes.fromhex(m.group(1))
        if len(b) >= 2:
            n = struct.unpack_from("<H", b)[0]
            return "<%s>" % b[2:2 + n].decode("utf-8", "replace")
        return "<var>"
    plain = ANY.sub("", VAR.sub(var, raw))
    plain = re.sub(r"([.!?…\"])([A-Z])", r"\1 \2", plain)
    return re.sub(r"\s+", " ", plain).strip()
