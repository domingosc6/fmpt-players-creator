"""Editor-faithful replay of a person's history grid, INCLUDING lsop=4.

`clean_import.replay` is the converter's reader and deliberately does not model
the editor's Duplicate button: it finds the cited row and appends nothing. That
is fine for reading a career, but it cannot verify one - the author builds most
created careers by duplicating a row and relabelling the copy (Ahmed Ziad's
whole career is 1 insert + 8 duplicates), so a simulation without it silently
loses every duplicated season.

What the editor does, as far as the file shows:
  lsop 3  Clear      - drop every row
  lsop 0  Add        - append one blank row
  lsop 4  Duplicate  - append a COPY of the row the snapshot cites
  lsop 2  Remove     - delete the row the snapshot cites
  lsop 1  set cell   - write one column on the row the snapshot cites
and a snapshot is resolved to the FIRST row that matches it. An op whose
snapshot matches nothing is DROPPED, in silence - that is the failure this
script exists to find.

A duplicate leaves two identical rows, so the next op citing that state resolves
to the FIRST of the pair - the original, not the copy. That is not a bug: the
pair are interchangeable, and the values land on one of them either way.
"""
import copy
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import convert_edition as c
import clean_import as ci


def replay(recs, verbose=False):
    """(rows, dropped) - dropped is the ops whose snapshot matched no row."""
    rows, dropped = [], []
    for i, rec in enumerate(recs):
        lsop, col, val, st = c.parse_op(rec)
        if lsop == "3":
            rows = []
            continue
        if lsop == "0":
            rows.append(ci.new_row())
            continue
        cands = [r for r in rows if st is None or ci.snap_matches(r, st, strict_stats=True)]
        if not cands:
            cands = [r for r in rows if st is None or ci.snap_matches(r, st)]
        row = cands[-1] if cands else None
        if row is None:
            dropped.append((i, lsop, col))
            if verbose:
                print(f"    op {i} (lsop={lsop}) matched NO row -> dropped")
            continue
        if lsop == "4":
            rows.append(copy.deepcopy(row))
            continue
        if lsop == "2":
            rows.remove(row)
            continue
        name = {v: k for k, v in ci.COL.items()}.get(col)
        if name is None:
            continue
        if val is None or val.tag == "null":
            row[name] = None
        elif val.tag == "record":
            # `club_el_from` builds a reference from a SNAPSHOT's (kind, value)
            # pair - a cell op already holds the record, so copy it, exactly as
            # clean_import.replay does
            row[name] = copy.deepcopy(val)
        elif val.tag == "date":
            row[name] = copy.deepcopy(val)
        elif val.tag == "boolean":
            row[name] = val.get("value") == "true"
        else:
            v = val.get("value")
            if v is None:
                row[name] = None
            else:
                try:
                    row[name] = int(v)
                except ValueError:
                    try:
                        row[name] = float(v)       # a fee comes as "0.000000"
                    except ValueError:
                        row[name] = v
    return rows, dropped


def grid(path, ids, prop="Plhs"):
    ids = set(ids)
    root = ET.parse(path).getroot()
    return [r for r in root.find('list[@id="db_changes"]')
            if r.find('large[@id="db_unique_id"]') is not None
            and r.find('large[@id="db_unique_id"]').get("value") in ids
            and c.rec_prop(r) == prop]


def show(path, ids, prop="Plhs", label=""):
    import fm_names
    nm = fm_names.Names(offline=True)
    recs = grid(path, ids, prop)
    rows, dropped = replay(recs)
    print(f"=== {label or path}: {len(recs)} ops -> {len(rows)} rows, {len(dropped)} dropped")
    for r in sorted(rows, key=lambda r: (r["year"] or 0, r["yror"] or 0)):
        club = ci.club_key(r)
        print(f"     {r['year']}  {(nm.club(club) or club or '-'):32} "
              f"apps={r['apps']} gols={r['gols']} youth={r['ytht']}")
    return rows, dropped


if __name__ == "__main__":
    show(sys.argv[1], sys.argv[2:])
