"""Turn a line list into one line per text box, for qwen_pack.py.

    py -3.14 -I make_box_lines.py <pack_full.jsonl> <line_table_USen.jsonl> <pack_boxes.jsonl>

A message that fills one box is copied unchanged. A longer one becomes one line per box: box 1 keeps the message id
(the mod shrinks that message to box 1), box n gets id <message>__bn (a message the mod adds), and each carries
"message", "box" and "boxes". qwen_pack.py skips any (voice, text) it has already made, so only new boxes are generated.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boxes  # noqa: E402


def main():
    src, table, dst = sys.argv[1:4]
    raw = {}
    with open(table, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            raw[row["id"]] = row["raw"]
    count = split_rows = new_rows = 0
    with open(src, encoding="utf-8") as f, open(dst + ".tmp", "w", encoding="utf-8") as out:
        for line in f:
            row = json.loads(line)
            count += 1
            parts = boxes.split(raw.get(row["id"], ""))
            if len(parts) < 2:
                out.write(line if line.endswith("\n") else line + "\n")
                continue
            split_rows += 1
            for n, part in enumerate(parts, 1):
                text = boxes.visible(part)
                if not text:
                    continue
                box = dict(row, id=row["id"] + (boxes.SUFFIX % n if n > 1 else ""), text=text,
                           message=row["id"], box=n, boxes=len(parts))
                box.pop("say", None)
                out.write(json.dumps(box, ensure_ascii=False) + "\n")
                new_rows += 1
    os.replace(dst + ".tmp", dst)
    print("%d lines in, %d split into %d box lines -> %s" % (count, split_rows, new_rows, dst))


if __name__ == "__main__":
    main()
