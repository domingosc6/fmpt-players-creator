#!/usr/bin/env python3
"""
FMPT Legends - playing-history cleaner for created players (v1).

Why. Careers were typed into the editor as one row copied N times and the
copies relabelled one by one, then touched up again in later editions. On
replay the editor resolves each op by its old-value snapshot to the FIRST row
that fits, so the same row gets relabelled repeatedly while the copies stay as
identical junk rows, later ops miss, and blank 1900 rows (used as scratch
values) survive. The grid you see is scrambled; the changeset is bloated.

What. For every CREATED player (ADDR, dcty=2) the career is recomputed from the
changeset by literal replay of every playing-history op on every id linked to
that person (authoring order records intent even when the editor scrambles it).
Then the rules: drop 1900/2100 rows; drop exact duplicates (year, club, apps,
goals); keep the on-loan flag; place each transfer fee on the last season of
the spell at the club it was paid for; flag same year + club with different stats; flag gaps in a run of
seasons; set the youth flag on empty seasons at 18 or under; keep the row ORDER
(`yror`) of shared seasons and assign 1, 2 when the author left it unset (the
spell with a leaving date first). Finally ALL old
playing-history ops of that person are removed and one fresh minimal sequence is
written under the primary id: insert row, fill every cell of that row, next row,
in ascending year order, never duplicating, never relabelling. Each op targets
the newest row, so index-based and snapshot-based matching agree and the grid is
exactly what is emitted. A created record has no rows in the FM database, so
nothing needs deleting.

Out of scope: existing DB records (their rows live in the database), staff, the
club-spells grid (Pnph) - same disease, next step.

PREFERRED ENTRY POINT: convert_edition.py --rebuild-careers, which runs this
module's replay/clean/emit inside the converter, on the SOURCE file, with the
converter's own person grouping and an anchor read from the rebuilt rows. The
standalone CLI below re-links ids on an already converted file and can group
differently (Shilton/Collins incident, 2026-09-03); keep it for experiments only.

Usage:
    clean_import.py INPUT.xml OUTPUT.xml [--report FILE.md] [--only NAME ...]
"""
import argparse
import copy
import random
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

import convert_edition as c

PLHS_PROP = 1349281907
ROW_ID = "1853322860"          # new_value id for row-level ops (insert)
OLVL_ID = "1869379180"
VAL_ID = "1986096245"
COL = {"year": "2036687218", "yror": "2037542770", "club": "1668049252", "divi": "1684633193",
       "apps": "1634758771", "gols": "1735355507", "ytht": "2037672052",
       "join": "1785686382", "leaving": "1818583414",
       "onln": "1869507694", "cash": "1667330920"}
SENT = {1900, 2100}


# ------------------------------------------------------------- replay -------

def blank_row():
    return {"year": 1900, "yror": 0, "club": None, "divi": None, "apps": None, "gols": None,
            "ytht": False, "onln": False, "cash": None, "join": None, "leaving": None}


def new_row():
    """A row as the EDITOR adds it: appearances and goals are 0, NOT blank.

    That is what its own snapshots say - a cell op on a fresh row cites "apps 0,
    gols 0" - and telling 0 apart from a nulled figure is what decides which row a
    DUPLICATE copies. Modelled as blank, a snapshot citing 0 matched the author's
    youth row (whose figures he had explicitly nulled) instead of the fresh one, so
    every later op on it landed on the wrong row: Litos came out youth in four
    senior seasons and short of three divisions, and Jose Tavares got the youth
    tick on seven rows and his divisions in the wrong order (user, 2026-09-08).

    `_set` remembers which figures an op actually wrote, so a season the author
    left alone is still emitted BLANK - his rule that an empty season carries no
    figures while a recorded 0/0 is a real season."""
    r = blank_row()
    r["apps"] = 0
    r["gols"] = 0
    r["_set"] = set()
    return r


def row_state(row):
    """Normalised view used for snapshot matching (club by value, kind-agnostic)."""
    club = None
    if row["club"] is not None:
        t = row["club"].find('*[@id="Ttea"]')
        club = c.team_dbid(t) if t is not None else None
    return {"year": row["year"], "apps": row["apps"], "gols": row["gols"], "club": club,
            "join": c.dtup(row["join"]) if row["join"] is not None else c.NULL_DATE,
            "left": c.dtup(row["leaving"]) if row["leaving"] is not None else c.NULL_DATE}


