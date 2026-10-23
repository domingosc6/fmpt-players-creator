"""Put each rebuilt record's person-type change at the front of his changes.

FM will not set a player's attributes on a person it files as a non-player, and
a type change RESETS ability and attributes anyway - which is the whole reason
the repair pass exists. Both point the same way: the type change has to be the
FIRST thing said about a person, not the last.

Evandro Goebel imported with club, salary and date of birth accepted and every
attribute and position refused, because his type change sat at the end.

A created person with no type change at all gets one: he is rebuilt from a
player's record, so he is a player.
"""
import argparse, collections, os, random
import xml.etree.ElementTree as ET

PTYP = str(int.from_bytes(b"Ptyp", "big"))
PLAYER, NON_PLAYER = "2", "1"
BUILD = "3733"


def type_op(uid, rng):
    r = ET.Element("record")
    ET.SubElement(r, "integer", id="database_table_type", value="1")
    ET.SubElement(r, "large", id="db_unique_id", value=uid)
    ET.SubElement(r, "unsigned", id="property", value=PTYP)
    ET.SubElement(r, "integer", id="new_value", value=PLAYER)
    ET.SubElement(r, "integer", id="version", value=BUILD)
    ET.SubElement(r, "integer", id="db_random_id", value=str(rng.randint(1, 2 ** 31 - 1)))
    ET.SubElement(r, "integer", id="odvl", value=NON_PLAYER)
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input")
    ap.add_argument("output")
    a = ap.parse_args()
    rng = random.Random(20260917)

    tree = ET.parse(a.input)
    dbc = tree.getroot().find('list[@id="db_changes"]')
    records = list(dbc)

    # keep the file's order, but for each person hoist his type change to where
    # his first change is; an ADDR row is not a person change and stays put
    order, seen = [], {}
    for r in records:
        t = r.find('integer[@id="database_table_type"]')
        u = r.find('large[@id="db_unique_id"]')
        if t is None or u is None or t.get("value") != "1":
            order.append((None, r)); continue
        uid = u.get("value")
        seen.setdefault(uid, [])
        seen[uid].append(r)
        order.append((uid, r))

    moved = added = 0
    out, done = [], set()
    for uid, r in order:
        if uid is None:
            out.append(r); continue
        if uid in done:
            p = r.find('unsigned[@id="property"]')
            if p is not None and p.get("value") == PTYP:
                continue                      # already hoisted
            out.append(r); continue
        done.add(uid)
        group = seen[uid]
        types = [x for x in group if (x.find('unsigned[@id="property"]') is not None
                                      and x.find('unsigned[@id="property"]').get("value") == PTYP)]
        if types:
            if group[0] is not types[0]:
                moved += 1
            out.extend(types)
        else:
            out.append(type_op(uid, rng)); added += 1
        out.append(r) if r not in types else None

    dbc[:] = out
    tree.write(a.output, encoding="unicode", xml_declaration=False)
    print("people whose type change was moved to the front: %d" % moved)
    print("people given a type change they lacked: %d" % added)
    print("changes: %d -> %s" % (len(dbc), a.output))


if __name__ == "__main__":
    main()
