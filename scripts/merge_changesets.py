"""Put several changesets into one file, in the order given.

Order is the whole point: the editor applies changes in file order and the last
change on a field wins, so a later file overrides an earlier one. The header of
the FIRST file is kept - it is the one the author saved - and only the contents
of each `db_changes` list are carried across.
"""
import argparse, os
import xml.etree.ElementTree as ET

OPEN = '<list id="db_changes">'


def close_of(text, start):
    """Where the db_changes list closes.

    Not the file's LAST `</list>`: these files carry a `Coms` list after
    db_changes, and slicing to the last one puts every merged change inside the
    comments, where the editor never looks. A self-closing `<list ... />` opens
    nothing, so it must not raise the depth."""
    i, depth = start, 1
    while depth:
        o, c = text.find("<list", i), text.find("</list>", i)
        if c < 0:
            raise ValueError("db_changes is not closed")
        if 0 <= o < c:
            end = text.index(">", o)
            i = end + 1
            if text[end - 1] != "/":
                depth += 1
            continue
        depth -= 1
        if depth == 0:
            return c
        i = c + len("</list>")


def split(path):
    """(head up to and including the db_changes tag, body, tail from its close)"""
    text = open(path, encoding="utf-8").read()
    i = text.index(OPEN) + len(OPEN)
    c = close_of(text, i)
    return text[:i], text[i:c], text[c:]


def body(path):
    return split(path)[1]


def count(path):
    """Top-level change records only - and clear only those, because clearing a
    nested element empties the record that has not ended yet."""
    n = 0
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag != "record" or el.get("id") is not None:
            continue
        if el.find('integer[@id="database_table_type"]') is not None:
            n += 1
        el.clear()
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    head, _, tail = split(a.inputs[0])
    parts = []
    for p in a.inputs:
        n = count(p)
        parts.append(body(p))
        print("  %-58s %7d changes" % (os.path.basename(p)[:58], n))
    open(a.out, "w", encoding="utf-8").write(head + "".join(parts) + "\n\t" + tail)
    print("merged -> %s (%d changes)" % (a.out, count(a.out)))


if __name__ == "__main__":
    main()