def snap_matches(row, st, strict_stats=False):
    """Does this row match the snapshot? `strict_stats` tells a blank stat apart
    from a zero, which is normally NOT safe (see below) but decides which of two
    otherwise identical rows an op means - `replay` tries it first."""
    rs = row_state(row)
    for k, v in st.items():
        if k == "club":
            if v is None:
                if rs["club"] is not None:
                    return False
            elif rs["club"] != v[1]:
                # same club under the other id kind (integer DBID vs large id)
                # is not comparable offline: treat as a wildcard, as the editor
                # resolves both to the club (Phil Neal: FM24 pass on FM17 rows)
                if row["club"] is not None and row["club"].find('*[@id="Ttea"]').tag != v[0]:
                    continue
                return False
        elif k in ("apps", "gols"):
            # snapshots write 0 for a blank stat (FM24) or null (older editors):
            # blank and 0 are indistinguishable in a snapshot, so match them alike
            #
            # ... except when that is the only thing telling two rows apart. Litos
            # is built by ticking Youth on a row, NULLING its apps and goals, and
            # later duplicating a FRESH Boavista row whose stats are 0 - and the
            # snapshot for those duplicates says 0, not blank. Matched loosely, the
            # first row that fits is the youth one, so four senior seasons came out
            # ticked Youth; the editor takes the row whose stats are exactly 0.
            # `replay` therefore asks for an exact match first and only then falls
            # back to this (user's FM18 grid, 2026-09-08).
            if strict_stats:
                if rs.get(k) != v:
                    return False
            elif (rs.get(k) or 0) != (v or 0):
                return False
        elif rs.get(k) != v:
            return False
    return True


