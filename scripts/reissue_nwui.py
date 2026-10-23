"""Re-issue `nwui` on every created-record ADDR row.

WHY (Totti, 2026-09-10, confirmed by single-variable probe): a created person's
ADDR carries `<integer id="nwui">`. When that value collides with something in
FM26's own database the GAME silently declines to add the record - the editor
shows it perfectly, because the editor only replays the changelist. Totti's
2000067971 was such a value; Rocca's adjacent 2000067975 loads. Changing only
nwui, with his original uid and all 228 ops untouched, fixed him.

The deliverable forwards whatever the author's editor allocated, across sessions
that each restarted their own counter: 2682 ADDR rows carry just 1041 distinct
nwui values, spread over seven bands from 7 to 2082082530. So re-issue the lot.

  * keyed by the record's uid, so a person created in more than one file gets
    one value everywhere (today no uid is created twice, but do not rely on it)
  * assigned in sorted-uid order from BASE, contiguous, one per person
  * BASE + count stays under 2**31, because a value past the signed boundary
    breaks records outright (learned the hard way with the uid's high half)
  * nothing else is touched: uid, ops, version, db_random_id all stay

VALIDATE THE BLOCK FIRST with --validate, which writes a single probe file
carrying a spread of records across the intended range. Import it, confirm every
person in it appears in a save, and only then run for real.
"""
import argparse
import copy
import glob
import os
import re
import xml.etree.ElementTree as ET

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "FM 26 XML Files")
DELIV = f"{ROOT}/final_xmls"
BASE = 2_100_000_000
ADDR_PROP = "1094992978"
SIGNED_MAX = 2 ** 31


def is_addr(rec):
    el = rec.find('unsigned[@id="property"]')
    return el is not None and el.get("value") == ADDR_PROP


def addr_uid(rec):
    nv = rec.find('record[@id="new_value"]')
    if nv is None:
        return None
    el = nv.find('large[@id="db_unique_id"]')
    return el.get("value") if el is not None else None


def created_uids(files):
    """every uid an ADDR row creates, across all files, sorted for determinism"""
    pat = re.compile(r'<large id="db_unique_id" value="(-?\d+)" />\s*<integer id="nwui"')
    uids = set()
    for f in files:
        uids |= set(pat.findall(open(f, encoding="utf-8", errors="replace").read()))
    return sorted(uids, key=int)


def build_map(files):
    uids = created_uids(files)
    assert BASE + len(uids) < SIGNED_MAX, "block crosses the signed-32 boundary"
    return {u: BASE + i for i, u in enumerate(uids)}, uids


def apply_to(path, mapping, out_dir):
    """Byte-precise substitution: rewrite the nwui of each ADDR row and nothing
    else. The uid+nwui pair below occurs ONLY inside an ADDR new_value block
    (2682 matches across the deliverable = the exact ADDR count), so no XML
    round-trip is needed and every other byte of the file is preserved."""
    src = open(path, encoding="utf-8", errors="replace").read()
    pat = re.compile(r'(<large id="db_unique_id" value="(-?\d+)" />\s*'
                     r'<integer id="nwui" value=")(\d+)(" />)')
    n = 0
    def sub(m):
        nonlocal n
        u = m.group(2)
        if u not in mapping:
            return m.group(0)
        n += 1
        return m.group(1) + str(mapping[u]) + m.group(4)
    out_text = pat.sub(sub, src)
    out = os.path.join(out_dir, os.path.basename(path))
    open(out, "w", encoding="utf-8").write(out_text)
    # nothing but the nwui digits may have moved
    assert len(out_text.splitlines()) == len(src.splitlines()), path
    return n


def validate(mapping, uids, out_dir, sample=12):
    """one file, a spread of created people across the block, own uids kept"""
    src = f"{DELIV}/FMPT Legends - Italy - target2025 - clean.xml"
    italy = created_uids([src])          # sorted, so the picks spread across the block
    step = max(1, len(italy) // sample)
    picks = italy[::step][:sample]
    totti = "883954140297461171"
    if totti not in picks:
        picks[-1] = totti
    tree = ET.parse(src)
    changes = tree.getroot().find('list[@id="db_changes"]')
    keep = []
    for rec in changes:
        u = addr_uid(rec) if is_addr(rec) else (
            rec.find('large[@id="db_unique_id"]').get("value")
            if rec.find('large[@id="db_unique_id"]') is not None else None)
        if u in picks:
            r = copy.deepcopy(rec)
            if is_addr(r):
                r.find('record[@id="new_value"]/integer[@id="nwui"]').set("value", str(mapping[u]))
            keep.append((u, r))
    for rec in list(changes):
        changes.remove(rec)
    for _, r in keep:
        changes.append(r)
    out = os.path.join(out_dir, "TEST - BLOCK validate 12 created players.xml")
    tree.write(out, encoding="utf-8", xml_declaration=False)
    print(f"  {os.path.basename(out)}: {len(keep)} ops, {len(picks)} people")
    for u in picks:
        print(f"    uid {u:>20}  nwui {mapping[u]}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--restyle", action="store_true",
                    help="drop nwui entirely (the shape convert_edition.py now emits) "
                         "instead of renumbering - no field left to collide")
    ap.add_argument("--out", default=f"{ROOT}/probes")
    a = ap.parse_args()
    files = sorted(glob.glob(f"{DELIV}/*.xml"))
    mapping, uids = build_map(files)
    print(f"{len(uids)} created records -> nwui {BASE}..{BASE + len(uids) - 1} "
          f"(ceiling {SIGNED_MAX}, headroom {SIGNED_MAX - (BASE + len(uids)):,})")
    if a.restyle:
        os.makedirs(a.out, exist_ok=True)
        pat = re.compile(r'(<large id="db_unique_id" value=")-?\d+(" />\s*'
                         r'<unsigned id="property" value="1094992978" />\s*'
                         r'<record id="new_value">\s*)'
                         r'(?:<unsigned id="id" value="\d+" />\s*)?'
                         r'(<integer id="database_table_type" value="1" />\s*'
                         r'<unsigned id="dcty" value="\d+" />\s*'
                         r'<large id="db_unique_id" value="-?\d+" />\s*)'
                         r'<integer id="nwui" value="\d+" />\s*')
        tot = 0
        for f in files:
            src = open(f, encoding="utf-8", errors="replace").read()
            out, n = pat.subn(lambda m: m.group(1) + "4294967297" + m.group(2) + m.group(3), src)
            open(os.path.join(a.out, os.path.basename(f)), "w", encoding="utf-8").write(out)
            tot += n
            print(f"  {os.path.basename(f)[15:-24]:26} {n:>5} ADDR rows restyled")
        print(f"total {tot} rows restyled into {a.out}")
    elif a.validate:
        validate(mapping, uids, a.out)
    else:
        os.makedirs(a.out, exist_ok=True)
        tot = 0
        for f in files:
            n = apply_to(f, mapping, a.out)
            tot += n
            print(f"  {os.path.basename(f)[15:-24]:26} {n:>5} ADDR rows re-issued")
        print(f"total {tot} rows rewritten into {a.out}")
