"""Replay a person's club spells (`Pnph`) the way the editor applies them.

`probe_editor_replay` models the playing-history grid only: its snapshot
matching knows year/apps/goals, not a spell's team/join/left/tjob, so it
drops every Pnph cell op - on the Portugal rebuilt records too, which import
fine. This is the same cell-op replay keyed on the spell snapshot.
"""
import xml.etree.ElementTree as ET

JOIN, LEFT, TEAM = "1785686382", "1818584692", "1952801133"
DAYS_TEAM = "1416914273"
EMPTY = (1, 1, 1900)


def _date(el):
    return (int(el.get("day")), int(el.get("month")), int(el.get("year")))


def _team(el):
    """The club DBID a value or snapshot names, or None."""
    if el is None or el.tag == "null":
        return None
    t = el.find("*[@id='Ttea']")
    if t is None:
        return None
    n = int(t.get("value"))
    return n // 4294967297 if n >= 4294967297 else n


def _snapshot(olvl):
    return {"team": _team(olvl.find("*[@id='team']")),
            "join": _date(olvl.find("date[@id='join']")),
            "left": _date(olvl.find("date[@id='left']")),
            "tjob": int(olvl.find("*[@id='tjob']").get("value"))}


def replay_spells(path, uid, prop_id):
    """(rows, dropped) for one person's Pnph ops, in file order."""
    rows, dropped = [], []
    lst = ET.parse(path).getroot().find(".//list[@id='db_changes']")
    for rec in lst:
        if rec.find("large[@id='db_unique_id']").get("value") != str(uid):
            continue
        if rec.find("unsigned[@id='property']").get("value") != str(prop_id):
            continue
        nv = rec.find("record[@id='new_value']")
        op = int(nv.find("integer[@id='lsop']").get("value"))
        if op == 3:
            rows = []
            continue
        if op == 0:
            rows.append({"team": None, "join": EMPTY, "left": EMPTY, "tjob": 11})
            continue
        snap = _snapshot(nv.find("record[@id='olvl']"))
        hit = [r for r in rows if r == snap]
        if not hit:
            dropped.append(snap)
            continue
        row = hit[0]
        if op == 2:
            rows.remove(row)
            continue
        col = nv.find("unsigned[@id='id']").get("value")
        val = nv.find("*[@id='value']")
        if col == TEAM:
            row["team"] = _team(val)
        elif col == JOIN:
            row["join"] = _date(val)
        elif col == LEFT:
            row["left"] = _date(val)
    return rows, dropped


def check_spells(path, uid, prop_id, expected):
    """Compare the replayed spells with the model's shifted spells: a list of
    {club, join, left(None = open)}. Returns a list of problem lines."""
    rows, dropped = replay_spells(path, uid, prop_id)
    got = sorted((r["team"], r["join"], None if r["left"] == EMPTY else r["left"]) for r in rows)
    want = sorted((s["club"], s["join"], s["left"]) for s in expected)
    problems = ["dropped op, snapshot matched no row: %s" % d for d in dropped]
    if got != want:
        problems.append("replayed spells differ from the model:\n  got  %s\n  want %s" % (got, want))
    return problems


def check_days(path, uid, prop_id, expected):
    """Replay the days-at-club/nation grid (`Pdcn`) the same way, keyed on its
    (team, days) snapshot, and compare with `expected` [(team, days)]."""
    rows, dropped = [], []
    lst = ET.parse(path).getroot().find(".//list[@id='db_changes']")
    for rec in lst:
        if rec.find("large[@id='db_unique_id']").get("value") != str(uid):
            continue
        if rec.find("unsigned[@id='property']").get("value") != str(prop_id):
            continue
        nv = rec.find("record[@id='new_value']")
        op = int(nv.find("integer[@id='lsop']").get("value"))
        if op == 3:
            rows = []
            continue
        if op == 0:
            rows.append({"team": None, "days": 1})
            continue
        o = nv.find("record[@id='olvl']")
        snap = {"team": _team(o.find("*[@id='Ttea']")), "days": int(o.find("*[@id='days']").get("value"))}
        hit = [r for r in rows if r == snap]
        if not hit:
            dropped.append(snap)
            continue
        val = nv.find("*[@id='value']")
        if nv.find("unsigned[@id='id']").get("value") == DAYS_TEAM:
            hit[0]["team"] = _team(val)
        else:
            hit[0]["days"] = int(val.get("value"))
    problems = ["Pdcn dropped op, snapshot matched no row: %s" % d for d in dropped]
    got = sorted((r["team"], r["days"]) for r in rows)
    if got != sorted(expected):
        problems.append("replayed days differ from the model:\n  got  %s\n  want %s" % (got, sorted(expected)))
    return problems