def find_repeat(recs):
    """The op list with a verbatim adjacent repeat removed, or None if there is
    no such block. Detection only - whether the block IS a redundant save is
    `choose_repeat`'s question, and it needs the caller's reader to answer."""
    sig = [ET.tostring(r, encoding="unicode") for r in recs]
    n = len(sig)
    for L in range(n // 2, 4, -1):
        for i in range(0, n - 2 * L + 1):
            if sig[i:i + L] == sig[i + L:i + 2 * L]:
                return recs[:i + L] + recs[i + 2 * L:]
    return None


def strip_repeat(recs):
    """Back-compatible wrapper: (ops, doubled) with no verification. Prefer
    `choose_repeat`, which decides whether the cut is actually a repeat."""
    cut = find_repeat(recs)
    return (cut, True) if cut is not None else (recs, False)


def year_gaps(rows):
    """Missing seasons between a career's first and last. A hole is the loudest
    sign that an op list was cut in the wrong place: splicing the head of one
    editing pass onto the tail of another leaves every other row behind."""
    ys = sorted(r["year"] for r in rows if r.get("year"))
    if not ys:
        return 0
    return sum(1 for y in range(ys[0], ys[-1]) if y not in ys)


def _removes_only_duplicates(full, cut):
    """Is every row the cut dropped a copy of one it kept? That is what a list
    saved twice looks like - the second pass re-inserts rows the first already
    made - and it is the only case where losing rows is the right outcome."""
    def key(r):
        return (r.get("year"), club_key(r), r.get("apps"), r.get("gols"))

    kept = Counter(key(r) for r in cut)
    return all(k in kept for k in (Counter(key(r) for r in full) - kept))


def choose_repeat(recs, read):
    """(ops, doubled) - the op list to read a career from.

    Some records carry a whole editing pass twice, verbatim, and that repeat has
    to go. But the search is greedy on block length, and a long block that
    repeats INSIDE one pass is not a second save: cutting there splices the head
    of one pass onto the tail of another. So the cut is judged by the career it
    produces, never trusted:

      1. fewer HOLES wins - a missing season is the loudest sign of a bad cut,
         because a splice leaves every other row behind;
      2. on a tie, more seasons wins - removing a genuine repeat can let MORE ops
         resolve, not fewer (Thomas Finney: 155 ops read 8 seasons, the 100 left
         after the cut read all 16);
      3. and a cut that costs seasons is taken only when everything it drops
         duplicates something it keeps, which is exactly what a pass saved twice
         looks like.

    Measured false positives, all rejected by 1 and 3 - Milonja Djukic (14
    seasons down to 2), Bobby Tambling (18 to 7 with a hole), Ray Wilson (17
    consecutive years to every other one), Peter Bonetti (10 to 4). Each has two
    member ids written by two editor builds, with the repeat inside the older
    build's block where the author rebuilt the same rows the same way.

    `read(ops, doubled) -> rows` must be the SAME reader the caller will use.
    Judging with `replay` while the caller reads with `replay_best` picks the
    wrong list - that cost Dennis Wise a Chelsea season and gave him a third
    youth year instead.
    """
    cut = find_repeat(recs)
    if cut is None:
        return recs, False
    full_rows, cut_rows = read(recs, False), read(cut, True)
    gf, gc = year_gaps(full_rows), year_gaps(cut_rows)
    if gc != gf:
        return (cut, True) if gc < gf else (recs, False)
    if len(cut_rows) < len(full_rows) and not _removes_only_duplicates(full_rows, cut_rows):
        return recs, False
    return cut, True


def state_key(st):
    return (st.get("year"), st.get("apps") or 0, st.get("gols") or 0, st.get("club")[1] if st.get("club") else None)


def row_from_olvl(rec):
    """Full row rebuilt from an op's raw `olvl` snapshot. Used when the saving
    editor's pass cites a row the replay does not have: the snapshot carries the
    whole row the author was looking at - division, flags and dates included, not
    just year/apps/goals/club (John Barnes lost every division this way)."""
    row = blank_row()
    olvl = rec.find('*[@id="new_value"]/record[@id="olvl"]')
    if olvl is None:
        return row
    for ch in olvl:
        cid, tag = ch.get("id"), ch.tag
        if cid == "year":
            row["year"] = int(ch.get("value"))
        elif cid == "yror":
            row["yror"] = int(ch.get("value") or 0)
        elif cid in ("apps", "gols"):
            row[cid] = None if tag == "null" or ch.get("value") in (None, "") else int(ch.get("value"))
        elif cid == "column_id" and tag == "record":
            row["club"] = copy.deepcopy(ch)
        elif cid == "divi" and tag == "record":
            row["divi"] = copy.deepcopy(ch)
        elif cid == "ytht":
            row["ytht"] = ch.get("value") == "true"
        elif cid == "onln":
            row["onln"] = ch.get("value") == "true"
        elif cid == "cash" and tag != "null" and ch.get("value") not in (None, "", "0", "0.000000"):
            row["cash"] = copy.deepcopy(ch)
        elif cid in ("join", "leaving", "left") and tag == "date":
            key = "join" if cid == "join" else "leaving"
            row[key] = None if int(ch.get("year")) in SENT else copy.deepcopy(ch)
    return row


def club_el_from(kind_value):
    """Build a club reference record from a snapshot's (kind, value)."""
    el = ET.Element("record", id="value")
    ET.SubElement(el, kind_value[0], id="Ttea", value=kind_value[1])
    return el


def replay(recs, dup_only_deletes=False, doubled=False, want_matches=False, trusted_build=None, fee_log=None):
    """Literal replay of one person's Plhs ops (file order). First-match rows.
    doubled (op list was repeated verbatim): a delete is IGNORED when a later
    set-op cites exactly the state being deleted - the author's deletes were
    fighting the doubles and his later relabels prove the rows lived (Hollins).
    Never applied to normal lists: an author who retypes a career deletes the
    old rows and then recreates the same states (Hansen, Tommy Smith)."""
    parsed = [c.parse_op(rec) for rec in recs]
    later_sets = [set() for _ in parsed]
    if doubled:
        seen = set()
        for i in range(len(parsed) - 1, -1, -1):
            later_sets[i] = set(seen)
            lsop, col, val, st = parsed[i]
            if lsop == "1" and st is not None:
                seen.add(state_key(st))
    rows = []
    matched = [False] * len(parsed)
    touched = set()                                  # id(row) touched by the trusted pass
    for i, (lsop, col, val, st) in enumerate(parsed):
        build = c.rec_build(recs[i])
        if lsop == "2" and st is not None and state_key(st) in later_sets[i]:
            continue
        if lsop == "3":                  # editor "Clear": wipe the grid (Phil Neal, FM24 retype)
            rows = []
            matched[i] = True
            continue
        if lsop == "0":
            rows.append(new_row())
            matched[i] = True
            if trusted_build is not None and build == trusted_build:
                touched.add(id(rows[-1]))
            continue
        # Exact first - a blank stat is not a zero when it is what separates two
        # candidate rows - then the lenient match the editions require. Among equal
        # candidates take the LAST, not the first: Jose Tavares ticks Youth on his
        # first row, nulls its figures, builds a second row the same way and then
        # duplicates - and both rows match {blank, blank}. Taking the first spread
        # his one youth tick over seven seasons and shuffled his divisions; the
        # editor plainly takes the newer row, which is also what
        # `replay_spells_ops` has always done for the spells grid (`hits[-1]`).
        cands = [r for r in rows if st is None or snap_matches(r, st, strict_stats=True)]
        if not cands:
            cands = [r for r in rows if st is None or snap_matches(r, st)]
        row = cands[-1] if cands else None
        if row is None:
            if trusted_build is not None and build == trusted_build and lsop == "1" and st is not None:
                # the saving editor's author SAW this row: materialise it whole
                row = row_from_olvl(recs[i])
                rows.append(row)
            else:
                continue      # created record: no DB rows exist, an unmatched op is simply lost
        matched[i] = True
        if trusted_build is not None and build == trusted_build:
            touched.add(id(row))
        if lsop == "2":
            if dup_only_deletes and not any(q is not row and row_state(q) == row_state(row) for q in rows):
                continue
            rows.remove(row)
        elif lsop == "4":
            dup = copy.deepcopy(row)
            dup["cash"] = None            # a fee belongs to one transfer; copies never inherit it (Ferdinand)
            rows.append(dup)
            if trusted_build is not None and build == trusted_build:
                touched.add(id(rows[-1]))
        elif lsop == "1":
            if col == COL["year"]:
                row["year"] = int(val.get("value")) if val is not None and val.get("value") else 1900
            elif col == COL["yror"]:
                row["yror"] = int(val.get("value")) if val is not None and val.get("value") else 0
            elif col == COL["apps"]:      # null value = cleared (blank); "0" = recorded 0
                row["apps"] = int(val.get("value")) if val is not None and val.tag != "null" and val.get("value") not in (None, "") else None
                if "_set" in row:
                    row["_set"].add("apps")
            elif col == COL["gols"]:
                row["gols"] = int(val.get("value")) if val is not None and val.tag != "null" and val.get("value") not in (None, "") else None
                if "_set" in row:
                    row["_set"].add("gols")
            elif col == COL["club"]:
                row["club"] = copy.deepcopy(val) if val is not None and val.tag == "record" else None
            elif col == COL["divi"]:
                row["divi"] = copy.deepcopy(val) if val is not None and val.tag == "record" else None
            elif col == COL["ytht"]:
                row["ytht"] = val is not None and val.get("value") == "true"
            elif col == COL["onln"]:
                row["onln"] = val is not None and val.get("value") == "true"
            elif col == COL["cash"]:
                # a fee is a statement about the row AS THE AUTHOR SAW IT; row
                # identities drift under first-match replay, so fees are re-attached
                # after the rebuild from these statements (see clean)
                if fee_log is not None and val is not None and val.tag != "null" and val.get("value") not in (None, "0", "0.000000"):
                    fee_log.append({"year": st.get("year"), "apps": st.get("apps"), "gols": st.get("gols"),
                                    "club": st.get("club")[1] if st.get("club") else None, "cash": copy.deepcopy(val)})
            elif col == COL["join"]:
                row["join"] = copy.deepcopy(val) if val is not None and val.tag == "date" and int(val.get("year")) not in SENT else None
            elif col in c.LEAVE_COLS:
                row["leaving"] = copy.deepcopy(val) if val is not None and val.tag == "date" and int(val.get("year")) not in SENT else None
    if trusted_build is not None and touched and any(c.rec_build(r) == trusted_build for r in recs):
        # rows the trusted pass never touched are stale when the author retyped
        # the same club/apps/goals elsewhere (his view was the editor's scramble)
        def club_kind(r):
            return r["club"].find('*[@id="Ttea"]').tag if r["club"] is not None else None
        tkeys = [(row_state(r)["club"], club_kind(r), r["apps"], r["gols"]) for r in rows if id(r) in touched]

        def retyped(r):
            cl, kd = row_state(r)["club"], club_kind(r)
            for tcl, tkd, a, g in tkeys:
                if (a or 0, g or 0) == (r["apps"] or 0, r["gols"] or 0) and (tcl == cl or (tkd != kd and tcl is not None and cl is not None)):
                    return True   # same stats at the same club, or at a club named under the other id kind
            return False
        rows = [r for r in rows if id(r) in touched or not retyped(r)]
    return (rows, matched) if want_matches else rows


def replay_best(recs, doubled=False, trusted_build=None, fee_log=None):
    """Replay choosing which INTERMEDIATE passes (edition builds) the editor had
    applied. The author's last pass cites the states he saw; the subset of
    earlier passes that lets the most of its ops match is the one that was live
    (Tommy Smith: FM18 renumbering never showed in FM24, the FM24 rework cites
    FM16 states). First and last pass always apply. Returns (rows, skipped builds)."""
    import itertools
    builds = []
    for rec in recs:
        b = c.rec_build(rec)
        if b not in builds:
            builds.append(b)
    if len(builds) <= 2:
        return replay(recs, doubled=doubled, trusted_build=trusted_build, fee_log=fee_log), []
    middle = builds[1:-1]
    best = None
    for k in range(len(middle), -1, -1):                 # prefer keeping more passes
        for keep in itertools.combinations(middle, k):
            chosen = {builds[0], builds[-1], *keep}
            ops = [r for r in recs if c.rec_build(r) in chosen]
            log = []
            rows, matched = replay(ops, doubled=doubled, want_matches=True, trusted_build=trusted_build, fee_log=log)
            score = sum(1 for r, m in zip(ops, matched) if m and c.rec_build(r) == builds[-1])
            if best is None or score > best[0]:
                best = (score, rows, [b for b in middle if b not in keep], log)
    if fee_log is not None:
        fee_log.extend(best[3])
    return best[1], best[2]


# -------------------------------------------------------------- rules -------

def fmt_stat(v):
    return "-" if v is None else str(v)


def club_key(row):
    s = row_state(row)
    return s["club"]


def assign_fees(out, fee_log, notes):
    """Place the author's transfer fees on the career the rebuild produced.

    A fee op cites the row AS IT WAS when the author typed it, and row states
    drift under first-match replay, so the snapshot is not a usable key on its
    own (Ferdinand, Rowley). Two things it does say reliably: which CLUB the fee
    was paid for, and - through repeated ops on the same snapshot - what the
    author's FINAL figure was (Diouf, Muamba: a mistyped fee corrected twice).
    The project rule then decides the row: a fee sits on the LAST season of that
    club's spell, i.e. the season the player left. A loan spell elsewhere does
    not end the parent spell, and a loan row never carries a fee. Where a club
    has several spells, the fee goes to the spell whose last season matches the
    statement's apps/goals, else the one covering its year, else the last one."""
    if not fee_log:
        return
    # successive ops on one snapshot are corrections: keep the last figure
    final = {}
    for f in fee_log:
        final[(f["club"], f["year"], f["apps"], f["gols"])] = f
    perm = [r for r in out if not r["onln"]]
    spells_by_club = defaultdict(list)
    i = 0
    while i < len(perm):
        j = i
        while j + 1 < len(perm) and club_key(perm[j + 1]) == club_key(perm[i]):
            j += 1
        spells_by_club[club_key(perm[i])].append(perm[i:j + 1])
        i = j + 1
    by_club = defaultdict(list)
    for f in final.values():
        by_club[f["club"]].append(f)
    for cl, fees in by_club.items():
        spells = list(spells_by_club.get(cl, []))
        fees.sort(key=lambda f: (f["year"] is None, f["year"]))
        if len(fees) > len(spells):
            extra, fees = fees[:len(fees) - len(spells)], fees[len(fees) - len(spells):]
            for f in extra:
                notes.append(f"FLAG transfer fee {f['cash'].get('value')} for club {cl} has no spell to sit on")
        for f in fees:
            pick = next((sp for sp in spells
                         if (sp[-1]["apps"] or 0) == (f["apps"] or 0) and (sp[-1]["gols"] or 0) == (f["gols"] or 0)), None)
            if pick is None:
                pick = next((sp for sp in spells
                             if f["year"] is not None and sp[0]["year"] <= f["year"] <= sp[-1]["year"]), None)
            if pick is None:
                pick = spells[-1]
            spells.remove(pick)
            pick[-1]["cash"] = f["cash"]
            notes.append(f"transfer fee {f['cash'].get('value')} placed on the last season at club {cl} ({pick[-1]['year']})")


def clean(rows, dob_year, fee_log=None):
    """Apply the cleaning rules; returns (rows, notes)."""
    notes = []
    kept = [r for r in rows if r["year"] not in SENT]
    if len(kept) != len(rows):
        notes.append(f"dropped {len(rows) - len(kept)} blank row(s) with year 1900/2100")
    seen, out = set(), []
    for r in sorted(kept, key=lambda r: (r["year"], club_key(r) or "", -(r["apps"] or 0), -(r["gols"] or 0))):
        k = (r["year"], club_key(r), r["apps"], r["gols"])
        if k in seen:
            notes.append(f"dropped exact duplicate {r['year']} club {club_key(r)} {r['apps']}/{r['gols']}")
            continue
        seen.add(k)
        out.append(r)
    by_yc = defaultdict(list)
    for r in out:
        by_yc[(r["year"], club_key(r))].append(r)
    for (y, cl), rs in by_yc.items():
        if len(rs) > 1 and not any(r["onln"] for r in rs):   # loan then permanent deal is legitimate
            notes.append(f"FLAG same season {y} at club {cl} with different stats: "
                         + ", ".join(f"{fmt_stat(r['apps'])}/{fmt_stat(r['gols'])}" for r in rs))
    out.sort(key=lambda r: (r["year"], r["yror"], club_key(r) or ""))
    by_year = defaultdict(list)
    for r in out:
        by_year[r["year"]].append(r)
    for y, rs in by_year.items():
        clubs = {club_key(r) for r in rs}
        if len(rs) < 2 or len(clubs) < 2:
            continue
        missing = [r for r in rs if r["yror"] == 0]
        if missing:
            # shared season with (some) order unset: the spell that ends first
            # comes first; unset rows take the smallest free numbers in that order
            def sort_key(r):
                left = r["leaving"] is not None
                join = r["join"] is not None
                # spell that ends first, then a loan before the permanent deal at the same club
                return (0 if left else (2 if join else 1), 0 if r["onln"] else 1, out.index(r))
            used = {r["yror"] for r in rs if r["yror"]}
            nxt = 1
            for r in sorted(missing, key=sort_key):
                while nxt in used:
                    nxt += 1
                r["yror"] = nxt
                used.add(nxt)
            notes.append(f"order assigned for shared season {y}: " + ", ".join(f"{club_key(r)}={r['yror']}" for r in rs))
        if len({r["yror"] for r in rs}) < len(rs):
            notes.append(f"FLAG shared season {y} with duplicate order values: " + ", ".join(f"{club_key(r)}={r['yror']}" for r in rs))
    out.sort(key=lambda r: (r["year"], r["yror"], club_key(r) or ""))
    if fee_log is not None:
        assign_fees(out, fee_log, notes)
    years = sorted({r["year"] for r in out})
    gaps = [(a, b) for a, b in zip(years, years[1:]) if b - a > 1]
    for a, b in gaps:
        notes.append(f"FLAG gap between {a} and {b}")
    for r in out:
        # a season with apps recorded but no goals figure is a 0-goal season (and vice versa)
        if r["apps"] is not None and r["gols"] is None:
            r["gols"] = 0
        elif r["gols"] is not None and r["apps"] is None:
            r["apps"] = 0
    if dob_year is not None:
        for r in out:
            # an EMPTY season has no figures at all; a recorded 0/0 is a real season
            if not r["ytht"] and r["apps"] is None and r["gols"] is None and r["year"] - dob_year <= 18:
                r["ytht"] = True
                notes.append(f"youth flag set on {r['year']} (age {r['year'] - dob_year}, no apps recorded)")
    return out, notes


# ------------------------------------------------------------ emission ------

def copy_ref_payload(dst, ref, key_only=False):
    """Copy a club/competition reference. VALUES keep every part the source had
    (FM24 refs carry the large unique id AND the integer DBID). SNAPSHOTS (olvl)
    keep only the key part (Ttea / competition), which is what the editor writes
    and compares - a DBID inside a snapshot makes every later op on the row miss
    (Grobbelaar: club set, division/apps/dates lost)."""
    for ch in ref:
        if ch.get("id") == "id":
            continue
        if key_only and ch.get("id") not in ("Ttea", "competition"):
            continue
        dst.append(copy.deepcopy(ch))


def sub(parent, tag, **attrs):
    e = ET.SubElement(parent, tag)
    for k, v in attrs.items():
        e.set(k, str(v))
    return e


def olvl_for(row):
    o = ET.Element("record", id="olvl")
    sub(o, "unsigned", id="id", value=OLVL_ID)
    sub(o, "integer", id="year", value=row["year"])
    sub(o, "integer", id="yror", value=row["yror"])
    if row["club"] is not None:
        cid = sub(o, "record", id="column_id")
        sub(cid, "unsigned", id="id", value=COL["club"])
        copy_ref_payload(cid, row["club"], key_only=True)
    else:
        sub(o, "null", id="column_id")
    sub(o, "boolean", id="onln", value="true" if row["onln"] else "false")
    sub(o, "boolean", id="trib", value="false")
    sub(o, "boolean", id="ytht", value="true" if row["ytht"] else "false")
    if row["apps"] is not None:
        sub(o, "unsigned", id="apps", value=row["apps"])
    else:
        sub(o, "null", id="apps")
    if row["gols"] is not None:
        sub(o, "unsigned", id="gols", value=row["gols"])
    else:
        sub(o, "null", id="gols")
    if row["cash"] is not None:
        sub(o, row["cash"].tag, id="cash", value=row["cash"].get("value"))
    else:
        sub(o, "null", id="cash")
    if row["divi"] is not None:
        d = sub(o, "record", id="divi")
        sub(d, "unsigned", id="id", value=COL["divi"])
        copy_ref_payload(d, row["divi"], key_only=True)
    else:
        sub(o, "null", id="divi")
    sub(o, "null", id="info")
    sub(o, "integer", id="hsfl", value=0)
    for f in ("join", "leaving"):
        d = row[f]
        if d is not None:
            sub(o, "date", id=f, day=d.get("day"), month=d.get("month"), year=d.get("year"), time="0")
        else:
            sub(o, "date", id=f, day=1, month=1, year=1900, time=0)
    return o


def wrap(uid, new_value, build):
    rec = ET.Element("record")
    sub(rec, "integer", id="database_table_type", value=1)
    sub(rec, "large", id="db_unique_id", value=uid)
    sub(rec, "unsigned", id="property", value=PLHS_PROP)
    rec.append(new_value)
    sub(rec, "integer", id="version", value=build)
    sub(rec, "integer", id="db_random_id", value=random.randint(1, 2**31 - 1))
    return rec


def emit_rows(uid, rows, build):
    """Fresh op sequence: CLEAR the grid, then insert and fill each row in turn.
    The Clear is harmless on a truly new record and protects against a created
    id that collides with a player added to a later database (Portugal: Mito's
    grid in FM26 showed a real lower-league player's seasons under his rows)."""
    ops = []
    nv = ET.Element("record", id="new_value")
    sub(nv, "unsigned", id="id", value=ROW_ID)
    sub(nv, "integer", id="lsop", value=3)
    ops.append(wrap(uid, nv, build))
    for row in sorted(rows, key=lambda r: (r["year"], r["yror"], club_key(r) or "")):
        nv = ET.Element("record", id="new_value")
        sub(nv, "unsigned", id="id", value=ROW_ID)
        sub(nv, "integer", id="lsop", value=0)
        ops.append(wrap(uid, nv, build))
        cur = blank_row()

        def set_cell(colkey, value_el, apply):
            nv = ET.Element("record", id="new_value")
            sub(nv, "unsigned", id="id", value=COL[colkey])
            nv.append(value_el)
            sub(nv, "integer", id="lsop", value=1)
            nv.append(olvl_for(cur))
            ops.append(wrap(uid, nv, build))
            apply(cur)

        # Order matters for robustness: stats, flags and dates first, club and
        # division LAST. A club unknown to the target DB (Durban City in FM26)
        # then only loses those two cells instead of every op that follows it.
        set_cell("year", ET.Element("integer", id="value", value=str(row["year"])),
                 lambda r: r.__setitem__("year", row["year"]))
        if row["yror"]:
            set_cell("yror", ET.Element("integer", id="value", value=str(row["yror"])),
                     lambda r: r.__setitem__("yror", row["yror"]))
        for stat in ("apps", "gols"):
            # 0 IS 0, and blank is nil - never write one for the other (user,
            # 2026-09-08). An emit guard here turned an untouched figure into a
            # blank, so Litos' 16-appearance Estoril season and Emidio Graca's
            # whole career lost their 0 goals. It is not needed: the author NULLS
            # the figures he wants empty (a youth row's apps and goals are cleared
            # explicitly), so the model already holds None for those and 0 - the
            # editor's own default, see `new_row` - for the ones he left alone.
            if row[stat] is not None:
                set_cell(stat, ET.Element("integer", id="value", value=str(row[stat])),
                         lambda r, stat=stat: r.__setitem__(stat, row[stat]))
            else:   # blank season: explicit clear, otherwise the editor shows its default 0
                set_cell(stat, ET.Element("null", id="value"),
                         lambda r, stat=stat: r.__setitem__(stat, None))
        if row["ytht"]:
            set_cell("ytht", ET.Element("boolean", id="value", value="true"),
                     lambda r: r.__setitem__("ytht", True))
        if row["onln"]:
            set_cell("onln", ET.Element("boolean", id="value", value="true"),
                     lambda r: r.__setitem__("onln", True))
        if row["cash"] is not None:
            set_cell("cash", ET.Element(row["cash"].tag, id="value", value=row["cash"].get("value")),
                     lambda r: r.__setitem__("cash", row["cash"]))
        for f in ("join", "leaving"):
            if row[f] is not None:
                d = row[f]
                set_cell(f, ET.Element("date", id="value", day=d.get("day"), month=d.get("month"),
                                       year=d.get("year"), time="0"),
                         lambda r, f=f: r.__setitem__(f, row[f]))
        if row["club"] is not None:
            v = ET.Element("record", id="value")
            sub(v, "unsigned", id="id", value=VAL_ID)
            copy_ref_payload(v, row["club"])
            set_cell("club", v, lambda r: r.__setitem__("club", row["club"]))
        if row["divi"] is not None:
            v = ET.Element("record", id="value")
            sub(v, "unsigned", id="id", value=VAL_ID)
            copy_ref_payload(v, row["divi"])
            set_cell("divi", v, lambda r: r.__setitem__("divi", row["divi"]))
    return ops


# ---------------------------------------------------------------- main ------

def run(in_path, out_path, report_path=None, only=None):
    tree = ET.parse(in_path)
    root = tree.getroot()
    build = int(root.find('integer[@id="version"]').get("value"))
    changes = root.find('.//list[@id="db_changes"]')
    recs = list(changes)
    person_recs = [(i, r) for i, r in enumerate(recs)
                   if r.find('integer[@id="database_table_type"]').get("value") == c.PERSON_TABLE]
    created = {}
    for r in recs:
        if c.rec_prop(r) == "ADDR":
            for nvr in r.findall('record[@id="new_value"]'):
                u, d = nvr.find('large[@id="db_unique_id"]'), nvr.find('unsigned[@id="dcty"]')
                if u is not None and d is not None:
                    created[u.get("value")] = d.get("value")
    uf, _ = c.link_identities(person_recs, set(created))
    staff_uids = c.detect_staff(changes)
    names = c.person_names(changes)
    parts = defaultdict(dict)
    for r in recs:
        if c.rec_prop(r) in ("Pfna", "Psna"):
            nv = r.find('*[@id="new_value"]')
            if nv is not None and nv.tag == "string" and nv.get("value"):
                parts[c.rec_uid(r)][c.rec_prop(r)] = nv.get("value")
    for u, d in parts.items():
        names.setdefault(u, (d.get("Pfna", "") + " " + d.get("Psna", "")).strip())
    members = defaultdict(list)
    for _, r in person_recs:
        u = c.rec_uid(r)
        if u not in members[uf.find(u)]:
            members[uf.find(u)].append(u)

    plhs = defaultdict(list)          # person -> [(idx, rec)]
    dob = {}
    for i, r in person_recs:
        p = uf.find(c.rec_uid(r))
        prop = c.rec_prop(r)
        if prop == "Plhs":
            plhs[p].append((i, r))
        elif prop == "Pdob":
            nv = r.find('*[@id="new_value"]')
            if nv is not None and nv.tag == "date":
                dob[p] = int(nv.get("year"))

    report, remove_idx, insert_at = [], set(), {}
    n_removed = n_added = 0
    for p, ops in plhs.items():
        primary = members[p][0]
        if created.get(primary) != "2" or any(u in staff_uids for u in members[p]):
            continue
        name = next((names[u] for u in members[p] if u in names), primary)
        if only and not any(o.lower() in name.lower() for o in only):
            continue
        rows = replay([r for _, r in ops])
        rows, notes = clean(rows, dob.get(p))
        new_ops = emit_rows(primary, rows, build)
        for i, _ in ops:
            remove_idx.add(i)
        insert_at[ops[0][0]] = new_ops
        n_removed += len(ops)
        n_added += len(new_ops)
        report.append((name, primary, len(ops), len(new_ops), rows, notes))

    rebuilt = []
    for i, r in enumerate(recs):
        if i in insert_at:
            rebuilt.extend(insert_at[i])
        if i not in remove_idx:
            rebuilt.append(r)
    for r in list(changes):
        changes.remove(r)
    for r in rebuilt:
        changes.append(r)
    tree.write(out_path, encoding="unicode", xml_declaration=False)

    print(f"players rebuilt: {len(report)}  playing-history ops: {n_removed} removed, {n_added} written  "
          f"(net {n_added - n_removed:+d}); changes in file: {len(recs)} -> {len(rebuilt)}")
    flagged = [x for x in report if any(n.startswith("FLAG") for n in x[5])]
    print(f"players with flags to review: {len(flagged)}")
    if report_path:
        L = [f"# Playing-history rebuild report\n", f"- Source: `{in_path}`", f"- Output: `{out_path}`",
             f"- Players rebuilt: {len(report)}; ops removed {n_removed}, written {n_added}; "
             f"changes {len(recs)} -> {len(rebuilt)}", f"- Players with flags: {len(flagged)}\n",
             "## Flagged players\n"]
        for name, uid, n_old, n_new, rows, notes in sorted(flagged, key=lambda x: x[0]):
            L.append(f"### {name} ({uid})\n")
            L += [f"- {n}" for n in notes]
            L.append("")
            L.append("| Year | Club | Apps | Goals | Youth | Joined | Left |\n|---|---|---|---|---|---|---|")
            for r in rows:
                L.append(f"| {r['year']} | {club_key(r)} | {r['apps'] or ''} | {r['gols'] or ''} | "
                         f"{'yes' if r['ytht'] else ''} | {'/'.join(c.dtup(r['join'])) if r['join'] is not None else ''} | "
                         f"{'/'.join(c.dtup(r['leaving'])) if r['leaving'] is not None else ''} |")
            L.append("")
        L.append("## All rebuilt players\n")
        L.append("| Player | Ops before | Ops after | Rows | Notes |\n|---|---|---|---|---|")
        for name, uid, n_old, n_new, rows, notes in sorted(report, key=lambda x: x[0]):
            L.append(f"| {name} | {n_old} | {n_new} | {len(rows)} | {'; '.join(notes)} |")
        with open(report_path, "w") as f:
            f.write("\n".join(L))
        print(f"report -> {report_path}")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rebuild created players' playing history")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--report", metavar="FILE.md")
    ap.add_argument("--only", nargs="*", help="restrict to players whose name contains any of these")
    a = ap.parse_args(argv)
    run(a.input, a.output, a.report, a.only)


if __name__ == "__main__":
    main()
