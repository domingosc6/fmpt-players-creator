#!/usr/bin/env python3
"""
FMPT Legends - FM editor changeset edition/season converter (v2).

Takes an FM editor-data XML changeset authored for one season and shifts every
meaningful year/date so it can be re-imported for another season. Two modes:

  --offset N          Add N years to every person, uniformly. Use when the whole
                      file shares one vintage (e.g. +1 to prep next season,
                      +2 to bring an FM24 file to FM26's current 25/26 season).

  --target-season Y   "Make every player current for season Y/(Y+1)" (Y is the
                      label year, e.g. 2025 for 25/26). The offset is computed
                      PER PERSON from each one's last-season anchor, so a
                      mixed-vintage file (players from FM16, 17, 18 ... 24) all
                      land on the same target. Staff, anchorless people and
                      anomalies (future anchors) are LEFT UNSHIFTED and listed
                      in the report (--shift-staff opts staff into the majority).

What gets shifted (people = database table 1 only):
  - Top-level date fields: Pdob, contract dates (Pcjd/Pcex/Pcsd/PCNj) and loan
    dates (PLsd/PLed).
  - History grids Plhs / Pnph / PPsT, via the ORDERED-PRODUCED rule (below).

What is left untouched:
  - Non-person records (clubs = table 3, etc.) - never shifted.
  - PErt (retirements): kept as-is (project rule).
  - Pacl (honours/achievements): not a shift target; its ops delete real DB
    honours whose match keys must keep their real dates.
  - odvl scalars (old values); non-date integers (yror/apps/goals/...);
    sentinel years 1900 (empty date) and 2100 (placeholder).

PERSON IDENTITY ACROSS RECORD IDS (v2). A cumulative file (re-saved edition
after edition) carries the same person under SEVERAL db_unique_id values: the
created record's id changes between editor sessions, and a legend may also have
been edited on a real DB record in one edition and recreated from scratch in
another. Later edits cite the earlier state in their `olvl`/`odvl` snapshots,
so the ids are linked (union-find) when:
  - a grid op's `olvl` does not match any row this id already holds, but does
    match a "rich" row state (club, apps/goals or a real date present) that an
    earlier id produced; or
  - a Pdob op's `odvl` equals exactly the Pdob an earlier id had set.
One person = one offset, and the produced set below is shared by the whole
person, so a chain that crosses ids still shifts consistently. Ambiguous links
(several candidate people) are NOT made and are reported.

ORDERED-PRODUCED rule (history grids). Grid cell-edits carry no row index; the
editor finds the target row by matching the op's `olvl` snapshot, replaying ops
in order. An `olvl` value is a CHAIN reference (to a row the changeset already
built - shift it) iff a prior op in the same person's grid produced that exact
value; otherwise it is a FIRST-TOUCH / real-DB reference (leave it - includes
every lsop=2 delete of a real row). So: keep a `produced` set of the SOURCE
year/date values written by prior lsop=1 set ops; shift an `olvl` year/date iff
it is in `produced`; then shift the op's own `new_value` and add its pre-shift
value to `produced`. Sentinels never shift.

Anchor detection (--target-season). A person's current-season year is read from
the playing-history row carrying the highest `year` the person set: EMPTY
(apps & goals cleared, or never set) at year Y => current season Y/(Y+1),
current year Y; FILLED (apps/goals >0) at year Y => prepared for the next
season, current year Y+1. Filled-ness comes from the LAST apps/goals op on that
row after it got its year, else from the state the row carried when it was
relabelled to Y (a later edition renumbering an earlier row keeps its stats).
Offset = target_season - current_year. A negative offset (future anchor) is bad
source data: reported as an ANOMALY and left unshifted.

Known limitation (editor quirk, NOT this script): a row whose match key holds a
YEAR-ONLY date (exported 0/0/YYYY - a season with no exact day; stored
internally as a 1/1/1901 marker) does not round-trip. On import the editor
cannot match it, so that op reverts and the row keeps its original values. This
hits the untouched source too. --flag-year-only lists the affected rows.

Usage:
    convert_edition.py INPUT OUTPUT (--offset N | --target-season YEAR)
                       [--shift-staff] [--flag-year-only] [--report FILE.md]
                       [--continuations current|none|all]

CONTINUATION IDS - LIVE OR DEAD. When the editor loads a file it maps each
created record to a session id; edits made then are saved under that id, with
no ADDR. Observed: ids from EARLIER editions are dead (the user sees the
pre-continuation state in the editor: Kempes/Puchades FM18 renumberings do not
show), the saving edition's own ids are live (Adelardo's FM24 renumbering
shows). Whether the NEXT editor (FM26) still honours the saving edition's ids
was the first reading. Editor grids (England: Alan Smith, Bonds, Williams)
then showed ops from EVERY edition landing or missing individually - ids are
not dead, single ops miss when their snapshot finds no row. So the anchor is
read from ALL of a person's ids (--continuations all, default): that is the
literal-replay state the cleaner (clean_import.py) rebuilds careers from, so
offset and rebuilt career agree. 'current' / 'none' remain for experiments.
"""
import argparse
import copy
import random
import re
from datetime import date, timedelta
import xml.etree.ElementTree as ET

import fm_names
from collections import Counter, defaultdict

class _Sentinels(frozenset):
    """Years that are never shifted. 1900 is FM's empty date and 2100 an old
    artefact; anything below 1000 is not a year at all - FM writes an unset date
    as year 0, and the author's own typos (198, 201, 209) have lost a digit.
    Shifting either produces a date the editor cannot read."""

    def __contains__(self, y):
        try:
            return int(y) < 1000 or frozenset.__contains__(self, int(y))
        except (TypeError, ValueError):
            return frozenset.__contains__(self, y)


SENTINELS = _Sentinels({1900, 2100})
NULL_DATE = ("1", "1", "1900")
YEAR_COL = "2036687218"                     # Plhs "year" grid column
JOIN_COL = "1785686382"                     # join date column
LEAVE_COLS = {"1818583414", "1818584692"}   # leave / left date columns
APPS_COL = "1634758771"                     # Plhs appearances column
GOLS_COL = "1735355507"                     # Plhs goals column
CLUB_COLS = {"1668049252", "1952540013"}    # clid (Plhs) / team (Pnph, PPsT)
GRID_PROPS = {"Plhs", "Pnph", "PPsT"}
TOP_DATE_PROPS = {"Pdob", "Pcjd", "Pcex", "Pcsd", "PCNj", "PLsd", "PLed"}
NEVER_SHIFT_PROPS = {"PErt"}                # retirements keep their dates
PERSON_TABLE = "1"                          # only table-1 (people) are shifted
MAX_OFFSET = 12                             # beyond this the anchor is not a transported legend
# editor build stamped on each change -> edition it was authored in (informative only)
EDITION_BY_BUILD = {2281: "FM15", 2380: "FM16", 2381: "FM16", 2382: "FM16",
                    2464: "FM17", 2468: "FM17", 2469: "FM17", 2637: "FM18",
                    2640: "FM18", 2768: "FM19", 2773: "FM19", 2961: "FM20",
                    3032: "FM21", 3035: "FM21", 3569: "FM24"}


def fourcc(n):
    n = int(n)
    return bytes([(n >> 24) & 255, (n >> 16) & 255, (n >> 8) & 255, n & 255]).decode("latin1")


def prop_id(name):
    """The unsigned property id behind a four-character property name."""
    return int.from_bytes(name.encode("latin1"), "big")


def dtup(el):
    return (el.get("day"), el.get("month"), el.get("year"))


def shift_date_year(el, off):
    """Add `off` years to a date element in place. 29 February clamps to the 28th
    when the target year is not a leap year - the editor rejects the impossible
    date and shows a blank/0 (Denis Law's 29/2 leave date)."""
    y = int(el.get("year"))
    if y in SENTINELS:
        return
    ny = y + off
    if el.get("day") == "29" and el.get("month") == "2" and not (ny % 4 == 0 and (ny % 100 != 0 or ny % 400 == 0)):
        el.set("day", "28")
    el.set("year", str(ny))


def is_year_only(el):
    return el.get("day") == "0" and el.get("month") == "0"


def usable_date(el):
    """Is this a date the editor can actually hold? A year-only date (0/0/2016)
    shows as `0` in the grid and does not round-trip, and a month of 0 is the same
    thing - Manuel Barbosa arrives with 0 in Date Joined on his first season and on
    his spell because the author wrote one (user, 2026-09-08). Such a date is
    treated as ABSENT, so the season boundary is derived instead."""
    return (el is not None and not is_year_only(el)
            and int(el.get("month") or 0) >= 1 and int(el.get("year") or 0) >= 1000)


def authored_date_ok(el, club, seasons, first_run=False):
    """Is a date the AUTHOR wrote good enough to beat the derived season boundary?

    `usable_date` asks only whether the editor can hold it. This asks whether it
    means anything. 1 JANUARY is ambiguous: it is what FM holds when the year is
    known and the day is not, AND it is the real date of a winter transfer.

    The two are told apart by WHERE the date sits in the career. On the FIRST run
    it is a placeholder - a youth arrival whose exact day nobody recorded - and
    taking it literally puts the arrival in the middle of the following season:
    Lucho Gonzalez's Huracan spell read 1/1/2015 against a career row labelled
    2014 (user, 2026-09-09). Anywhere later it is a mid-season move, and it is his
    real answer: Milonja Djukic left Vojvodina on 31/12/2016 and joined Sutjeska
    Niksic on 1/1/2017, a handoff the user had already validated - refusing that
    one rewrote a correct career.

    Refusing lets the DERIVED date stand, computed from the run's own start year,
    so it lands on the right season. Coercing the date in place could not do that:
    1/1/2015 would become 1/7/2015, a year late.

    A calendar-year league really does open on 1 January, and there 1/1 is always
    his answer and is kept.
    """
    if not usable_date(el):
        return False
    if first_run and el.get("day") == "1" and el.get("month") == "1" \
            and seasons is not None and not seasons.calendar_year(club):
        return False
    return True


def rec_uid(rec):
    return rec.find('large[@id="db_unique_id"]').get("value")


def rec_prop(rec):
    return fourcc(rec.find('unsigned[@id="property"]').get("value"))


def rec_build(rec):
    v = rec.find('integer[@id="version"]')
    return int(v.get("value")) if v is not None else None


# ---------------------------------------------------------------- grid ops ---

TEAM_UID_SCALE = 4294967297          # unique id = DBID * (2**32 + 1), exactly


def team_dbid(t):
    """The two id kinds name the SAME club: older editors write the integer
    DBID, FM21+ the large unique id, and unique = DBID * 4294967297 exactly -
    verified against every club reference in every file. Normalising to the DBID
    is what stops one club reading as two (Xabi Alonso's Real Sociedad seasons
    appeared twice, once under each kind)."""
    v = t.get("value")
    if t.tag == "large":
        n = int(v)
        if n > 0 and n % TEAM_UID_SCALE == 0:
            return str(n // TEAM_UID_SCALE)
    return v


def club_of(el):
    """Club reference from a nested club/team record as (kind, value), else None,
    normalised so the same club compares equal whatever edition wrote it."""
    if el is None or el.tag != "record":
        return None
    t = el.find('*[@id="Ttea"]')
    if t is None:
        return None
    v = team_dbid(t)
    return ("integer" if v != t.get("value") else t.tag, v)


def parse_op(rec):
    """Decompose a grid op: (lsop, col, value-element, olvl-state-dict|None)."""
    nv = rec.find('*[@id="new_value"]')
    if nv is None:
        return None, None, None, None
    idel = nv.find('unsigned[@id="id"]')
    col = idel.get("value") if idel is not None else None
    lsop_el = nv.find('integer[@id="lsop"]')
    lsop = lsop_el.get("value") if lsop_el is not None else None
    val = next((c for c in nv if c.get("id") == "value"), None)
    olvl = nv.find('record[@id="olvl"]')
    return lsop, col, val, (olvl_state(olvl) if olvl is not None else None)


def olvl_state(olvl):
    """Normalised row snapshot: only the fields the snapshot carries."""
    st = {}
    y = olvl.find('integer[@id="year"]')
    if y is not None:
        st["year"] = int(y.get("value"))
    for f in ("apps", "gols"):
        e = olvl.find(f'*[@id="{f}"]')
        if e is not None:          # None = no figure recorded (blank), distinct from 0
            st[f] = None if e.tag == "null" or e.get("value") in (None, "") else int(e.get("value"))
    for f in ("column_id", "team"):
        e = olvl.find(f'*[@id="{f}"]')
        if e is not None:
            st["club"] = club_of(e)
    for f, key in (("join", "join"), ("leaving", "left"), ("left", "left")):
        e = olvl.find(f'date[@id="{f}"]')
        if e is not None:
            st[key] = dtup(e)
    return st


BLANK_ROW = {"year": 1900, "apps": 0, "gols": 0, "club": None,
             "join": NULL_DATE, "left": NULL_DATE}


def row_matches(row, st):
    """Snapshot equals the row; a club stored under a different id kind is a
    wildcard (same club, other editor generation). Identity linking only: a
    blank stat and 0 are treated alike here."""
    for k, v in st.items():
        rv = row.get(k, BLANK_ROW[k])
        if k == "club" and rv is not None and v is not None and rv[0] != v[0]:
            continue
        if k in ("apps", "gols"):
            if (rv or 0) != (v or 0):
                return False
            continue
        if rv != v:
            return False
    return True


KEY_FIELDS = ("year", "apps", "gols", "join", "left")   # club checked separately


def row_key(row):
    return tuple((row.get(k, BLANK_ROW[k]) or 0) if k in ("apps", "gols") else row.get(k, BLANK_ROW[k]) for k in KEY_FIELDS)


def is_rich(st):
    """A snapshot specific enough to identify a person: a season with stats, or a
    club spell with both dates. Club-only or year-only states are shared by too
    many people (teammates) to link on."""
    real = lambda d: d != NULL_DATE
    return ((st.get("year", 1900) not in SENTINELS and ((st.get("apps") or 0) > 0 or (st.get("gols") or 0) > 0))
            or (st.get("club") is not None and real(st.get("join", NULL_DATE)) and real(st.get("left", NULL_DATE))))


def cell_update(row, col, val):
    """Apply an lsop=1 set to a simulated row."""
    if col == YEAR_COL:
        row["year"] = int(val.get("value")) if val is not None and val.get("value") else 1900
    elif col == APPS_COL:
        row["apps"] = int(val.get("value")) if val is not None and val.get("value") not in (None, "") else 0
    elif col == GOLS_COL:
        row["gols"] = int(val.get("value")) if val is not None and val.get("value") not in (None, "") else 0
    elif col in CLUB_COLS:
        row["club"] = club_of(val)
    elif col == JOIN_COL:
        row["join"] = dtup(val) if val is not None and val.tag == "date" else NULL_DATE
    elif col in LEAVE_COLS:
        row["left"] = dtup(val) if val is not None and val.tag == "date" else NULL_DATE


class Rows:
    """Light replay of one id's grid so olvl snapshots can be matched to rows."""

    def __init__(self):
        self.rows = []

    def find(self, st):
        for r in self.rows:
            if row_matches(r, st):
                return r
        return None

    def apply(self, lsop, col, val, st):
        """Replay one op; returns (key of the row before the op or None,
        the row after the op or None for deletes)."""
        if lsop == "0" or (lsop is None and st is None):
            row = dict(BLANK_ROW)
            self.rows.append(row)
            return None, row
        row = self.find(st) if st is not None else None
        pre = row_key(row) if row is not None else None
        if row is None and st is not None:
            row = dict(BLANK_ROW)
            row.update(st)                # first touch of a real DB row
            self.rows.append(row)
        if lsop == "2":
            if row in self.rows:
                self.rows.remove(row)
            return pre, None
        if lsop == "4":
            dup = dict(row)
            self.rows.append(dup)
            return None, dup
        if lsop == "1" and row is not None:
            cell_update(row, col, val)
        return pre, row


# ------------------------------------------------------------ union-find ----

class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def split(self, x):
        """Detach one id into a group of its own. Safe only once every id has
        been through find(), which compresses each of them onto the root, so no
        other id's chain still runs through this one."""
        self.parent[x] = x


NAME_PROPS = ("Pfln", "Pcna", "Pfna", "Psna")


def person_names(changes):
    """uid -> display name, for records that set a name (created profiles).

    Most created profiles carry a full name (`Pfln`), but plenty are named by
    parts instead - Paulo Sergio has `Pfna` "Paulo Sergio", `Psna` "Silvestre do
    Nascimento" and `Pcna` "Paulo Sergio", and no `Pfln` at all - and reading only
    `Pfln` left every one of those labelled "(existing DB record, no name change)"
    throughout the report. Last value per property wins, the way the editor
    applies them."""
    parts = defaultdict(dict)
    for rec in changes:
        prop = rec_prop(rec)
        if prop not in NAME_PROPS:
            continue
        nv = rec.find('*[@id="new_value"]')
        if nv is not None and nv.tag == "string" and nv.get("value"):
            parts[rec_uid(rec)][prop] = nv.get("value")
    names = {}
    for uid, got in parts.items():
        full = got.get("Pfln") or " ".join(x for x in (got.get("Pfna"), got.get("Psna")) if x)
        names[uid] = full or got.get("Pcna")
    return {u: n for u, n in names.items() if n}


def detect_staff(changes):
    """Id is staff if created with dcty=1, or carries an N-prefix attribute
    change and was never flipped to player (Ptyp -> 2)."""
    created_dcty, has_n, became_player = {}, defaultdict(bool), defaultdict(bool)
    for rec in changes:
        prop = rec_prop(rec)
        uid = rec_uid(rec)
        if prop == "ADDR":
            for nvr in rec.findall('record[@id="new_value"]'):
                d = nvr.find('unsigned[@id="dcty"]')
                u = nvr.find('large[@id="db_unique_id"]')
                if d is not None and u is not None:
                    created_dcty[u.get("value")] = d.get("value")
        if prop.startswith("N"):
            has_n[uid] = True
        if prop == "Ptyp":
            nv = rec.find('*[@id="new_value"]')
            if nv is not None and nv.get("value") == "2":
                became_player[uid] = True
    uids = {rec_uid(rec) for rec in changes}
    return {u for u in uids
            if created_dcty.get(u) == "1" or (has_n[u] and not became_player[u])}


LINK_THRESHOLD = 2   # independent snapshot matches needed to link two ids


def link_identities(person_recs, created):
    """Union ids that edit the same person. Evidence for a pair (id X cites id
    Y) is counted from X's snapshots that match none of X's own rows but do
    match Y's CURRENT state (what the editor would see): one point per distinct
    rich grid row, one for a Pdob odvl equal to Y's current Pdob. Created ids
    (fresh ADDR records) never cite anyone. X is linked to the single Y with
    >= LINK_THRESHOLD points, or the clear winner (twice the runner-up); otherwise X is ambiguous
    (reported, unlinked).
    Returns (uf, ambiguous) with ambiguous = [(uid, [(cand, points)])]."""
    grids = {}                                   # (uid, prop) -> Rows
    index = defaultdict(dict)                    # (prop, key) -> {id(row): (uid, row)}
    pdob_cur, pdob_idx = {}, defaultdict(set)    # uid -> date ; date -> {uid}
    evidence = defaultdict(set)                  # (X, Y) -> {evidence tokens}

    for idx, rec in person_recs:
        uid, prop = rec_uid(rec), rec_prop(rec)
        if prop in GRID_PROPS:
            lsop, col, val, st = parse_op(rec)
            rows = grids.setdefault((uid, prop), Rows())
            if uid not in created and st is not None and rows.find(st) is None and is_rich(st):
                key = tuple(st.get(k, BLANK_ROW[k]) for k in KEY_FIELDS)
                for (u, row) in index[(prop, key)].values():
                    if u != uid and row_matches(row, st):
                        evidence[(uid, u)].add((prop, key))
            pre_row = rows.find(st) if st is not None and lsop != "0" else None
            if pre_row is not None:
                index[(prop, row_key(pre_row))].pop(id(pre_row), None)
            _, row = rows.apply(lsop, col, val, st)
            if row is not None:
                index[(prop, row_key(row))][id(row)] = (uid, row)
        elif prop == "Pdob":
            nv = rec.find('*[@id="new_value"]')
            od = rec.find('*[@id="odvl"]')
            if uid not in created and od is not None and od.tag == "date" \
                    and dtup(od) != NULL_DATE and not is_year_only(od):
                for u in pdob_idx.get(dtup(od), set()) - {uid}:
                    evidence[(uid, u)].add(("Pdob", dtup(od)))
            if nv is not None and nv.tag == "date" and dtup(nv) != NULL_DATE:
                if uid in pdob_cur:
                    pdob_idx[pdob_cur[uid]].discard(uid)
                pdob_cur[uid] = dtup(nv)
                pdob_idx[dtup(nv)].add(uid)

    uf, ambiguous = UnionFind(), []
    for _, rec in person_recs:
        uf.find(rec_uid(rec))
    by_x = defaultdict(list)
    for (x, y), ev in evidence.items():
        # An id that is not DBID * 4294967297 was INVENTED by an editor, so it has
        # no database rows of its own to cite. When such an id cites another
        # record's row, that is already the whole story - demanding a second
        # citation is what left Ahmed Ziad's 2015 season on an unlinked id, and the
        # unlinked rebuild then wiped his career. A real DB id still needs
        # LINK_THRESHOLD, where a single coincidence is cheap.
        need = 1 if fm_names.dbid(x) is None else LINK_THRESHOLD
        if len(ev) >= need:
            by_x[x].append((y, len(ev)))
    for x, cands in by_x.items():
        # A REAL database id never links to a CREATED one. An ADDR record IS a new
        # person, so FM's own record for somebody else cannot be that same person,
        # and joining them only produces the "has both a created record and a real
        # one - fix by hand" refusal, which leaves the real record's raw ops to
        # apply against the target database and wreck it.
        #
        # Pedro Emanuel (FM dbid 1587) is the case: his ops cite rows that collide
        # with the created "Ademar Moreira Marques", so the two were linked, the
        # rebuild refused, and his FM17 deletes and relabels landed on FM26's own
        # Pedro Emanuel - his real 1991-2008 career plus three stray rows. Unlinked,
        # he is rebuilt as what he is: a real record the author transported (his own
        # career, shifted +17 in the FM18 file).
        #
        # An INVENTED id may still link to a created one - that is a continuation of
        # the created record, and refusing it is what broke Ahmed Ziad.
        if fm_names.dbid(x) is not None:
            cands = [c for c in cands if c[0] not in created]
            if not cands:
                continue
        cands.sort(key=lambda c: -c[1])
        # A tie between a record the author CREATED in this file and one of FM's
        # own goes to the created one, when the id doing the citing was invented by
        # an editor. Such an id belongs to the author's own work, and the row it
        # cites was built here with those exact figures, while a database row that
        # happens to share a club and a scoreline is a coincidence among thousands
        # of records - a teammate, usually.
        #
        # Fredrik Soderstrom is the case (user, 2026-09-08): his extra 2015 season
        # sits on an invented id that cites {2014, Vitoria, 6 apps, 0 goals}, which
        # matches BOTH his created record and a real one, one point each. Tied, the
        # linker refused, the unlinked id was rebuilt on its own, and its Clear left
        # him with a single season of 30 apps - the very shape Ahmed Ziad had.
        if (len(cands) > 1 and cands[0][1] == cands[1][1]
                and fm_names.dbid(x) is None):
            top = [c for c in cands if c[1] == cands[0][1]]
            made = [c for c in top if c[0] in created]
            if len(made) == 1:
                uf.union(x, made[0][0])
                continue
            # Still tied: take the candidate whose id is NUMERICALLY CLOSEST. This
            # editor allocates a continuation id right beside the record it
            # continues - in the FM17 Portugal file there are 15 pairs exactly 242
            # apart, and in all 15 the lower id is the CREATED (ADDR) record, the
            # same delta Ahmed Ziad's and Fredrik Soderstrom's pairs carry. Joaquim
            # Antonio Jorge is the case: his 2015 Vitoria season sits on his id +242
            # and cites {2014, FC Porto, 4 apps, 0 goals}, which also matches a
            # stranger's row one point for one point, so the link was refused and
            # the season vanished (user, 2026-09-08). Distance settles it: 242
            # against half a billion.
            if made:
                top = made
            try:
                near = sorted(top, key=lambda c: abs(int(c[0]) - int(x)))
            except ValueError:
                near = []
            if len(near) > 1 and abs(int(near[0][0]) - int(x)) * 1000 < abs(int(near[1][0]) - int(x)):
                uf.union(x, near[0][0])
                continue
        if len(cands) == 1 or cands[0][1] >= 2 * cands[1][1]:   # clear winner
            uf.union(x, cands[0][0])
        else:
            ambiguous.append((x, cands))
    return uf, ambiguous


def detect_current_year(plhs_recs):
    """Current-season year for one person's playing-history ops (file order).
    None if the person never set a playing-history year."""
    max_year, max_i, max_st = None, None, None
    for i, rec in enumerate(plhs_recs):
        lsop, col, val, st = parse_op(rec)
        if lsop == "1" and col == YEAR_COL and val is not None and val.get("value"):
            y = int(val.get("value"))
            if y not in SENTINELS and (max_year is None or y >= max_year):
                max_year, max_i, max_st = y, i, st or {}
    if max_year is None:
        return None
    last_positive = None
    for rec in plhs_recs[max_i + 1:]:
        lsop, col, val, st = parse_op(rec)
        if lsop != "1" or col not in (APPS_COL, GOLS_COL) or not st or st.get("year") != max_year:
            continue
        v = val.get("value") if val is not None else None
        last_positive = bool(v) and int(v) > 0
    if last_positive is None:                 # relabelled row keeps its stats
        last_positive = (max_st.get("apps") or 0) > 0 or (max_st.get("gols") or 0) > 0
    return max_year + 1 if last_positive else max_year


def shift_top_date(nv, off):
    if nv is not None and nv.tag == "date" and int(nv.get("year")) not in SENTINELS:
        shift_date_year(nv, off)


def convert_grid(recs, off):
    """Apply the ordered-produced rule to one (person, grid-prop) op sequence."""
    prod_years, prod_dates = set(), set()
    for rec in recs:
        nv = rec.find('*[@id="new_value"]')
        if nv is None:
            continue
        idel = nv.find('unsigned[@id="id"]')
        col = idel.get("value") if idel is not None else None
        lsop_el = nv.find('integer[@id="lsop"]')
        lsop = lsop_el.get("value") if lsop_el is not None else None
        val = next((c for c in nv if c.get("id") == "value"), None)
        olvl = nv.find('record[@id="olvl"]')

        # 1) shift olvl fields already produced by a prior op (chain refs)
        if olvl is not None:
            y = olvl.find('integer[@id="year"]')
            if y is not None:
                yi = int(y.get("value"))
                if yi not in SENTINELS and yi in prod_years:
                    y.set("value", str(yi + off))
            for f in ("join", "leaving", "left"):
                de = olvl.find(f'date[@id="{f}"]')
                if de is not None and int(de.get("year")) not in SENTINELS and dtup(de) in prod_dates:
                    shift_date_year(de, off)

        # 2) record the pre-shift produced value, then shift the new_value
        if lsop == "1" and val is not None:
            if col == YEAR_COL and val.get("value") is not None:
                yi = int(val.get("value"))
                if yi not in SENTINELS:
                    prod_years.add(yi)
                    val.set("value", str(yi + off))
            elif col in ({JOIN_COL} | LEAVE_COLS) and val.tag == "date":
                if int(val.get("year")) not in SENTINELS:
                    prod_dates.add(dtup(val))
                    shift_date_year(val, off)


def find_year_only_rows(changes, uids):
    """Distinct (uid, prop) with a year-only date in an op's olvl match key."""
    flagged = set()
    for rec in changes:
        uid = rec_uid(rec)
        if uid not in uids:
            continue
        prop = rec_prop(rec)
        if prop not in GRID_PROPS:
            continue
        olvl = rec.find('*[@id="new_value"]/record[@id="olvl"]')
        if olvl is None:
            continue
        if any(is_year_only(de) and int(de.get("year")) not in SENTINELS for de in olvl.iter("date")):
            flagged.add((uid, prop))
    return sorted(flagged)



# ------------------------------------------- real records: the shift model ---

STAT_COLS = {APPS_COL, GOLS_COL, "2037672052", "1869507694", "1667330920",
             "1684633193", "2037542770"}          # apps, gols, youth, loan, fee, division, order
SPELL = {"row": "1853322860", "team": "1952801133", "join": "1785686382",
         "left": "1818584692", "tjob": "1953132386"}
PNPH_PROP = str(int.from_bytes(b"Pnph", "big"))


def replay_spells(pnph_ops):
    """Final state of the club-spells grid, replayed from its ops. A created
    player builds his spells on BLANK rows, so no snapshot ever names the club and
    the last-value reading real records use cannot see them at all (Elkjaer). The
    grid the author leaves behind is the source of truth for a row's dates."""
    rows = []

    def same(row, st):
        if st is None:
            return False
        if "club" in st:
            ref = st["club"]
            if (ref[1] if ref else None) != (row["team"][1] if row["team"] else None):
                return False
        for k in ("join", "left"):
            if k in st and (dtup(row[k]) if row[k] is not None else NULL_DATE) != st[k]:
                return False
        return True

    def find(st):
        hits = [r for r in rows if same(r, st)]
        return hits[-1] if hits else None       # the newest of several blank rows

    for rec in pnph_ops:
        lsop, col, val, st = parse_op(rec)
        if lsop == "3":
            rows = []
        elif lsop == "0":
            rows.append({"team": None, "join": None, "left": None})
        elif lsop in ("2", "4"):
            row = find(st)
            if row is None:
                continue
            rows.remove(row) if lsop == "2" else rows.append(dict(row))
        elif lsop == "1":
            row = find(st) or (rows[-1] if rows else None)
            if row is None:
                continue
            if col == SPELL["team"]:
                row["team"] = club_of(val) if val is not None and val.tag == "record" else None
            elif col in (SPELL["join"], SPELL["left"]):
                k = "join" if col == SPELL["join"] else "left"
                row[k] = copy.deepcopy(val) if val is not None and val.tag == "date" \
                    and int(val.get("year")) not in SENTINELS else None
    return [r for r in rows if r["team"]]


def replay_spells_ops(pnph_ops):
    """`replay_spells`, but each row also remembers the OP that last set its join
    and its leave, so the date can be rewritten where the author left a zero."""
    rows = []

    def same(row, st):
        if st is None:
            return False
        if "club" in st:
            ref = st["club"]
            if (ref[1] if ref else None) != (row["team"][1] if row["team"] else None):
                return False
        for k in ("join", "left"):
            if k in st and (dtup(row[k]) if row[k] is not None else NULL_DATE) != st[k]:
                return False
        return True

    def find(st):
        hits = [r for r in rows if same(r, st)]
        return hits[-1] if hits else None

    for rec in pnph_ops:
        lsop, col, val, st = parse_op(rec)
        if lsop == "3":
            rows = []
        elif lsop == "0":
            rows.append({"team": None, "join": None, "left": None,
                         "join_op": None, "left_op": None, "ops": []})
        elif lsop in ("2", "4"):
            row = find(st)
            if row is None:
                continue
            rows.remove(row) if lsop == "2" else rows.append(dict(row))
        elif lsop == "1":
            row = find(st) or (rows[-1] if rows else None)
            if row is None:
                continue
            row["ops"].append((rec, col))
            if col == SPELL["team"]:
                row["team"] = club_of(val) if val is not None and val.tag == "record" else None
            elif col in (SPELL["join"], SPELL["left"]):
                k = "join" if col == SPELL["join"] else "left"
                row[k] = copy.deepcopy(val) if val is not None and val.tag == "date" \
                    and int(val.get("year")) not in SENTINELS else None
                row[k + "_op"] = val if val is not None and val.tag == "date" else None
    return [r for r in rows if r["team"]]


def spells_need_rebuild(pnph_ops, rows=None):
    """Should a created player's spells grid be replaced by the career-derived one?

    Only where his own is DEFICIENT. Rebuilding every created player also rewrote
    the ones that were already right, and his hand-set dates carry things the
    derivation cannot know - Milonja Djukic left Vojvodina on 31/12/2016 and joined
    Sutjeska Niksic on 1/1/2017, a mid-season handoff the user had validated, which
    the rebuild turned into an overlapping 30/12/2016 against a 30/6/2017 leave.

    Deficient means the DATES are unusable: no spells at all, or a date the editor
    draws as 0 (absent join, sentinel, year-only) - Eduardo Luis, whose three
    spells read 0 for both dates.

    It deliberately does NOT mean "the clubs disagree with the career", even
    though that is the 493-row report class. Rebuilding on that trigger repairs
    the disagreement by DELETING what disagrees, and what disagrees is often real:
    Bobby Tambling's spells name Cork City, where he went with no playing record,
    and the rebuild dropped the club entirely. It also costs accuracy, because
    `fits` refuses 1 January categorically for a rebuilt spell - so his genuine
    mid-season move to Crystal Palace (1/1/2022, the career shows him at both
    clubs in 2021) came out as 1/7/2021. The disagreements stay REPORTED, which is
    the state the user has been working with, rather than silently resolved the
    wrong way (user's records, 2026-09-09).
    """
    spells = replay_spells_ops(pnph_ops)
    if not spells:
        return True
    for sp in spells:
        if not usable_date(sp["join"]):
            return True
        if sp["left"] is not None and not usable_date(sp["left"]):
            return True
    return False


def fill_blank_divisions(rows):
    """Give a career row with no DIVISION the one his other rows at that club use.

    The author leaves it blank here and there - Eduardo Luis's first Benfica
    season, a youth year, has none while his later Benfica row carries the
    Portuguese Premier League (user, 2026-09-09, reported twice). Nothing is
    invented: the value comes from another row of HIS OWN at the SAME club, so a
    legend's old club outside any playable league still gets nothing, which is
    correct - that is why the field is null for those.

    The most common division at the club wins, so one stray row cannot drag the
    rest. Returns how many rows were filled.
    """
    import clean_import as ci
    by_club = defaultdict(Counter)
    seen = {}
    for r in rows:
        if r["club"] is None or r.get("divi") is None:
            continue
        key = ET.tostring(r["divi"], encoding="unicode")
        by_club[ci.club_key(r)][key] += 1
        seen[key] = r["divi"]
    n = 0
    for r in rows:
        if r["club"] is None or r.get("divi") is not None:
            continue
        pick = by_club.get(ci.club_key(r))
        if not pick:
            continue
        d = copy.deepcopy(seen[pick.most_common(1)[0][0]])
        d.set("id", "divi")
        r["divi"] = d
        n += 1
    return n


def fill_zero_spell_dates(pnph_ops, derived):
    """The author leaves a spell's Date Joined / Date Left as 0 - FM's unset date -
    on plenty of created players, so the row reads "0" in the editor even though his
    PLAYING history carries the dates (Jair Rosa Pinto: all five spells 0, every
    career row dated 1/1). Where a zero sits, take the date from the spell the
    career derives for the same club. USER RULE (2026-09-07). Only zeros are
    written; a date he typed stands, and a leave he left blank on his current club
    stays blank.

    Grid and derived spells are paired in ORDER and every club must agree down the
    list - a grid that does not line up is left alone, the same all-or-nothing rule
    `dates_from_spells` uses. The derived dates are already in the target frame, so
    this runs AFTER the shift: a zero is a sentinel and would otherwise be shifted
    on top of the value just written."""
    rows = replay_spells_ops(pnph_ops)
    if not rows or len(rows) > len(derived):
        return 0
    # His grid is not always in career order: Renato Zaccarelli's runs
    # reverse-chronologically (Torino 2023 first, Catania 2017 last), so the
    # order-preserving pairing below found nothing and his 1/1 dates were left
    # alone (user, 2026-09-08). Try the grid as written, then reversed.
    for attempt in (rows, rows[::-1]):
        got = _fill_spells_in_order(attempt, derived)
        if got:
            return got
    return 0


def _fill_spells_in_order(rows, derived):
    # His grid is often a SUBSET of the career - he lists the clubs that matter and
    # skips a loan or a return - so the rows are matched as an order-preserving
    # subsequence rather than one-for-one (Moacir Barbosa's grid reads Vasco then
    # Ypiranga against a career of Ypiranga, Vasco, Ypiranga). Greedy, earliest
    # match: if any row finds no club after the one before it, the whole player is
    # left alone.
    want, i = [], 0
    for row in rows:
        if not row["team"]:
            return 0
        while i < len(derived):
            ref = club_of(derived[i]["ref"])
            i += 1
            if ref and ref[1] == row["team"][1]:
                want.append(derived[i - 1])
                break
        else:
            return 0                              # the grids do not describe one career
    if len(want) != len(rows):
        return 0
    n = 0
    for row, sp in zip(rows, want):
        new = {}
        for k in ("join", "left"):
            # A zero; a YEAR-ONLY date (0/0/2016), which the editor shows as 0 just
            # the same (Manuel Barbosa's Boavista spell); and 1 JANUARY, which is
            # what the editor holds when only the year is known - Renato Zaccarelli's
            # spells all read 1/1 while his career rows are correctly dated 1/7
            # (user, 2026-09-08). Taking 1/1 literally puts a summer move in the
            # middle of the previous season, which is why `fits` has always refused
            # it for a rebuilt spell. Deriving costs nothing where 1/1 is genuinely
            # right: a calendar-year league derives 1/1 anyway.
            def unset_date(el):
                return (el is None or is_year_only(el)
                        or (el.get("day") == "1" and el.get("month") == "1"))

            if (unset_date(row[k])
                    and row[k + "_op"] is not None and sp.get(k) is not None):
                new[id(row[k + "_op"])] = sp[k]
        if not new:
            continue
        # Writing the value is only half of it. Every op cites the row state it
        # expects (`olvl`), the editor resolves that to the FIRST row that fits, and
        # a later op on the same row still quoted the zero this one just replaced -
        # so it matched nothing and the change was silently dropped (Jair's Date
        # Joined took, every Date Left stayed blank). Walk the row's own ops in
        # order and re-thread the chain.
        cur = {"join": NULL_DATE, "left": NULL_DATE}
        for rec, col in row["ops"]:
            nv = rec.find('*[@id="new_value"]')
            olvl = nv.find('record[@id="olvl"]') if nv is not None else None
            if olvl is not None:
                for k in ("join", "left"):
                    el = olvl.find('date[@id="%s"]' % k)
                    if el is not None:
                        el.set("day", cur[k][0])
                        el.set("month", cur[k][1])
                        el.set("year", cur[k][2])
            if col not in (SPELL["join"], SPELL["left"]):
                continue
            k = "join" if col == SPELL["join"] else "left"
            val = nv.find('date[@id="value"]') if nv is not None else None
            if val is not None and id(val) in new:
                src = new[id(val)]
                val.set("day", src.get("day"))
                val.set("month", src.get("month"))
                val.set("year", src.get("year"))
                n += 1
            cur[k] = dtup(val) if val is not None else NULL_DATE
    return n


def dates_from_spells(spells, authored, seasons=None):
    """Take each run's join and leave date from the author's own spells grid: he
    dates a calendar-year league 1/1 - 31/12 and a mid-season move on the day it
    happened (Elkjaer joined Koln on 1/1/2018 and Lokeren on 6/2/2019), and none
    of that can be derived from the career. Runs and spells are paired in order at
    each club; where the counts disagree nothing is claimed and the derived dates
    stand."""
    by_club = defaultdict(list)
    for sp in authored:
        by_club[sp["team"][1]].append(sp)
    mine = defaultdict(list)
    for sp in spells:
        if sp.get("run") is not None:
            mine[sp["run"]["club"]].append(sp)
    # His grid is the authority only where it still describes THIS career. It can
    # lag his relabelling (Platini's Nancy B spell reads 2018 against a 2012 row;
    # Thuram's Parma spell is a year behind his Parma rows), and taking the dates
    # that happen to fit while deriving the rest is worse than deriving them all -
    # it leaves a hole between one club's leave and the next one's join. So the
    # whole player is checked first, and one date out of step forfeits the lot.
    take = []
    # the career's earliest run, not merely the first at each club: only there is
    # a 1/1 join a placeholder rather than a winter transfer
    earliest = min((sp for rs in mine.values() for sp in rs),
                   key=lambda sp: sp["run"]["start"], default=None)
    for club, runs in mine.items():
        his = by_club.get(club) or []
        if len(his) != len(runs):
            return 0
        for sp, h in zip(runs, his):
            run = sp["run"]
            rs = sorted(run["rows"], key=lambda r: (r["year"], r["yror"]))
            for f, k in (("join", "join"), ("leaving", "left")):
                d = h[k]
                # a year-only date of his (0/0/2016) is no date at all - it shows as
                # 0 in the editor - so it must not be copied onto a career row
                # either, or Manuel Barbosa's first season reads 0 as well. 1/1 is
                # refused for the same reason - see `authored_date_ok`.
                if d is None or not authored_date_ok(
                        d, club, seasons,
                        first_run=(f == "join" and sp is earliest)):
                    continue
                if not run["start"] <= int(d.get("year")) <= run["end"] + 1:
                    return 0
                take.append((rs[0] if f == "join" else rs[-1], f, d))
    for row, f, d in take:
        d = copy.deepcopy(d)
        d.set("id", "value")
        row[f] = d
    return len(take)


def career_sketch(ops):
    """A one-line fingerprint of the career the file reveals, for a record the
    model refuses to rebuild. Real records carry no name in the changeset, so
    this is how a record is recognised: open the id in the editor and compare.
    """
    produced, seen = set(), []
    for rec in ops:
        lsop, col, val, st = parse_op(rec)
        if st is None:
            continue
        ys, cl = st.get("year"), st.get("club")
        if ys is not None and ys not in produced and ys not in SENTINELS:
            seen.append((ys, cl[1] if cl else "-", st.get("apps"), st.get("gols")))
        if lsop == "1" and col == YEAR_COL and val is not None and val.get("value"):
            produced.add(int(val.get("value")))
    if not seen:
        return []
    return sorted(set(seen), key=lambda t: (t[0], str(t[1]), -1 if t[2] is None else t[2]))


def sketch_text(seen, names=None):
    """One line naming the career the file reveals, clubs named where known."""
    if not seen:
        return "no readable season"
    def club(c):
        nm = names.club(c) if names else None
        return nm or str(c)[-7:]
    body = ", ".join("%s %s %s/%s" % (y, club(c), "-" if a is None else a,
                                      "-" if g is None else g) for y, c, a, g in seen[:14])
    return "real %d-%d: %s%s" % (seen[0][0], seen[-1][0], body,
                                 " ..." if len(seen) > 14 else "")


def _replay_grid(ops, base):
    """The editor's own semantics, seeded with rows we already know: Clear wipes,
    Add appends a blank, DUPLICATE appends a copy of the row the snapshot cites,
    Remove deletes it, a cell op writes one column, and a snapshot resolves to the
    FIRST row that matches. An op that matches nothing is dropped, exactly as the
    editor drops it."""
    import clean_import as ci
    field = {v: k for k, v in ci.COL.items()}
    rows = [dict(r) for r in base]
    for rec in ops:
        lsop, col, val, st = parse_op(rec)
        if lsop == "3":
            rows = []
            continue
        if lsop == "0":
            rows.append(ci.new_row())
            continue
        row = next((r for r in rows if st is None or ci.snap_matches(r, st)), None)
        if row is None:
            continue
        if lsop == "4":
            rows.append(copy.deepcopy(row))
            continue
        if lsop == "2":
            rows.remove(row)
            continue
        name = field.get(col)
        if name is None:
            continue
        if val is None or val.tag == "null":
            row[name] = None
        elif val.tag == "record":
            # exactly as clean_import.replay stores a club or division cell: the
            # record itself, deep-copied. `club_el_from` takes a (kind, value)
            # pair from a SNAPSHOT and is not the same thing.
            row[name] = copy.deepcopy(val)
        elif val.tag == "date":
            row[name] = copy.deepcopy(val)
        elif val.tag == "boolean":
            row[name] = val.get("value") == "true"
        else:
            # a fee comes through as a float ("0.000000"), so do not insist on int
            v = val.get("value")
            if v is None:
                row[name] = None
            else:
                try:
                    row[name] = int(v)
                except ValueError:
                    try:
                        row[name] = float(v)
                    except ValueError:
                        row[name] = v
    return rows


def untick_played_youth(rows, dob_year=None):
    """A YOUTH season carries no figures - the user's own rule. A row with
    appearances or goals AND the youth tick is wrong, and it is wrong in the
    SOURCE: the author builds a career by DUPLICATING a row, a duplicate inherits
    the tick, and he fills the figures in afterwards without clearing it. Litos
    (Carlos Magalhaes) arrives as a youth player in four Boavista seasons of 27 to
    32 appearances, while the one season he built differently is clean; replaying
    his own ops reproduces it exactly, so this corrects HIM, not us (user,
    2026-09-08).

    A blank season escapes that test, so the author's second rule applies too: a
    season with no appearances and no goals, after the player turned 19, is not a
    youth season either. Quim kept a youth tick on 2021/22 at Vitoria, between two
    full seasons, because it had no figures to catch it (user, 2026-09-16).

    Returns how many ticks were removed."""
    n = 0
    for r in rows:
        if not r["ytht"]:
            continue
        played = (r["apps"] or 0) or (r["gols"] or 0)
        too_old = dob_year is not None and r.get("year") and r["year"] - dob_year > 19
        if played or too_old:
            r["ytht"] = False
            n += 1
    return n


def apply_flags(ops, kept, first_of, rows, real_of, K):
    """Copy the LOAN and YOUTH ticks from a faithful replay of the author's ops
    onto the rebuilt rows. A row is matched by the season it belongs to - his year
    for it is the real year plus his own shift - and by club, and only when
    exactly one replayed row fits. A youth tick is refused on a row that has
    appearances or goals: the user's own rule is that a youth season carries no
    figures, and that is the last line against a mis-placed tick."""
    import clean_import as ci
    base = []
    for ident, real_year in sorted(kept.items(), key=lambda kv: kv[1]):
        row = ci.row_from_olvl(first_of[ident])
        row["year"] = real_year
        base.append(row)
    replayed = _replay_grid(ops, base)
    # Match on CLUB and FIGURES, not on the year. A relabel moves years around and
    # the author's own shift is not always the dominant one the model picked - Pedro
    # Emanuel's file moves his rows a year further than `K` says, so matching by
    # year found nothing and his two added loan ticks were lost (3 loans in v14, 1
    # in v17). Appearances and goals survive a relabel, which makes them the stable
    # handle; anything ambiguous is skipped, exactly as the division edits are.
    def handle(r):
        return (ci.club_key(r), r["apps"] or 0, r["gols"] or 0)
    for row in rows:
        if real_of.get(id(row)) is None:
            continue
        hit = [r for r in replayed if handle(r) == handle(row)]
        if len(hit) != 1:
            continue
        src = hit[0]
        row["onln"] = bool(src["onln"])
        if not ((row["apps"] or 0) or (row["gols"] or 0)):
            row["ytht"] = bool(src["ytht"])
        elif src["ytht"] and not row["ytht"]:
            continue                            # a youth tick on a season with
                                                # figures is a mis-placed edit


def leading_youth(rows):
    """The block of YOUTH seasons a career opens with - ticked Youth, no figures.
    That is the shape the author writes: three Boavista years before Pedro
    Emanuel's first senior season."""
    out = []
    for r in sorted(rows, key=lambda r: (r["year"] or 0, r["yror"] or 0)):
        if r["ytht"] and not (r["apps"] or 0) and not (r["gols"] or 0):
            out.append(r)
        else:
            break
    return out


def authored_youth_rows(ops, kept, first_of, rows, shift):
    """Youth seasons the author ADDED to a real career, which the shift model
    cannot see (user request, 2026-09-08).

    He builds them by DUPLICATING a row, clearing its figures and ticking Youth,
    and `real_career` skips every insert and duplicate - so Pedro Emanuel's three
    Boavista youth years never arrive. Recovering them does not disturb the model:
    seed a replay with the database rows the model reconstructed, follow the
    author's whole stream, and compare the block of youth seasons his grid opens
    with against the one ours does. The difference is his addition, and it is
    appended in the seasons immediately before the career - which is where he put
    it - keeping his club. Only rows with NO figures are ever added, so nothing
    can land on a real season."""
    import clean_import as ci
    base = []
    for ident, real_year in sorted(kept.items(), key=lambda kv: kv[1]):
        row = ci.row_from_olvl(first_of[ident])
        row["year"] = real_year
        base.append(row)
    his = leading_youth(_replay_grid(ops, base))
    mine = leading_youth(rows)
    extra = len(his) - len(mine)
    if extra <= 0 or not rows:
        return []
    first = min(r["year"] for r in rows)
    out = []
    for i, src in enumerate(his[:extra]):
        row = ci.blank_row()
        row["year"] = first - extra + i
        row["ytht"] = True
        for f in ("club", "divi"):
            if src.get(f) is not None:
                row[f] = copy.deepcopy(src[f])
        out.append(row)
    return out


def real_career(ops, target_season):
    """Read a REAL database record's career out of the changeset.

    The author deletes every playing-history row from the prime season onwards
    and relabels the rest by ONE constant, and he touches every row - so each
    op's `olvl` snapshot is an image of that row as the database holds it, and
    the real career is in the file even though the database is not.

    Returns (rows, shift, note, extras) or (None, 0, reason, 0). `rows` are
    clean_import row dicts already moved to the target season; `extras` counts
    the author's own cell edits and inserted rows that are NOT reproduced.
    """
    import clean_import as ci
    if any(parse_op(rec)[0] == "3" for rec in ops):
        # the author cleared the grid himself, so the database rows are gone and the
        # whole career is authored in the file - replay it from empty, like a
        # created player (Gudjohnsen)
        stripped, doubled = ci.choose_repeat(ops, lambda o, d: ci.replay(o, doubled=d))
        rws = ci.replay(stripped, doubled=doubled)
        rws, notes = ci.clean(rws, None)
        if rws:
            last = max(x["year"] for x in rws)
            filled = any((x["apps"] or 0) > 0 or (x["gols"] or 0) > 0 for x in rws if x["year"] == last)
            sh = (target_season - 1 if filled else target_season) - last
            for x in rws:
                x["year"] += sh
                for f in ("join", "leaving"):
                    if x[f] is not None:
                        shift_date_year(x[f], sh)
            return rws, sh, "%d rows, authored after the author's own Clear, shift %+d" % (len(rws), sh), 0
        # a Clear that leaves nothing behind is a leftover from an old pass; fall
        # through and read the career the ordinary way
    produced, kept, deleted, ks, first_of, shift_seen = set(), {}, set(), Counter(), {}, {}
    ends, shift_all, divi_of, seq = {}, defaultdict(set), {}, {}
    extra_rows, chain_del, cell_edits = 0, 0, 0
    # A row can be relabelled in more than one step (Sergio Conceicao: 1992 -> 2006
    # in one pass, 2006 -> 2016 in the next). Only the END of that chain is the
    # author's intent, so follow it: a relabel keeps the row's club and stats, so
    # (year, club, apps, goals) identifies the row at each step.
    chain = {}
    for rec in ops:
        lsop, col, val, st = parse_op(rec)
        if lsop != "1" or col != YEAR_COL or st is None or val is None or not val.get("value"):
            continue
        cl = st.get("club")
        key = (st.get("year"), cl[1] if cl else None, st.get("apps") or 0, st.get("gols") or 0)
        yt = int(val.get("value"))
        if yt not in SENTINELS:
            chain[key] = yt

    def final_year(ident, first_target):
        y, seen = first_target, {ident[0]}
        for _ in range(12):
            nxt = chain.get((y, ident[1], ident[2], ident[3]))
            if nxt is None or nxt in seen:
                break
            seen.add(y)
            y = nxt
        return y
    for rec in ops:
        lsop, col, val, st = parse_op(rec)
        if lsop in ("0", "4"):
            extra_rows += 1
            continue
        if st is None:
            continue
        ys, cl = st.get("year"), st.get("club")
        ident = (ys, cl[1] if cl else None, st.get("apps") or 0, st.get("gols") or 0)
        first_touch = ys is not None and ys not in produced and ys not in SENTINELS
        if lsop == "2":
            if first_touch:
                deleted.add(ident)
            else:
                chain_del += 1
        elif lsop == "1":
            if col == YEAR_COL and val is not None and val.get("value"):
                yt = int(val.get("value"))
                if yt in SENTINELS:
                    # The author parks a row on the blank year and restores it a
                    # pass later (Hasselbaink's Atletico season). The park is not
                    # a deletion, so follow it to where the row ends up.
                    if first_touch:
                        fin = final_year(ident, yt)
                        if fin not in SENTINELS:
                            kept.setdefault(ident, ys)
                            first_of.setdefault(ident, rec)
                            shift_seen[ident] = fin - ys
                            shift_all[ident].add(fin - ys)
                            ends.setdefault(ident, fin)
                            ks[fin - ys] += 1
                            o = rec.find('*[@id="new_value"]/record[@id="olvl"]')
                            d = o.find('*[@id="divi"]/integer[@id="competition"]') if o is not None else None
                            n = o.find('integer[@id="yror"]') if o is not None else None
                            divi_of.setdefault(ident, (d.get("value") if d is not None else None,
                                                       n.get("value") if n is not None else None))
                    continue
                if first_touch:
                    kept[ident] = ys
                    first_of[ident] = rec
                    shift_seen[ident] = yt - ys
                    shift_all[ident].add(yt - ys)
                    ends[ident] = yt
                    ks[yt - ys] += 1
                    seq[ident] = len(seq)
                    o = rec.find('*[@id="new_value"]/record[@id="olvl"]')
                    d = o.find('*[@id="divi"]/integer[@id="competition"]') if o is not None else None
                    n = o.find('integer[@id="yror"]') if o is not None else None
                    divi_of.setdefault(ident, (d.get("value") if d is not None else None,
                                               n.get("value") if n is not None else None))
                produced.add(yt)
            elif col in STAT_COLS:
                cell_edits += 1
    # A row that is BOTH deleted and relabelled: keep it. You do not relabel a row
    # you want gone, and the delete is the older intent left in a cumulative file -
    # obeying it cost McCarthy a Porto season (two of his Porto rows have the same
    # 23 appearances, so one delete swallowed both).
    for k in list(kept):
        if k in deleted and k not in shift_all:
            del kept[k]
    if not kept:
        return None, 0, "no row is kept", 0
    if not ks:
        return None, 0, "no row is relabelled", 0
    # The author relabels every row by ONE constant; a row that appears to move by
    # some other amount is a second relabel of a row already counted, so keep the
    # dominant shift and drop the strays. If dropping them leaves a hole, the
    # contiguity check below refuses the record anyway.
    def dominant(counter):
        k = counter.most_common(1)[0][0]
        rest = sum(n for j, n in counter.items() if j != k)
        return k if counter[k] >= 2 * rest else None

    if len(ks) > 1 and dominant(ks) is None:
        # No majority among the first relabels - the author may have moved a row
        # in more than one step (Sergio Conceicao: 1992 -> 2006, then 2006 -> 2016).
        # Follow each chain to its end and see whether that agrees.
        ks2, seen2 = Counter(), {}
        for ident in kept:
            seen2[ident] = final_year(ident, ends[ident]) - kept[ident]
            ks2[seen2[ident]] += 1
        if dominant(ks2) is not None:
            ks, shift_seen = ks2, seen2

    K = ks.most_common(1)[0][0]
    dropped_years = set()
    # Two shifts one year apart are not a disagreement: a calendar-year league
    # overlaps a European season, so Solano's 1996 in Peru and his 1997 at Boca
    # are deliberately one and the same target year (his shifts split 3 and 3,
    # and there is nothing wrong with the record).
    if len(ks) > 1 and max(ks) - min(ks) > 1:
        if ks[K] < 2 * sum(n for k, n in ks.items() if k != K):
            return None, 0, "no dominant shift (%s)" % dict(ks), 0
        # The author re-reads a record from the real database in a later edition
        # and relabels the same row again, so one row can carry two first
        # relabels (Essien's 2002, Mark Hughes' 1985 and 1986). Where one of them
        # is the majority shift, that is the reading to keep - dropping the row
        # punches a hole in a career that is perfectly consistent.
        core = [y for i, y in kept.items() if shift_seen[i] == K]
        lo, hi = (min(core), max(core)) if core else (1, 0)
        for ident in [i for i, y in kept.items() if shift_seen[i] != K]:
            if K in shift_all[ident]:
                shift_seen[ident] = K
                continue
            # A stray INSIDE the career is a real season the author nudged by a
            # different amount, usually to pull two rows of one season apart
            # (Hasselbaink's 1990). Keep it where the database has it. Only a
            # stray outside the career is dropped - that one is a misread.
            if lo <= kept[ident] <= hi:
                shift_seen[ident] = K
                continue
            dropped_years.add(kept[ident])
            del kept[ident]
    if not kept:
        return None, 0, "nothing is left once the stray shifts are dropped", 0
    # Two rows in one season at one club are a real pair when the database keeps
    # them apart - a different competition, or a different order within the season
    # (Beckham played four league games and none in Europe for United in 1994).
    # The SAME slot twice is one row seen at two moments, because the author edited
    # a cell and the later image reads as a second row: Giggs' 1990 appears as 0/0
    # and again as 2/1, and 2/1 is the row. Keep his latest image of it.
    slots = defaultdict(list)
    for k, y in kept.items():
        slots[(y, k[1], divi_of.get(k))].append(k)
    for group in slots.values():
        # the latest image that still records a figure - a later BLANK image is
        # the author retyping the row, not him wiping the season (Sam Field)
        for k in sorted(group, key=lambda i: (i[2] + i[3] > 0, seq.get(i, 0)))[:-1]:
            del kept[k]
    # The author BLANKS the row of the season the player is BASED ON - it is the
    # season about to be played, not one he has played (Varela's Estrela row, no
    # apps and no goals). The row's database figures must not be restored over
    # that, and the row itself does not belong in the career: the anchor is the
    # last season that still records figures.
    cleared = set()
    for rec in ops:
        lsop, col, val, st = parse_op(rec)
        if lsop != "1" or col not in (APPS_COL, GOLS_COL) or st is None:
            continue
        if val is not None and val.tag != "null" and val.get("value"):
            continue
        cl = st.get("club")
        cleared.add((cl[1] if cl else None, st.get("apps") or 0, st.get("gols") or 0))
    while kept and cleared:
        tail = max(kept.values())
        drop = [i for i, y in kept.items() if y == tail and (i[1], i[2], i[3]) in cleared]
        if not drop or len(drop) == len(kept):
            break
        for i in drop:
            del kept[i]

    years = sorted(set(kept.values()))
    # A hole the model MADE is a misread: rows dropped as strays leave seasons the
    # Clear would then delete for good. A hole that was always there is just a
    # career, and plenty of them are (Hasselbaink spent 1993 and 1994 at clubs the
    # database does not carry).
    lost = [(a, b) for a, b in zip(years, years[1:])
            if b - a > 1 and any(a < y < b for y in dropped_years)]
    if lost:
        return None, 0, "the kept career has a hole (%s)" % ", ".join(
            "%d to %d" % (a, b) for a, b in lost), 0
    # One shift for the whole career. Placing rows at the author's own chain-end
    # target was tried and is worse: a chain end can be followed into an
    # unrelated row and it collapsed Beckham's three youth seasons onto one year.
    last = max(kept.values())
    filled = any(k[2] > 0 or k[3] > 0 for k, y in kept.items() if y == last)
    shift = (target_season - 1 if filled else target_season) - last
    rows, of_row, real_of = [], {}, {}
    for ident, real_year in sorted(kept.items(), key=lambda kv: kv[1]):
        row = ci.row_from_olvl(first_of[ident])
        real_of[id(row)] = real_year
        # every year this row has ever carried, so a later cell edit that cites it
        # by one of them can be recognised
        path, y = {real_year}, ends.get(ident)
        while y is not None and y not in path:
            path.add(y)
            y = chain.get((y, ident[1], ident[2], ident[3]))
        of_row[id(row)] = path
        row["year"] = real_year + shift
        for f in ("join", "leaving"):
            if row[f] is None:
                continue
            shift_date_year(row[f], shift)
            # The author edits a row's dates in one pass and its year in another,
            # so the two travel separately and the date can end up decades from
            # the season it belongs to (Capucho joining in 1/7/2050, Varela in
            # 2032). A row is ONE season: its dates are re-anchored to it, day and
            # month kept.
            m = int(row[f].get("month") or 0)
            row[f].set("year", str(row["year"] if m >= 7 or m < 1 else row["year"] + 1))
        rows.append(row)
    # The author's own cell edits: apps, goals, division, youth and loan flags,
    # order, fee. The rebuild writes the row the DATABASE holds, so without this
    # his edits are silently dropped - that is how Steinsson lost the divisions
    # he had typed in himself. An edit cites the row as it was, so match it on
    # club, apps and goals, and apply it only when exactly one row can be meant.
    # The division, the fee, and the LOAN and YOUTH flags. A FIGURE edit still
    # cannot be placed safely - the author also DUPLICATES rows, a duplicate is
    # identical to its original at the moment it is made, and apps and goals are
    # part of the key an edit is matched on, so an edit meant for one lands on the
    # other (it put 4 appearances on the Solano season that has 40).
    #
    # A flag is not in that key, so it carries none of that risk, and the unique-
    # match guard below is the same one the division already relies on. The flags
    # matter: FM's database has Pedro Emanuel on loan at Penafiel only, while the
    # author ticked On Loan at Marco 09 and Ovarense as well (user, 2026-09-08) -
    # dropping those left two of his three loan spells reading as permanent moves.
    ROW_KEY = {"1684633193": "divi", "1667330920": "cash"}
    applied = 0
    for rec in ops:
        lsop, col, val, st = parse_op(rec)
        key = ROW_KEY.get(col)
        if lsop != "1" or key is None or st is None:
            continue
        cl = st.get("club")
        want = (cl[1] if cl else None, st.get("apps") or 0, st.get("gols") or 0)
        hit = [r for r in rows
               if (club_of(r["club"])[1] if r["club"] is not None else None,
                   r["apps"] or 0, r["gols"] or 0) == want]
        if len(hit) > 1:                        # same club and figures twice: the
            ys = st.get("year")                 # year the edit cites tells them apart
            hit = [r for r in hit if ys in of_row.get(id(r), ())]
        if len(hit) != 1:
            continue
        row = hit[0]
        row[key] = copy.deepcopy(val) if val is not None and val.tag != "null" else None
        applied += 1
    cell_edits = max(0, cell_edits - applied)
    unrecreated = max(0, extra_rows - chain_del)
    # LOAN and YOUTH flags the author changed. These cannot be placed by matching
    # the row on (club, apps, goals): he duplicates a row and changes its figures
    # AFTERWARDS, so an edit meant for the copy matches the original instead. That
    # put Litos - three youth years then three loans then six senior seasons at
    # Boavista - down as a youth player in four of his senior seasons (user,
    # 2026-09-08), and it is the same hazard the division note above describes.
    #
    # A faithful REPLAY knows which row really ends up flagged, so ask it: the
    # author's frame is the real year plus HIS shift (K), ours is the real year
    # plus ours, which lines the two grids up. No match, or more than one, leaves
    # the flag as the database has it - what happened before any of this.
    apply_flags(ops, kept, first_of, rows, real_of, K)
    untick_played_youth(rows)
    # Youth seasons the author ADDED are invisible to the model above, because it
    # only ever shifts rows the database already holds. Recover just those.
    youth = authored_youth_rows(ops, kept, first_of, rows, shift)
    rows = youth + rows
    note = "%d rows (real %d-%d), shift %+d (file %+d)%s" % (
        len(rows) - len(youth), min(kept.values()), max(kept.values()), shift, K,
        ", %d authored youth season(s) recovered" % len(youth) if youth else "")
    return rows, shift, note, cell_edits + max(0, unrecreated - len(youth))


def real_span(note):
    """(first, last, rows, shift) of the REAL career behind a rebuilt record, or
    None when there is none to read: a stub, or a career the author typed from
    scratch after his own Clear."""
    m = re.match(r"(\d+) rows \(real (\d+)-(\d+)\), shift ([+-]\d+)", note)
    return (int(m.group(2)), int(m.group(3)), int(m.group(1)), int(m.group(4))) if m else None


def mkdate(day, month, year):
    return ET.Element("date", id="value", day=str(day), month=str(month), year=str(year), time="0")


# Two properties hold the date the player joined the club. Which one the editor
# shows is not ours to guess, so BOTH are written: Bakero came out right with only
# Pcjd, while Zidane, Pochettino and Etxeberria stayed wrong, and the one thing
# they had that he did not was a PCNj - twice CLEARED by the author, which leaves
# the field empty and the database's own date on show.
# ------------------------------------------------------- season calendars ---

# When a league's season starts is a property of the NATION, not of the tier: the
# Argentine fourth division runs February to December exactly like the Premier
# Division, so one entry per country covers every club in it. Division would be
# the finer key and is in the same index record, but it goes null for a club
# outside a playable league - defunct, merged, dropped to regional football -
# which is disproportionately where a legend's old clubs sit.
#
# This governs DERIVED dates only. A date the author typed himself always wins;
# his own grid is the authority and is read first (dates_from_spells).
#
# The list is real-world league calendars, NOT induced from the author's files:
# his own dates are too inconsistent to induce from (in the Argentina file itself
# Argentine clubs come out 7 European-style against 4 calendar-year, and Brazil is
# 15 calendar-year in the Portugal file against 1 in Italy's). The report's
# "season calendars" section lists every nation where his dates disagree with this
# table, so a wrong entry here is visible rather than silent.
CALENDAR_YEAR_NATIONS = frozenset({
    # South America, minus Argentina - see ERA_CHANGED_NATIONS
    "Bolivia", "Brazil", "Chile", "Colombia", "Ecuador", "Peru", "Paraguay",
    "Uruguay", "Venezuela",
    # the Nordics: spring to autumn, unchanged for a century, no era problem
    "Norway", "Sweden", "Finland", "Iceland",
    # MLS: February to November inside one calendar year for the whole era these
    # legends played, and the author dates it that way himself (4 joins on 1/1,
    # none on 1/7). USER DECISION 2026-09-08, overriding the "never moved" test:
    # MLS switches to a summer-to-spring calendar from 2027, so by that test it
    # belongs in ERA_CHANGED_NATIONS - he wants the dates right for the era
    # instead. Both spellings: the index files clubs under the long one and a few
    # people under the short one.
    "The United States of America", "United States",
})

# Leagues whose season calendar has MOVED, so no single constant describes them.
# Argentina ran TWO championships inside one calendar year through the 70s and
# 80s (Metropolitano and Nacional), then unified onto the European calendar
# (Apertura/Clausura), then went back to a calendar year - so which is right
# depends on the season, not the country. These are left on the European default,
# which is what the author himself uses for them, and a REAL record whose career
# touches one is reported instead of silently re-dated. Created players need none
# of this: their careers are the author's own invention and are already coherent.
# USER DECISION 2026-09-09: Argentina comes OUT. Membership here never changed a
# date - Argentina is not in CALENDAR_YEAR_NATIONS, so its clubs always derived
# European boundaries - it only made every real career touching one get reported.
# Every transported season sits in the modern era, after the calendar settled, so
# the flag was noise: 161 rows across the files.
ERA_CHANGED_NATIONS = frozenset()

EURO_SEASON = ((1, 7), (30, 6), 1)      # join, leave, years to add for the leave
CALENDAR_SEASON = ((1, 1), (31, 12), 0)

# FM's `Unknown Club` is ONE record used freely all over the database - the author
# has assigned it in many different countries - so it is not a club and nothing
# about it can be read as evidence of a calendar (user, 2026-09-08). It has no
# nation, so it takes the European default like any unresolved club, and it must
# never be pooled per-id: doing so moved a Rosenborg boundary from 30/12 to 2/7.
PLACEHOLDER_CLUBS = frozenset({"Unknown Club"})

# A legend's FIRST club is his home or youth club, so when it is extinct - and the
# index therefore gives it no nation - the player's own nation is what dates it.
# John Harkes started at Albany Capitals and got 1/7 while D.C. United got 1/1, in
# one career. Measured over six files: 122 nation-less first clubs against 337
# later ones, and every first one checked is in the player's own country (Solskjaer
# and Leonhardsen at Clausenengen, Vilfort at Skovlunde, Wohlfahrt at St. Veit,
# and Marcos Senna at Rio Branco de Andradas - a Brazilian club in the SPAIN file,
# which is why the PLAYER's nation is the right source and the file's country is
# not).
#
# It is deliberately ONLY the first club. Read wider, the same idea dated FC RWDM
# Brussels - a Belgian club on a Belgian stint next to Standard Liege - as
# calendar-year because the player was Norwegian, which v9 had right. Mid-career
# clubs are where foreign stints are, so they keep the European default.
EXTINCT_FROM_PLAYER = "(extinct first club, the player's nation)"

# Better than either of those, and it is FM's own record of where he played: the
# playing-history row names the COMPETITION for that season (`divi` ->
# `competition`), and the index resolves a competition WITH its nation. Measured
# over four files: 83 nation-less clubs appear on a dated row, and 79 of them are
# placed this way - only 4 competitions are missing from the index. It settles the
# case the player's nation got wrong, because RWDM Brussels' row records the
# Jupiler Pro League, so the club is Belgian however Norwegian the player is.
# Read from the SOURCE snapshots: a rebuilt career is written onto blank rows and
# never re-emits `divi`.
EXTINCT_FROM_COMPETITION = "(extinct club, the competition on his row)"
CLID_COLUMN = "1668049252"              # the club cell of a playing-history row


class Seasons:
    """Season boundaries for a club, from its nation. An unknown club falls back
    to the European calendar - what every derived date used before nations were
    read - so a cache miss can never move a date that was already right."""

    def __init__(self, namer=None):
        self.namer = namer
        self.seen = Counter()           # nation -> derived dates written
        self.inherited = {}             # B team -> parent it took its nation from
        self.player_nation = None       # nation of the person being processed
        self.first_club = None          # his earliest club, the only one it dates
        self.from_player = {}           # club -> (player, nation) it was dated by
        self.seen_cal = {}              # label -> the calendar it resolved to
        self.club_from_comp = {}        # nation-less club -> nation, via a competition
        self.comp_basis = {}            # that club -> the competition that named it
        self.from_comp = Counter()      # that club -> derived dates it received

    def for_player(self, who, nation, first_club=None):
        """Whose career is being written, and which club he started at. Consulted
        only for a first club the index gives no nation."""
        self.player_nation = nation or None
        self.first_club = first_club
        self._who = who

    def nation(self, club):
        """The club's nation. A B team with none of its own takes its parent's,
        which is how an extinct reserve side still lands on the right calendar."""
        if self.namer is None or not club:
            return None
        n = self.namer.nation(club)
        if n and not ((self.namer.entry("team", club) or {}).get("na")):
            self.inherited[club] = self.namer.parent_of(club)
        return n

    def _of(self, club):
        n = self.nation(club)
        if n is None and club and club in self.club_from_comp:
            cn = self.club_from_comp[club]
            cal = CALENDAR_SEASON if cn in CALENDAR_YEAR_NATIONS else EURO_SEASON
            self.seen_cal[EXTINCT_FROM_COMPETITION] = ("calendar year"
                                                       if cal is CALENDAR_SEASON else "European")
            self.from_comp[club] += 1
            return EXTINCT_FROM_COMPETITION, cal
        if (n is None and club and self.player_nation
                and self.first_club is not None and club == self.first_club
                and (self.namer.club(club) if self.namer else None) not in PLACEHOLDER_CLUBS):
            self.from_player[club] = (getattr(self, "_who", None), self.player_nation)
            cal = (CALENDAR_SEASON if self.player_nation in CALENDAR_YEAR_NATIONS
                   else EURO_SEASON)
            self.seen_cal[EXTINCT_FROM_PLAYER] = ("calendar year" if cal is CALENDAR_SEASON
                                                  else "European")
            return EXTINCT_FROM_PLAYER, cal
        return n, (CALENDAR_SEASON if n in CALENDAR_YEAR_NATIONS else EURO_SEASON)

    def calendar_year(self, club):
        return self._of(club)[1] is CALENDAR_SEASON

    def bounds(self, club, year):
        """(start, end) of the season labelled `year` at this club, as dates. Does
        not count towards `seen` - it is a measurement, not a date written."""
        _n, ((jd, jm), (ld, lm), off) = self._of(club)
        return date(year, jm, jd), date(year + off, lm, ld)

    def join(self, club, year):
        """Start of the season labelled `year` at this club."""
        n, ((d, m), _, _) = self._of(club)
        self.seen[n] += 1
        return mkdate(d, m, year)

    def leave(self, club, end_year):
        """End of the season labelled `end_year` at this club. A European season
        ends in the NEXT calendar year, a calendar-year one in its own."""
        n, (_, (d, m), off) = self._of(club)
        self.seen[n] += 1
        return mkdate(d, m, end_year + off)


def career_oddities(rows, shift, namer):
    """Shapes worth a human eye in a real record whose career touches a league
    with a moved calendar. None of these is a converter fault - FM's own data
    really is like this - and none is repaired, only reported.

    Verified against the three the user picked out of the Argentina file: Veron
    (1996 split between Boca and Sampdoria), Bochini (57 apps in 1977, which is
    the Metropolitano and the Nacional added together) and Celso Ayala (two
    Olimpia seasons with no apps or goals at all)."""
    import clean_import as ci
    out = []

    def real(y):
        return y - shift

    def name(r):
        club = ci.club_key(r) if r["club"] is not None else None
        return (namer.club(club) if namer is not None and club else None) or "?"

    by_year = defaultdict(list)
    for r in rows:
        by_year[r["year"]].append(r)

    for y in sorted(by_year):
        rs = by_year[y]
        if len(rs) > 1:
            what = ", ".join(f"{name(r)} {r['apps'] if r['apps'] is not None else '?'} apps"
                             for r in sorted(rs, key=lambda r: r["yror"]))
            out.append(f"{real(y)}: {len(rs)} rows in one year ({what})")
        for r in rs:
            if r["apps"] is None and r["gols"] is None:
                out.append(f"{real(y)}: no apps or goals recorded ({name(r)})")
            elif (r["apps"] or 0) > 50:
                out.append(f"{real(y)}: {r['apps']} apps in one season ({name(r)}) - "
                           f"two championships added together?")
    years = sorted(by_year)
    for a, b in zip(years, years[1:]):
        if b - a > 1:
            out.append(f"{real(a)}-{real(b)}: no rows for "
                       f"{', '.join(str(real(y)) for y in range(a + 1, b))}")
    return out


# `Pcjd` is forced to the spell that opens the contract. `PCNj` - the date he
# moved to his based nation - is NOT: working out when a man moved country is a
# different calculation from when he signed, and the author's own value, shifted,
# is good enough (user rule, 2026-09-08).
JOINED_PROPS = ("Pcjd",)
NATION_MOVE_PROP = "PCNj"
START_PROP = "Pcsd"                  # contract start
EXPIRY_PROP = "Pcex"                 # contract expiry


def sync_contract_dates(primary, recs_by_prop, join_el, build, target_season,
                        seasons=None, club=None):
    """The contract on the record must agree with the club spell that opens it.

    The joined-club date is forced: the author writes it in whatever season he
    was working in, so it drifts from the spells the rebuild produces (Pantic
    reads 2016 against a Panionios spell that starts in 2021), and the open spell
    is the source of truth. Fields that merely track it move with it.

    The contract itself is only FILLED IN, never overruled. A start or expiry the
    author set is his and gets shifted like every other date. Where the file says
    nothing the FM database's own value stands - the start of the target season
    for anyone under contract - so a plausible one is invented instead: the start
    somewhere between the day he joined and the new season, the expiry at the end
    of a season two to five years out. The draw is seeded from the record id, so
    the same file always converts to the same dates.
    """
    if join_el is None:
        return [], []

    def val(el):
        """The date on a change (its new value), or on a raw element."""
        if el is None:
            return None
        if el.tag == "date":
            return dtup(el)
        v = el.find('*[@id="new_value"]')
        return dtup(v) if v is not None and v.tag == "date" else None

    def op(prop, want, was):
        rec = ET.Element("record")
        ET.SubElement(rec, "integer", id="database_table_type", value=PERSON_TABLE)
        ET.SubElement(rec, "large", id="db_unique_id", value=primary)
        ET.SubElement(rec, "unsigned", id="property", value=str(prop_id(prop)))
        ET.SubElement(rec, "date", id="new_value", day=str(want[0]), month=str(want[1]),
                      year=str(want[2]), time="0")
        ET.SubElement(rec, "integer", id="version", value=str(build))
        # every change in the file carries one, and a change without it does not
        # take: this is why the joined dates read as the database's own values
        ET.SubElement(rec, "integer", id="db_random_id",
                      value=str(rng_id.randint(1, 2 ** 31 - 1)))
        ET.SubElement(rec, "date", id="odvl", day=str(was[0]), month=str(was[1]),
                      year=str(was[2]), time="0")
        return rec

    rng_id = random.Random(int(primary) ^ 0x5EED)
    want = (join_el.get("day"), join_el.get("month"), join_el.get("year"))
    written, dropped = [], []
    for prop in JOINED_PROPS:
        old = recs_by_prop.get(prop) or []
        if old and val(old[-1]) == want:
            continue                                   # already says the right thing
        # `odvl` is decoration on a scalar change: a probe set the same field four
        # ways (the editor's own value, empty, no odvl at all, the new value
        # itself) and all four took. What matters is ORDER - see below.
        written.append(op(prop, want, val(old[-1]) if old and val(old[-1]) else NULL_DATE))
        dropped.extend(old)

    def unset(prop):
        # no change at all, or the author's last word CLEARS the field
        old = recs_by_prop.get(prop) or []
        return not old or val(old[-1]) is None

    rng = random.Random(int(primary))
    # "the start of the new season" is the club's own season, so an Argentine
    # contract runs to 31 December and a Spanish one to 30 June
    (sd, sm), (ed, em), eoff = (seasons._of(club)[1] if seasons is not None
                                else EURO_SEASON)
    joined_year = int(want[2])
    joined_on = date(joined_year, int(want[1]), int(want[0]))

    def prior(prop):
        old = recs_by_prop.get(prop) or []
        v = val(old[-1]) if old else None
        if v is None:
            return None
        try:
            return date(int(v[2]), int(v[1]), int(v[0]))
        except ValueError:
            return None

    # Date Joined is FORCED to the spell that opens the contract, so an authored
    # contract date can end up on the wrong side of it: Pietro Rava was signed and
    # joined on the same day in the author's file (1/7/2015), but the rebuilt spell
    # puts him at the club in 2023 while his signed date only shifts to 2021 - two
    # years before he arrives. Where that happens the authored date is no longer
    # usable and is re-drawn by the rules below; where it still fits, it stands.
    stale = {}
    for prop, bad in ((START_PROP, lambda d: d < joined_on),
                      (EXPIRY_PROP, lambda d: d <= joined_on)):
        d = prior(prop)
        stale[prop] = d is not None and bad(d)
        if stale[prop]:
            dropped.extend(recs_by_prop.get(prop) or [])
    # USER RULES, 2026-09-08. Only ever FILLS what the file leaves empty.
    #
    # Last contract signed: a real date somewhere between the season AFTER he
    # joined and the current one, and never more than four years back - a player
    # who joined long ago has re-signed since, one who joined last season may not
    # have. A window that closes before it opens means no contract has been
    # signed yet, so the field stays empty (he joined this season), and a window
    # of exactly one season is a coin toss between "still on his first contract"
    # and "re-signed after a year".
    signed_year = None
    if unset(START_PROP) or stale[START_PROP]:
        lo, hi = max(joined_year + 1, target_season - 4), target_season
        if lo < hi:
            a, b = date(lo, sm, sd), date(hi, sm, sd)
            d = a + timedelta(days=rng.randint(0, (b - a).days))
            signed_year = d.year
            written.append(op(START_PROP, (d.day, d.month, d.year), NULL_DATE))
        elif lo == hi and rng.random() < 0.5:
            signed_year = hi
            written.append(op(START_PROP, (sd, sm, hi), NULL_DATE))
    else:
        got = val((recs_by_prop.get(START_PROP) or [])[-1])
        signed_year = int(got[2]) if got else None      # dtup holds strings
    # Contract expires: the end of a season from the current one out, capped at
    # six years after the contract was signed - a deal signed in 2021 cannot still
    # be running in 2031. With no signed date to cap against, four years out.
    if unset(EXPIRY_PROP) or stale[EXPIRY_PROP]:
        # never before he arrives: a contract that expires the season he joins is
        # not a contract (Jenilson joined 1/7/2026 and expired 30/6/2026)
        lo = max(target_season + eoff, joined_year + 1)
        hi = (signed_year + 6) if signed_year else (target_season + eoff + 3)
        written.append(op(EXPIRY_PROP, (ed, em, rng.randint(lo, max(lo, hi))), NULL_DATE))
    return written, dropped


def spells_from_career(rows, pnph_ops, shift, offset, namer=None, authored_left=False,
                       seasons=None):
    """Club spells derived from the REBUILT career, so the two grids can never
    disagree: consecutive seasons at one club are one spell. The author's own
    spell dates are used wherever a real spell lines up with the run (they carry
    mid-season transfers, e.g. Rooney's 31 August), otherwise 1 July and 30 June.
    The last spell is left open - the player is still there.

    Reading the spells grid directly does not work on a heavily rewritten record:
    the dates are rewritten edition after edition and a chained snapshot is
    indistinguishable from a real spell (Drogba)."""
    import clean_import as ci
    seasons = seasons if seasons is not None else Seasons(namer)
    # A loan does not interrupt the spell at the parent club: Lampard's season on
    # loan at Swansea sits inside one West Ham spell, not between two of them.
    # Loans get their own spell, nested, and never break the chain.
    runs, loans = [], []
    for r in sorted(rows, key=lambda r: (r["year"], r["yror"])):
        club = ci.club_key(r)
        if r["onln"]:
            if loans and loans[-1]["club"] == club and loans[-1]["end"] >= r["year"] - 1:
                loans[-1]["end"] = r["year"]
                loans[-1]["rows"].append(r)
            else:
                loans.append({"club": club, "ref": r["club"], "start": r["year"], "end": r["year"],
                              "join": r["join"], "left": r["leaving"], "loan": True, "rows": [r]})
            continue
        if runs and runs[-1]["club"] == club:
            runs[-1]["end"] = r["year"]
            runs[-1]["rows"].append(r)
            continue
        runs.append({"club": club, "ref": r["club"], "start": r["year"], "end": r["year"],
                     "join": r["join"], "left": r["leaving"], "loan": False, "rows": [r]})
    # A B team is not a transfer. If the player never changed main club - his B
    # team years run straight into the first team's - the first team's spell
    # starts when he joined the B team, and the B spell sits inside it, exactly
    # like a loan (Julen Guerrero: Bilbao Athletic 2019 then Athletic Club).
    # Whether two clubs are one club and its B team cannot be read off the
    # career: a season spent at both of them, neither on loan, is what a MID-SEASON
    # TRANSFER looks like too (Abbondanzieri's 2015 at Rosario Central and Boca).
    # Only the club's own name settles it, so is_b_team is the test - and every
    # club in the file is looked up before the rebuild starts, so the answer never
    # depends on what happens to be cached.
    def family(x, y):
        return namer is not None and (namer.is_b_team(x, y) or namer.is_b_team(y, x))

    if namer is not None:
        i = 0
        while i < len(runs) - 1:
            a, b = runs[i], runs[i + 1]
            # consecutive RUNS already means no other main club in between - a loan
            # year sits between Voro's Valencia B and his Valencia, and must not
            # break the pair
            if family(a["club"], b["club"]):
                child, parent = (a, b) if namer.is_b_team(a["club"], b["club"]) else (b, a)
                # the date he joined the CLUB is the earlier of the two runs, and
                # the author's own first-team date must not override it
                first = child if child["start"] <= parent["start"] else parent
                parent["start"] = min(parent["start"], child["start"])
                j = first["join"] \
                    if authored_date_ok(first["join"], first["club"], seasons,
                                        first_run=True) \
                    else seasons.join(first["club"], first["start"])
                j = copy.deepcopy(j)
                j.set("id", "value")
                parent["join"], parent["force"] = j, j
                child["loan"] = True
                loans.append(child)
                runs.remove(child)
                continue
            i += 1
        # pulling the B years into the first team can leave the first team either
        # side of them - Sergi Barjuan's Barcelona 2016 and his Barcelona 2019 are
        # one spell, not two
        i = 0
        while i < len(runs) - 1:
            if runs[i]["club"] == runs[i + 1]["club"]:
                runs[i]["end"] = max(runs[i]["end"], runs[i + 1]["end"])
                runs[i]["rows"] = runs[i]["rows"] + runs[i + 1]["rows"]
                if runs[i].get("force") is None and runs[i + 1].get("force") is not None:
                    runs[i]["force"] = runs[i + 1]["force"]
                del runs[i + 1]
                continue
            i += 1

    # The author's OWN last word on a spell's dates beats any old image: he keeps
    # re-setting them edition after edition (Henry's Monaco join went 1/7/2006 ->
    # 2007 -> 2008 -> 2009), and those values are already shifted to the file's own
    # season, so they need only the person's offset on top.
    last_set, last_ref = defaultdict(dict), {}
    for rec in pnph_ops:
        lsop, col, val, st = parse_op(rec)
        if lsop != "1" or st is None:
            continue
        ref = st.get("club")
        club = ref[1] if ref else None
        if club is None:
            continue
        olvl = rec.find('*[@id="new_value"]/record[@id="olvl"]')
        t = olvl.find('*[@id="team"]') if olvl is not None else None
        if t is not None and t.tag == "record":
            last_ref[club] = t
        for f, colid in (("join", SPELL["join"]), ("left", SPELL["left"])):
            if col == colid:
                if val is not None and val.tag == "date" and int(val.get("year")) not in SENTINELS:
                    d = copy.deepcopy(val)
                    shift_date_year(d, offset)
                    d.set("id", "value")
                    last_set[club][f] = d
                else:
                    last_set[club][f] = None          # the author cleared it
    # real spell dates, first touch only (a state an earlier op produced is not real)
    produced, real, lead = set(), {}, {}
    for rec in pnph_ops:
        lsop, col, val, st = parse_op(rec)
        if st is None:
            continue
        ref = st.get("club")
        club = ref[1] if ref else None
        j, l = st.get("join"), st.get("left")
        state = (club, j, l)
        if state not in produced and club is not None and j not in (None, NULL_DATE):
            # a spell starting in January belongs to the season that began the
            # previous July (Henry joined Juventus on 18 January), so register it
            # under both readings and let the run pick the one that fits
            y, m = int(j[2]), int(j[1])
            olvl = rec.find('*[@id="new_value"]/record[@id="olvl"]')
            ref = olvl.find('*[@id="team"]') if olvl is not None else None
            real.setdefault((club, y + shift), (j, l))
            real.setdefault((club, (y if m >= 7 else y - 1) + shift), (j, l))
            if m >= 1 and (club not in lead or y < lead[club][0]):
                lead[club] = (y, j, ref)

        if lsop == "1" and val is not None:
            if col == SPELL["join"] and val.tag == "date":
                produced.add((club, dtup(val), l))
            elif col == SPELL["left"] and val.tag == "date":
                produced.add((club, j, dtup(val)))
            elif col == SPELL["team"]:
                r2 = club_of(val)
                produced.add((r2[1] if r2 else None, j, l))
        produced.add(state)
    def season(el):
        y, m = int(el.get("year")), int(el.get("month"))
        return y if m >= 7 else y - 1

    def fits(el, lo, hi):
        # a year-only date (0/0/YYYY) does not round-trip in the editor, so it is
        # never carried into a rebuilt spell. 1 January is the same thing wearing a
        # date: it is what the editor holds when only the year is known, and taking
        # it literally puts a summer move in the middle of the previous season.
        if el is None or is_year_only(el) or int(el.get("month")) < 1:
            return False
        if int(el.get("day")) == 1 and int(el.get("month")) == 1:
            return False
        return lo <= season(el) <= hi or lo <= int(el.get("year")) <= hi

    out = []
    for n, run in enumerate(runs):
        mine = last_set.get(run["club"], {})
        hit = real.get((run["club"], run["start"]))
        join = copy.deepcopy(run["force"]) if run.get("force") is not None else None
        # the author's own last word, but only where it still fits this run: his
        # spell dates often lag his career relabelling by an edition or two
        # (Rooney), and following them blindly would put the two grids back out of
        # step - which is the very thing rebuilding the spells is meant to prevent
        if join is None and fits(mine.get("join"), run["start"], run["start"]):
            join = copy.deepcopy(mine["join"])
        # a leave date belongs to the END of the run, not anywhere inside it
        if join is None and hit:
            j = hit[0]
            cand = mkdate(j[0], j[1], int(j[2]) + shift)
            if fits(cand, run["start"], run["start"]):
                join = cand
        derived = False
        if join is None:
            # The row's own join date, but held to the same standard as his spell
            # date above: `fits` refuses 1 January there because it is FM's "the
            # year is known, the day is not", and this branch had no guard at all -
            # which is the whole of Lucho Gonzalez's Huracan spell reading 1/1/2015
            # against a career row labelled 2014 (user, 2026-09-09). Deriving from
            # the RUN gets the season right; coercing the date in place could not,
            # since 1/1/2015 would become 1/7/2015, a year late.
            if authored_date_ok(run["join"], run["club"], seasons, first_run=(n == 0)):
                join = copy.deepcopy(run["join"])
            else:
                join = seasons.join(run["club"], run["start"])
                derived = True                  # nothing said when: see the spread below
            if join.get("id") != "value":
                join.set("id", "value")
        out.append({"ref": run["ref"], "join": join, "left": None, "run": run,
                    "derived_join": derived})

    # Two clubs whose runs START in the same season both derive that season's own
    # opening date, and the chain - a spell ends when the next begins - then leaves
    # the first of them beginning and ending on the same day. Petkovic played for
    # Red Star, Sevilla and Real Madrid in 1995/96, so Sevilla collapsed to
    # 1/7 -> 1/7. Nothing in a career row says WHEN inside a season a move
    # happened, so the joins are spread evenly across it in row order: invented,
    # exactly like the 1 July they replace, but ordered and non-degenerate.
    # A run already under way when the season opens holds the first slot, so a
    # season shared by a leaver and two arrivals is cut in three, not two.
    # Only DERIVED joins move - a date the author gave, or one read off the real
    # database, stands where it is.
    def as_date(el):
        return date(int(el.get("year")), int(el.get("month")), int(el.get("day")))

    same_season = defaultdict(list)
    for sp in out:
        if sp.get("run") is not None and sp.get("derived_join"):
            same_season[sp["run"]["start"]].append(sp)
    for year, group in same_season.items():
        carry = any(r["start"] < year <= r["end"] for r in runs)
        slots = len(group) + (1 if carry else 0)
        if slots < 2:
            continue
        # order them the way the career does, by the row order WITHIN this season -
        # a run reaching into the next season has a low row order there, which is
        # not where it belongs here (Real Madrid sorted ahead of Sevilla on it)
        group.sort(key=lambda sp: min(r["yror"] for r in sp["run"]["rows"]
                                      if r["year"] == year))
        lo, season_end = seasons.bounds(group[0]["run"]["club"], year)
        # stop at the next move, not at the end of the season: the season after a
        # calendar-year club opens on 1 January, and spreading to 30 June past it
        # left Racing Santander with a two-day spell before Vitoria
        mine = {id(sp) for sp in group}
        later = [as_date(sp["join"]) for sp in out
                 if id(sp) not in mine and as_date(sp["join"]) > lo]
        hi = min([season_end] + later)
        if hi <= lo:
            continue
        for i, sp in enumerate(group):
            idx = i + (1 if carry else 0)
            if idx == 0:
                continue                        # the season's own opening date
            d = lo + timedelta(days=round((hi - lo).days * idx / slots))
            sp["join"] = mkdate(d.day, d.month, d.year)
    # The rebuild only sees rows the author touched. A club he never touched is
    # invisible in the career, and the Clear would take its spell with it (Kolo
    # Toure's ASEC Mimosas). A spell at such a club, begun before the first season
    # the file reveals, is a real early spell: keep it.
    if out:
        visited = {r["club"] for r in runs} | {r["club"] for r in loans}
        floor = min(int(sp["join"].get("year")) for sp in out)
        # A youth club has no join date in the DATABASE, only a leave date, so it
        # never reads as a spell above (Xabi Alonso's Antiguoko). The author's own
        # dates for it are still in the file: use those.
        def prepend(ref, join_el):
            v = ET.Element("record", id="value")
            ci.sub(v, "unsigned", id="id", value="1986096245")
            for ch in ref:
                if ch.get("id") != "id":
                    v.append(copy.deepcopy(ch))
            out.insert(0, {"ref": v, "join": join_el, "left": None})

        for club, mine in last_set.items():
            if club in visited or club in lead or last_ref.get(club) is None:
                continue
            j = mine.get("join")
            if j is None or int(j.get("year")) >= floor:
                continue
            if int(j.get("day")) == 1 and int(j.get("month")) == 1 \
                    and not seasons.calendar_year(club):
                # 1 January is FM's "year known, date not". Where the season
                # really does open on 1 January it is also the right date, so it
                # is left alone rather than pushed to July.
                j = seasons.join(club, int(j.get("year")))
            prepend(last_ref[club], copy.deepcopy(j))
        for club, (y, j, ref) in sorted(lead.items(), key=lambda kv: kv[1][0]):
            if club in visited or ref is None or ref.tag != "record":
                continue
            if y + shift >= floor:
                continue
            if (j[0], j[1]) == ("1", "1") and not seasons.calendar_year(club):
                (d0, m0), _, _ = seasons._of(club)[1]
                j = (str(d0), str(m0), j[2])           # a year, not a date
            v = ET.Element("record", id="value")
            ci.sub(v, "unsigned", id="id", value="1986096245")
            for ch in ref:
                if ch.get("id") != "id":
                    v.append(copy.deepcopy(ch))
            out.insert(0, {"ref": v, "join": mkdate(j[0], j[1], y + shift), "left": None})
        out.sort(key=lambda sp: (int(sp["join"].get("year")), int(sp["join"].get("month")),
                                 int(sp["join"].get("day"))))

    # The author clears a spell's leave date to say "he is there now". If that
    # club has no seasons in the rebuilt career it is his next move, not a hole:
    # McCarthy stops playing at Porto and is at Blackburn from the season after.
    if out:
        visited = {r["club"] for r in runs} | {r["club"] for r in loans}
        for club, mine in last_set.items():
            # a join date he cleared, or one FM never had (Paredes' Reggina reads
            # year 0), says the same thing as a date he typed: the club is his
            # and the move has no date yet
            if club in visited or mine.get("left") is not None or "join" not in mine:
                continue
            if True:
                # He dates these in his own season, which need not line up with the
                # career (Abbondanzieri's Getafe reads 2019 against a career that
                # ends in 2024), so the move goes at the start of the season after
                # the last one he plays.
                j = seasons.join(club, max(r["year"] for r in rows) + 1)
                if int(j.get("year")) <= int(out[-1]["join"].get("year")):
                    continue
                ref = last_ref.get(club)
                if ref is None:
                    continue
                v = ET.Element("record", id="value")
                ci.sub(v, "unsigned", id="id", value="1986096245")
                for ch in ref:
                    if ch.get("id") != "id":
                        v.append(copy.deepcopy(ch))
                out.append({"ref": v, "join": j, "left": None})

    # a spell ends exactly when the next one starts - that is what every correct
    # example shows (Rooney 31 August, Henry 18 January, Drogba 1 January) and it
    # guarantees the spells chain. The last spell stays open.
    for a, b in zip(out, out[1:]):
        a["left"] = copy.deepcopy(b["join"])
        a["left"].set("id", "value")
    # A created player's spells grid is the author's and is not rewritten, so the
    # rows must carry HIS leave dates or the two grids disagree by the day between
    # 30 June and 1 July (Di Gennaro).
    if authored_left:
        for sp in out:
            run = sp.get("run")
            if run is None or sp["left"] is None:
                continue
            mine = (last_set.get(run["club"]) or {}).get("left")
            if mine is not None and season(mine) == run["end"]:
                sp["left"] = copy.deepcopy(mine)
                sp["left"].set("id", "value")
    for run in loans:
        mine = last_set.get(run["club"], {})
        join = copy.deepcopy(mine["join"]) if fits(mine.get("join"), run["start"], run["start"]) else None
        if join is None:
            hit = real.get((run["club"], run["start"]))
            if hit:
                j = hit[0]
                cand = mkdate(j[0], j[1], int(j[2]) + shift)
                join = cand if fits(cand, run["start"], run["start"]) else None
        if join is None:
            # `fits` already refuses 1/1 for the author's own SPELL; the career
            # ROW's join had no such guard, which is the whole of Lucho Gonzalez's
            # 1/1/2015 on a row labelled 2014.
            join = copy.deepcopy(run["join"]) \
                if authored_date_ok(run["join"], run["club"], seasons,
                                    first_run=(n == 0)) \
                else seasons.join(run["club"], run["start"])
            join.set("id", "value")
        out.append({"ref": run["ref"], "join": join,
                    "left": seasons.leave(run["club"], run["end"]), "run": run})
    out.sort(key=lambda sp: (int(sp["join"].get("year")), int(sp["join"].get("month")),
                             int(sp["join"].get("day"))))

    # The two grids must agree: a spell's dates are the dates of its own rows.
    # The first row of the run carries the join, the last one the leave date, and
    # the rows in between carry neither (Varela's 2022 Sporting row said it left
    # on 30/6/2023 while the spell ran to 1/7/2025).
    for sp in out:
        run = sp.get("run")
        if run is None:
            continue
        rs = sorted(run["rows"], key=lambda r: (r["year"], r["yror"]))
        for r in rs:
            r["join"] = r["leaving"] = None
        rs[0]["join"] = copy.deepcopy(sp["join"])
        rs[0]["join"].set("id", "value")
        if sp["left"] is not None:
            rs[-1]["leaving"] = copy.deepcopy(sp["left"])
            rs[-1]["leaving"].set("id", "value")
    return out


def emit_spells(uid, spells, build):
    """Clear the club-spells grid and write one row per spell. A Clear carries no
    snapshot so it cannot fail, and SETTING a value resolves an old club id
    perfectly well - it is only MATCHING that compares raw ids."""
    import clean_import as ci

    def wrap(nv):
        rec = ci.wrap(uid, nv, build)
        rec.find('unsigned[@id="property"]').set("value", PNPH_PROP)
        return rec

    ops = []
    nv = ET.Element("record", id="new_value")
    ci.sub(nv, "unsigned", id="id", value=SPELL["row"])
    ci.sub(nv, "integer", id="lsop", value=3)
    ops.append(wrap(nv))
    for sp in spells:
        state = {"team": None, "join": None, "left": None}

        def snapshot():
            o = ET.Element("record", id="olvl")
            ci.sub(o, "unsigned", id="id", value="1869379180")
            if state["team"] is None:
                ci.sub(o, "null", id="team")
            else:
                t = ci.sub(o, "record", id="team")
                for ch in state["team"]:
                    if ch.get("id") != "id":
                        t.append(copy.deepcopy(ch))
            for f in ("join", "left"):
                d = state[f]
                if d is None:
                    ci.sub(o, "date", id=f, day=1, month=1, year=1900, time=0)
                else:
                    ci.sub(o, "date", id=f, day=d.get("day"), month=d.get("month"),
                           year=d.get("year"), time="0")
            ci.sub(o, "integer", id="tjob", value=11)
            return o

        def cell(colid, value_el, apply):
            nv = ET.Element("record", id="new_value")
            ci.sub(nv, "unsigned", id="id", value=colid)
            nv.append(value_el)
            ci.sub(nv, "integer", id="lsop", value=1)
            nv.append(snapshot())
            ops.append(wrap(nv))
            apply()

        nv = ET.Element("record", id="new_value")
        ci.sub(nv, "unsigned", id="id", value=SPELL["row"])
        ci.sub(nv, "integer", id="lsop", value=0)
        ops.append(wrap(nv))
        if sp["ref"] is not None:
            v = ET.Element("record", id="value")
            ci.sub(v, "unsigned", id="id", value="1986096245")
            for ch in sp["ref"]:
                if ch.get("id") != "id":
                    v.append(copy.deepcopy(ch))
            cell(SPELL["team"], v, lambda ref=sp["ref"]: state.__setitem__("team", ref))
        for f, colid in (("join", SPELL["join"]), ("left", SPELL["left"])):
            d = sp[f]
            if d is None or int(d.get("year")) in SENTINELS:
                continue
            cell(colid, copy.deepcopy(d), lambda f=f, d=d: state.__setitem__(f, d))
    return ops


# --------------------------------------------------------------- convert ----

RETIRED_TYPE = "5"     # Ptyp old value of an FM "retired player" record


NAME_PROPS = {"Pfln", "Pfna", "Psna", "Pcna", "Phln"}


def drop_retired_adaptations(changes):
    """Remove every change on person records that are dead weight:
    - adapted from an FM retired-player entry: no ADDR and either Ptyp old
      value 5, or an EMPTY old date of birth on a record that had a name (the
      retired-players table carries no DOB and is already player-typed: Hansen);
    - created shells: an ADDR record whose only changes are names (Rowley).
    FM drops the adapted records in later databases; shells are human error.
    Returns [(uid, kind, n changes)]."""
    created = set()
    for rec in changes:
        if rec_prop(rec) == "ADDR":
            for nvr in rec.findall('record[@id="new_value"]'):
                u = nvr.find('large[@id="db_unique_id"]')
                if u is not None:
                    created.add(u.get("value"))
    props, first_dob_od, ptyp_od, named_old = defaultdict(set), {}, {}, set()
    for rec in changes:
        if rec.find('integer[@id="database_table_type"]').get("value") != PERSON_TABLE:
            continue
        u, pr = rec_uid(rec), rec_prop(rec)
        props[u].add(pr)
        od = rec.find('*[@id="odvl"]')
        if pr == "Pdob" and u not in first_dob_od:
            first_dob_od[u] = dtup(od) if od is not None and od.tag == "date" else None
        if pr == "Ptyp" and od is not None:
            ptyp_od[u] = od.get("value")
        if pr in NAME_PROPS and od is not None and od.tag == "string" and od.get("value"):
            named_old.add(u)
    victims = {}
    for u in props:
        if u in created:
            # a shell carries nothing but names / biography bits (a created referee
            # with O*** official attributes is not a shell)
            if props[u] <= NAME_PROPS | {"Peth", "Phcl", "Pskt", "DELE"}:
                victims[u] = "created shell (names and biography only)"
        elif (fm_names.dbid(u) is None and u in named_old
              and props[u] <= NAME_PROPS | {"Peth", "Phcl", "Pskt", "DELE", "Pdob",
                                            "Pcti", "Pnat", "Pdcn", "Pdfn", "Prid"}):
            # An id that is not DBID * 4294967297 was invented by an editor for a
            # person the author CREATED, in an edition this file no longer carries.
            # All that survives here is the rename, which lands on whoever holds
            # that id now and gives them the legend's name over a stranger's career.
            victims[u] = "rename left over from an earlier edition (no record to rename)"
        elif ptyp_od.get(u) == RETIRED_TYPE:
            victims[u] = "retired-player adaptation (type 5)"
        elif first_dob_od.get(u) == NULL_DATE and u in named_old:
            victims[u] = "retired-player adaptation (no DOB on the record)"
    # A record the author DELETES cannot be edited: every other change he ever
    # typed on it is a guaranteed failure in the editor. Keep the deletion, drop
    # the rest - Xabi Alonso's superseded record carried a whole career.
    doomed = {u for u, ps in props.items() if "DELE" in ps and u not in victims}
    counts = Counter()
    for rec in list(changes):
        if (rec.find('integer[@id="database_table_type"]').get("value") == PERSON_TABLE
                and rec_uid(rec) in doomed and rec_prop(rec) != "DELE"):
            counts[rec_uid(rec)] += 1
            changes.remove(rec)
    for u in doomed:
        if counts[u]:
            victims[u] = "deleted by the author (only the deletion is kept)"
    for rec in list(changes):
        tt = rec.find('integer[@id="database_table_type"]').get("value")
        if tt == PERSON_TABLE and rec_uid(rec) in victims and rec_prop(rec) != "DELE":
            counts[rec_uid(rec)] += 1
            changes.remove(rec)
        elif rec_prop(rec) == "ADDR":                      # drop a shell's creation too
            for nvr in list(rec.findall('record[@id="new_value"]')):
                u = nvr.find('large[@id="db_unique_id"]')
                if u is not None and victims.get(u.get("value"), "").startswith("created shell"):
                    rec.remove(nvr)
                    counts[u.get("value")] += 1
            if not rec.findall('record[@id="new_value"]'):
                changes.remove(rec)
    return [(u, victims[u], counts[u]) for u in victims]


def convert(in_path, out_path, off, shift_staff, flag_year_only, target_season=None,
            continuations="all", rebuild_careers=False, drop_retired=False,
            rebuild_real=False, namer=None):
    tree = ET.parse(in_path)
    root = tree.getroot()
    file_build = int(root.find('integer[@id="version"]').get("value"))
    changes = root.find('.//list[@id="db_changes"]')
    dropped = drop_retired_adaptations(changes) if drop_retired else []
    staff_uids = detect_staff(changes)
    names = person_names(changes)

    person_recs = [(i, rec) for i, rec in enumerate(changes)
                   if rec.find('integer[@id="database_table_type"]').get("value") == PERSON_TABLE]
    rec_index = {id(rec): i for i, rec in person_recs}
    other_tables = Counter(rec.find('integer[@id="database_table_type"]').get("value")
                           for rec in changes) - Counter({PERSON_TABLE: len(person_recs)})

    created, created_dcty = set(), {}
    for rec in changes:
        if rec_prop(rec) == "ADDR":
            for nvr in rec.findall('record[@id="new_value"]'):
                u = nvr.find('large[@id="db_unique_id"]')
                d = nvr.find('unsigned[@id="dcty"]')
                if u is not None:
                    created.add(u.get("value"))
                    if d is not None:
                        created_dcty[u.get("value")] = d.get("value")
    seasons = Seasons(namer)
    uf, ambiguous = link_identities(person_recs, created)
    ambiguous_ids = {x for x, _ in ambiguous}
    members = defaultdict(list)                  # person -> [uids] in first-seen order
    for _, rec in person_recs:
        u = rec_uid(rec)
        if u not in members[uf.find(u)]:
            members[uf.find(u)].append(u)
    if namer is not None:
        # Names settle a link that the snapshots could not: two ids that resolve
        # to DIFFERENT people were never the same person, whatever their DOB and
        # club old-values suggested. Six such links in the England file, three of
        # which were the reason the record could not be rebuilt at all.
        namer.fetch([("person", fm_names.dbid(u)) for us in members.values() for u in us
                     if fm_names.dbid(u) is not None])
        for pid, us in list(members.items()):
            if len(us) < 2:
                continue
            head = namer.person(us[0])
            if not head:
                continue
            for u in [x for x in us[1:] if namer.person(x) and namer.person(x) != head]:
                uf.split(u)
                members[pid].remove(u)
                members[u].append(u)
    groups = defaultdict(list)                   # (person, prop) -> recs in file order
    props_of = defaultdict(set)
    builds = defaultdict(set)
    for _, rec in person_recs:
        p, prop = uf.find(rec_uid(rec)), rec_prop(rec)
        groups[(p, prop)].append(rec)
        props_of[p].add(prop)
        b = rec_build(rec)
        if b is not None:
            builds[p].add(b)

    # The table in CALENDAR_YEAR_NATIONS is real-world league calendars, so it can
    # be wrong for a nation. Where the author dated a spell himself, the date says
    # which calendar he was using, and a nation whose evidence contradicts the
    # table is worth a look.
    #
    # Read the JOIN date ONLY. The leave date belongs to the club he is going TO,
    # not the one he is leaving - a spell ends exactly when the next one starts -
    # so a Swede moving abroad correctly leaves on 30 June, and counting that as
    # European evidence against Sweden is simply wrong. Judging on the pair had
    # Sweden at 5 against 5; on the join alone it is 28 calendar-year against 3,
    # which is what the user says it is. Argentina really is split (60 to 39) -
    # that is its calendar having MOVED, see ERA_CHANGED_NATIONS.
    cal_evidence = defaultdict(Counter)
    for (q, prop), recs in groups.items():
        if prop != "Pnph":
            continue
        for sp in replay_spells(recs):
            j = sp["join"]
            if j is None or not (1930 <= int(j.get("year")) <= 2090):
                continue
            jd = (int(j.get("day")), int(j.get("month")))
            kind = "euro" if jd == (1, 7) else "calyr" if jd == (1, 1) else None
            if kind:
                cal_evidence[seasons.nation(sp["team"][1]) or "(unknown)"][kind] += 1

    # A CREATED player's spells grid is his own and is carried through untouched -
    # only year-shifted - so a mistake in it survives the conversion intact. It can
    # be checked against his career, because the rows at a club and the spell at
    # that club must cover the same seasons. Paulo Sergio is the case that found
    # this: his FM19 relabel pass moved every JOIN date up with the rows and left
    # the LEAVE dates behind, so Novorizontino reads 2015-2017 against a single
    # 2015 row (Rio Branco the same). Reported, never repaired - only the author
    # knows whether the spell or the row is the one he meant.
    #
    # Real records are not checked: their spells are DERIVED from the career, so
    # the two grids cannot disagree by construction.
    import clean_import as ci_chk
    spell_row_odd = []
    for p in members:
        if not any(u in created for u in members[p]):
            continue
        plhs, pnph = groups.get((p, "Plhs")), groups.get((p, "Pnph"))
        if not plhs or not pnph:
            continue
        try:
            rows = ci_chk.replay_best(plhs)[0]
        except Exception:
            continue
        if not rows:
            continue
        by_club = defaultdict(set)
        for r in rows:
            c = ci_chk.club_key(r)
            if c and r.get("year") and r["year"] not in SENTINELS:
                by_club[c].add(r["year"])
        notes = []
        for sp in replay_spells(pnph):
            ys = by_club.get(sp["team"][1])
            if not ys:
                continue
            lo, hi = min(ys), max(ys)
            club = (namer.club(sp["team"][1]) if namer is not None else None) or sp["team"][1]
            j, l = sp["join"], sp["left"]
            if j is not None and int(j.get("year")) not in SENTINELS:
                jy = int(j.get("year"))
                # a spell opens in the season of its first row on either calendar
                # (1/7/Y or 1/1/Y), so one year of slack is plenty
                if abs(jy - lo) >= 2:
                    notes.append(f"{club}: spell joins in {jy}, but his first season "
                                 f"there is {lo}")
            if l is not None and int(l.get("year")) not in SENTINELS:
                ly = int(l.get("year"))
                # and closes in the season of its last row or the one after - a
                # European season labelled Y ends on 30/6/(Y+1)
                if ly - hi >= 2:
                    notes.append(f"{club}: spell runs to {ly}, but his last season "
                                 f"there is {hi}")
                elif hi - ly >= 1:
                    notes.append(f"{club}: spell ends in {ly}, but he still has "
                                 f"{hi} at the club")
        if notes:
            spell_row_odd.append((p, notes))
    # The author's own date of birth and career per editor build, read BEFORE
    # anything is shifted. He moves the two together while he is paying
    # attention; a build that moves one and not the other is the drift. The
    # first Pdob op's odvl is the untouched database value - the real one.
    dob_real, dob_seq = {}, defaultdict(dict)
    for (p, prop), recs in groups.items():
        for rec in recs:
            b = rec_build(rec)
            if prop == "Pdob":
                od = rec.find('*[@id="odvl"]')
                if p not in dob_real and od is not None and od.tag == "date" \
                        and int(od.get("year")) not in SENTINELS:
                    dob_real[p] = int(od.get("year"))
                nv = rec.find('*[@id="new_value"]')
                if nv is not None and nv.tag == "date" and b is not None \
                        and int(nv.get("year")) not in SENTINELS:
                    dob_seq[p].setdefault(b, {})["dob"] = int(nv.get("year"))
            elif prop == "Plhs" and b is not None:
                lsop, col, val, _ = parse_op(rec)
                if lsop == "1" and col == YEAR_COL and val is not None \
                        and val.get("value") is not None:
                    y = int(val.get("value"))
                    if y not in SENTINELS:
                        d = dob_seq[p].setdefault(b, {})
                        d["year"] = max(d.get("year", 0), y)

    # a person is staff if any of its ids is staff-typed and none flipped to player
    flipped = {rec_uid(rec) for _, rec in person_recs if rec_prop(rec) == "Ptyp"
               and rec.find('*[@id="new_value"]') is not None
               and rec.find('*[@id="new_value"]').get("value") == "2"}
    staff = {p for p in members if any(u in staff_uids for u in members[p])
             and not any(u in flipped for u in members[p])}
    shiftable = TOP_DATE_PROPS | GRID_PROPS

    # Continuation ids: linked ids that were not created here. Their edits are
    # live only if the editor can map them back to the record; the editor of
    # the saving edition does, earlier editions' ids are dead (see module docs).
    build_of = defaultdict(set)
    for _, rec in person_recs:
        b = rec_build(rec)
        if b is not None:
            build_of[rec_uid(rec)].add(b)
    def is_live(uid, p):
        if uid in created or uid == members[p][0]:
            return True
        if continuations == "all":
            return True
        if continuations == "current":
            return build_of[uid] == {file_build}
        return False
    live = {u for p in members for u in members[p] if is_live(u, p)}
    dead = {u for p in members for u in members[p]} - live

    # Career rebuild (created players): literal replay of every Plhs op of the
    # person -> cleaning rules -> fresh minimal op sequence replaces ALL old ops.
    # The anchor of a rebuilt person is read from the rebuilt rows, so offset and
    # career agree by construction. See clean_import.py.
    rebuilt = {}
    if rebuild_careers:
        import clean_import as ci
        dob_year = {}
        for (p, prop), recs in groups.items():
            if prop == "Pdob":
                for rec in recs:
                    nv = rec.find('*[@id="new_value"]')
                    if nv is not None and nv.tag == "date":
                        dob_year[p] = int(nv.get("year"))
        # A member id is a REAL DB record (not a continuation of the created one)
        # when it flips person type, or when its Pdob old value is a BIRTHDAY the
        # component never produced. The day and month are the test, not the whole
        # date: the author bumps the year edition after edition and the chain has
        # holes (Platini's continuation cites a year no pass in the file wrote),
        # while a genuinely different person does not share a birthday. Its ops
        # act on another database object and must not be folded into the rebuilt
        # career (Portugal: Mito + an unrelated player).
        def real_ids(p):
            produced, real = set(), set()
            recs = [rec for (pp, prop), rs in groups.items() if pp == p and prop in ("Pdob", "Ptyp") for rec in rs]
            recs.sort(key=lambda rec: rec_index[id(rec)])
            for rec in recs:
                u = rec_uid(rec)
                if rec_prop(rec) == "Ptyp":
                    real.add(u)
                    continue
                nv, od = rec.find('*[@id="new_value"]'), rec.find('*[@id="odvl"]')
                if od is not None and od.tag == "date" and dtup(od) != NULL_DATE \
                        and dtup(od)[:2] not in produced and u not in created:
                    real.add(u)
                if nv is not None and nv.tag == "date" and dtup(nv) != NULL_DATE:
                    produced.add(dtup(nv)[:2])
            return real - set(created)
        rebuilt_ops = {}
        for p in members:
            primary = members[p][0]
            if created_dcty.get(primary) != "2" or p in staff or (p, "Plhs") not in groups:
                continue
            skip_ids = real_ids(p)
            own = [rec for rec in groups[(p, "Plhs")] if rec_uid(rec) not in skip_ids]
            if not own:
                continue
            rebuilt_ops[p] = own
            fee_log = []
            ops, doubled = ci.choose_repeat(
                own, lambda o, d: ci.replay_best(o, doubled=d, trusted_build=file_build)[0])
            del fee_log[:]
            rows, skipped = ci.replay_best(ops, doubled=doubled, trusted_build=file_build, fee_log=fee_log)
            rows, notes = ci.clean(rows, dob_year.get(p), fee_log)
            if skipped:
                notes.insert(0, "passes never applied in the editor, skipped: " +
                             ", ".join(EDITION_BY_BUILD.get(b, str(b)) for b in skipped))
            if skip_ids:
                notes.insert(0, "linked real DB record(s) left out of the career: " + ", ".join(sorted(skip_ids)))
            if doubled:
                notes.insert(0, "doubled op list: repeat dropped")
            if rows:
                rebuilt[p] = (rows, notes)

    # Whose spells will be replaced, decided BEFORE the shift: the test is
    # shift-invariant (a usable date stays usable, a club set stays the same), and
    # the shift loop below has to know, because a grid we are NOT rebuilding must
    # keep being shifted like any other. Skipping the shift for every created
    # player left Milonja Djukic's authored spells sitting in 2003-2011 while his
    # career moved to the target season.
    spell_rebuild = {p for p in rebuilt
                     if spells_need_rebuild(groups.get((p, "Pnph"), []), rebuilt[p][0])}

    # offsets
    anchors, offsets, anomalies, anchorless, skipped_staff = {}, {}, [], [], []
    spread = Counter()
    for p in members:
        if target_season is None:
            offsets[p] = off
            continue
        if p in rebuilt:
            rows = rebuilt[p][0]
            mx = max(r["year"] for r in rows)
            filled = any((r["apps"] or 0) > 0 or (r["gols"] or 0) > 0 for r in rows if r["year"] == mx)
            cy = mx + 1 if filled else mx
        else:
            live_plhs = [r for r in groups.get((p, "Plhs"), []) if rec_uid(r) in live]
            cy = detect_current_year(live_plhs) if p not in staff else None
        anchors[p] = cy
        if p in staff:
            skipped_staff.append(p)
            continue
        if cy is None:
            if props_of[p] & shiftable:
                anchorless.append(p)
            continue
        o = target_season - cy
        if o < 0 or o > MAX_OFFSET:
            anomalies.append((p, cy, o))
            continue
        offsets[p] = o
        spread[o] += 1
    majority = spread.most_common(1)[0][0] if spread else off
    if shift_staff:
        for p in skipped_staff:
            offsets[p] = majority
    shifted = set(offsets)

    # Real DB records: rebuild the playing history with the shift model (no Clear)
    real_rebuilt, real_skipped, real_ops = {}, [], {}
    divisions_filled = 0                         # blank divisions taken from the same club
    moved_to_contract_club = 0                   # loan-only club the contract names
    derived_spells = {}                          # created player -> spells from his career
    player_nation = {}                           # person -> his nation, for an extinct first club
    comp_ties = []                               # club named by two nations' competitions
    era_flagged = []                             # real careers in a moved-calendar league
    joined_synced = 0
    tail_ops = []
    contracts_filled = 0                         # contract dates written for created players
    youth_unticked = 0                           # youth ticks removed from played seasons
    year_only_dated = 0                          # 0/0/YYYY row dates given a real day
    contract_drop = set()                        # their old ops, superseded by the tail
    if rebuild_real and target_season is not None:
        import clean_import as ci
        if namer is not None:
            # Every club the careers and the spells mention, in one sweep. The
            # B-team test reads the cache, and an unfetched club silently is not
            # anyone's B team - which is why the rule fired for Guerrero (cached
            # from an earlier run) and not for Canales.
            want = set()
            for (q, prop), recs in groups.items():
                if prop not in ("Plhs", "Pnph"):
                    continue
                for rec in recs:
                    _, _, val, st = parse_op(rec)
                    for ref in ((st or {}).get("club"),
                                club_of(val) if val is not None and val.tag == "record" else None):
                        if ref:
                            d = fm_names.dbid(ref[1])
                            if d is not None:
                                want.add(("team", d))
            namer.fetch(sorted(want))
            # His own nation, for a first club the index cannot place. A created
            # player states it in the file (`Pnti` -> `Nnat`, which the index
            # resolves as a `nation`); a real record does not need to, so the
            # index's own person entry answers instead.
            nat_ids = {}
            for (q, prop), recs in groups.items():
                if prop != "Pnti":
                    continue
                for rec in recs:
                    nv = rec.find('*[@id="new_value"]')
                    el = nv.find('*[@id="Nnat"]') if nv is not None else None
                    if el is not None and el.get("value"):
                        nat_ids[q] = int(el.get("value"))
            namer.fetch(sorted({("nation", d) for d in nat_ids.values()}))
            for q in members:
                n = namer.get("nation", nat_ids[q]) if q in nat_ids else None
                if not n:
                    n = next((namer.person_nation(u) for u in members[q]
                              if namer.person_nation(u)), None)
                if n:
                    player_nation[q] = n
            # Where a club has no nation, the COMPETITION on the row does. Read
            # from the source snapshots over the whole file: the same extinct club
            # turns up in several careers, and one of them may carry the division
            # where another does not. A club is taken to be in one country, so a
            # club named by competitions in two nations goes to the majority and
            # the tie is reported rather than guessed.
            comp_of = defaultdict(Counter)
            for (q, prop), recs in groups.items():
                if prop != "Plhs":
                    continue
                for rec in recs:
                    for snap in rec.iter("record"):
                        col, divi = (snap.find('*[@id="column_id"]'),
                                     snap.find('*[@id="divi"]'))
                        if col is None or divi is None or divi.tag == "null":
                            continue
                        which = col.find('*[@id="id"]')
                        if which is None or which.get("value") != CLID_COLUMN:
                            continue
                        team, comp = col.find('*[@id="Ttea"]'), divi.find('*[@id="competition"]')
                        if team is None or not team.get("value"):
                            continue
                        if comp is None or not comp.get("value"):
                            continue
                        comp_of[team.get("value")][int(comp.get("value"))] += 1
            unplaced = {c: v for c, v in comp_of.items() if seasons.nation(c) is None}
            namer.fetch(sorted({("competition", k) for v in unplaced.values() for k in v}))
            for club, comps in unplaced.items():
                by_nation = Counter()
                for comp, n in comps.items():
                    e = namer.entry("competition", comp)
                    na = (e or {}).get("na") if isinstance(e, dict) else None
                    if na:
                        by_nation[na] += n
                if not by_nation:
                    continue
                top = by_nation.most_common()
                if len(top) > 1 and top[0][1] == top[1][1]:
                    comp_ties.append((club, [n for n, _ in top]))
                    continue
                seasons.club_from_comp[club] = top[0][0]
                seasons.comp_basis[club] = max(comps, key=comps.get)
        for p in members:
            primary = members[p][0]
            if primary in created or p in staff or (p, "Plhs") not in groups or p in rebuilt:
                continue
            # An INVENTED id the linker could not place is the dangerous shape: it
            # is somebody's continuation, we do not know whose, and a rebuild opens
            # with a Clear that lands on whoever the editor resolves it to. Fredrik
            # Soderstrom lost his whole career that way (one row, 30 apps), and 20
            # ids in the FM17 Portugal file alone carry the same loaded gun. Shift
            # the ops as authored instead - his duplicate-and-relabel then applies
            # on top of the right person, and nothing gets wiped.
            #
            # NOT all invented ids: a LONE one rebuilds correctly and refusing those
            # cost six England careers (13 rows -> 0). Only the ambiguous ones.
            if p in ambiguous_ids and fm_names.dbid(p) is None:
                real_skipped.append((p, "an invented id the identity pass could not place - "
                                        "rebuilding it would Clear the grid of whoever it "
                                        "belongs to, so its ops are shifted as written",
                                     primary, career_sketch(groups[(p, "Plhs")])))
                continue
            if any(u in created for u in members[p]):
                real_skipped.append((p, "the person has both a created record and a real one "
                                        "(the legend was recreated after FM dropped him) - fix by hand",
                                     primary, career_sketch(groups[(p, "Plhs")])))
                continue
            # An id that is not DBID * 4294967297 was INVENTED by an editor, so FM's
            # database holds no record behind it and there is no real career to read
            # from its snapshots. Rebuilding one is not merely useless, it is
            # DESTRUCTIVE: the rebuild opens with a Clear, and where the invented id
            # is a continuation the editor resolves to a created player, that Clear
            # wipes the career his own record just built.
            #
            # Ahmed Ziad is the case that found this (FM17 Portugal, 2026-09-08). The
            # author added his 2015 season on a second invented id, whose four ops
            # DUPLICATE the created record's 2014 row and relabel the copy. Linking
            # needs LINK_THRESHOLD independent citations and that id cites only ONE
            # distinct row - after its duplicate op its later snapshots match its own
            # new row - so the two were never joined. Unlinked, this loop rebuilt it,
            # and its Clear (later in the file) left him with a single season.
            # Shifted as authored instead, the duplicate-and-relabel reproduces the
            # season exactly, which is what the author meant.
            # NOTE (2026-09-08): a blanket refusal here - "never rebuild an invented
            # id" - was tried and REVERTED. It did stop the destructive Clear, but
            # linking (below) already prevents that case by putting the continuation
            # in the created record's group, and the refusal cost six England careers
            # that legitimately rebuild from a lone invented id: the author created
            # those people in an EARLIER edition, so the id can be live in the target
            # database even though this file holds no ADDR for it. Left as it was.
            rows, shift, note, extras = real_career(groups[(p, "Plhs")], target_season)
            if rows is None:
                real_skipped.append((p, note, primary, career_sketch(groups[(p, "Plhs")])))
                continue
            divisions_filled += fill_blank_divisions(rows)
            replaced = list(groups[(p, "Plhs")])
            first_row = min((r for r in rows if r["club"] is not None),
                            key=lambda r: (r["year"], r["yror"]), default=None)
            seasons.for_player(p, player_nation.get(p),
                               ci.club_key(first_row) if first_row is not None else None)
            # the club spells must move with the career or the two grids disagree
            clubs = {ci.club_key(r) for r in rows if r["club"] is not None}
            # A league that changed its calendar cannot be dated by one constant,
            # so these careers keep the default and are reported for a hand check.
            era = sorted({n for n in (seasons.nation(c) for c in clubs)
                          if n in ERA_CHANGED_NATIONS})
            if era:
                odd = career_oddities(rows, shift, namer)
                if odd:
                    era_flagged.append((p, primary, era, odd))
            last_real = max(r["year"] for r in rows) - shift
            n_spells = 0
            # spells FIRST: they write the join and leave dates onto the rows, so
            # the two grids cannot disagree
            spells = spells_from_career(rows, groups.get((p, "Pnph"), []), shift,
                                        offsets.get(p, 0), namer, seasons=seasons)
            contract_club = None
            for rec in groups.get((p, "Pcti"), []):
                nv = rec.find('*[@id="new_value"]')
                ref = club_of(nv) if nv is not None else None
                if ref:
                    contract_club = ref[1]
            # The club the CONTRACT names outranks the spells. Where the author
            # moved him somewhere he only ever appeared ON LOAN there is no
            # definitive join to read, and the fallback was the parent club's -
            # Tulipa's contract said Salgueiros while his Date Joined read
            # 1/7/2019, the day he joined Porto. A move like that is a fresh
            # signing for the coming season (user, 2026-09-09): he joins on the
            # target season's opening day and the spell he is leaving closes the
            # day before. This runs BEFORE `emit_spells` - closing the spell after
            # it is written changes nothing that reaches the file.
            forced_join = None
            if spells and contract_club:
                own_now = next((sp for sp in spells
                                if sp["left"] is None and not sp.get("loan")), None)
                at = club_of(own_now["ref"])[1] if own_now is not None else None
                if at != contract_club:
                    leaving = next((sp for sp in spells if sp["left"] is None), None)
                    if leaving is not None:
                        leaving["left"] = seasons.leave(
                            club_of(leaving["ref"])[1], target_season - 1)
                    forced_join = seasons.join(contract_club, target_season)
                    # ...and he needs a spell AT the new club, or the grid says he
                    # left Porto for nowhere. A loan that turned permanent therefore
                    # ends with TWO rows at the club - the loan season and the
                    # definitive one - which is what the user asked for (2026-09-09).
                    import clean_import as ci_
                    spells.append({"ref": ci_.club_el_from(("integer", contract_club)),
                                   "join": forced_join, "left": None, "run": None})
                    moved_to_contract_club += 1
            new_ops = ci.emit_rows(primary, rows, file_build)
            if spells:
                new_ops = new_ops + emit_spells(primary, spells, file_build)
                if (p, "Pnph") in groups:
                    replaced = replaced + list(groups[(p, "Pnph")])
                n_spells = len(spells)
                mine = {q: groups[(p, q)] for q in JOINED_PROPS + (START_PROP, EXPIRY_PROP)
                        if (p, q) in groups}
                # Rule 1.1 again, and the real path never had it: Date Joined is
                # the DEFINITIVE join, so a loan spell cannot supply it.
                own = [sp for sp in spells if not sp.get("loan")]
                now = next((sp for sp in own if sp["left"] is None),
                           (own or spells)[-1])
                now_club = club_of(now["ref"])
                if forced_join is not None:     # decided above, before the emit
                    now = {"ref": None, "join": forced_join}
                    now_club = ("integer", contract_club)
                add, gone = sync_contract_dates(primary, mine, now["join"], file_build,
                                                target_season, seasons,
                                                now_club[1] if now_club else None)
                # These go at the very END of the file. Setting a player's CLUB
                # resets his Date Joined to the game's own date, and the club
                # change sits later in the file than the rebuild does, so a date
                # written next to the career is overwritten before the import ends
                # (proved: the same change applies on its own, fails in the file).
                tail_ops.extend(add)
                replaced = replaced + gone
                joined_synced += len(add)
            senior = sorted({r["year"] for r in rows if not r["ytht"]}) or \
                sorted({r["year"] for r in rows})
            real_rebuilt[p] = (new_ops, note + ", %d club spell(s)" % n_spells, extras,
                               sorted({r["year"] for r in rows}), senior[0])
            real_ops[p] = replaced

    for (p, prop), recs in groups.items():
        if p not in offsets or prop in NEVER_SHIFT_PROPS:
            continue
        o = offsets[p]
        if prop in ("Plhs", "Pnph") and p in real_rebuilt:
            continue              # rebuilt absolutely, not shifted
        if prop == "Pnph" and p in spell_rebuild:
            continue              # rebuilt from the career, in the target frame already
        if prop == "Plhs" and p in rebuilt:
            own = {id(r) for r in rebuilt_ops[p]}
            recs = [r for r in recs if id(r) not in own]      # real-record ops keep being shifted
            if not recs:
                continue
        if prop in TOP_DATE_PROPS:
            for rec in recs:
                shift_top_date(rec.find('*[@id="new_value"]'), o)
        elif prop in GRID_PROPS:
            convert_grid(recs, o)

    zero_dates_filled, zero_dates_people = 0, 0

    # A contract that expires before the target season even ends leaves the
    # player a free agent the moment the game loads. The author's expiry is
    # shifted like every other date, and where that lands short it is pushed out
    # to the end of a season two to five years away - his own day and month kept,
    # drawn from the record id so a rerun gives the same answer.
    pushed = 0
    if target_season is not None:
        by_record = defaultdict(list)          # per RECORD: that is what the game reads
        for (p, prop), recs in groups.items():
            if prop == EXPIRY_PROP:
                for rec in recs:
                    by_record[rec_uid(rec)].append(rec)
        for uid, recs in by_record.items():
            last = recs[-1].find('*[@id="new_value"]')
            if last is None or last.tag != "date" or int(last.get("year")) > target_season:
                continue
            rng = random.Random(int(uid) + 1)
            last.set("year", str(target_season + rng.randint(2, 5)))
            pushed += 1

    # A date of birth that does not fit the career it sits on. The author moves
    # both, edition after edition, and they drift apart until the record says a
    # seven-year-old played 36 league games (Genar Andrinua). Two repairs, both
    # computed rather than guessed - see docs at the top of this file.
    dob_fixed, dob_guarded, dob_manual, dob_odd = [], [], [], []
    if target_season is not None:
        first_senior = {p: v[4] for p, v in real_rebuilt.items() if len(v) > 4}
        for p, (rows_, notes_) in rebuilt.items():        # created players, shifted later
            senior = [r["year"] for r in rows_ if not r["ytht"]] or [r["year"] for r in rows_]
            if senior:
                first_senior[p] = min(senior) + offsets.get(p, 0)

        def set_dob(p, want, why):
            """Write an absolute year onto the LAST Pdob op of EVERY id the person
            has. Which id the editor resolves is not knowable here - Maldini's
            last word sits on an id that never applies - so every ending is made
            to say the same thing. The age it gives at his first senior season is
            the guard: a computed date that puts a child in a league game is a
            misread of the career, not a fix, and goes on the by-hand list."""
            ends = {}
            for rec in groups.get((p, "Pdob")) or []:
                nv = rec.find('*[@id="new_value"]')
                if nv is not None and nv.tag == "date":
                    ends[rec_uid(rec)] = nv
            if not ends:
                return
            was = int(list(ends.values())[-1].get("year"))
            if all(int(nv.get("year")) == want for nv in ends.values()):
                return
            first = first_senior.get(p)
            if first is not None and not 15 <= first - want <= 48:
                dob_guarded.append((p, was, want, first, first - want))
                return
            for nv in ends.values():
                nv.set("year", str(want))
            dob_fixed.append((p, was, want, want - was, why))

        # Real records: the career was rebuilt from its REAL years, so the date of
        # birth belongs at the real one plus that same shift.
        for p, v in real_rebuilt.items():
            span = real_span(v[1])
            if span is None or span[2] < 3:
                continue                          # a stub, or a career he typed
            if p in dob_real:
                set_dob(p, dob_real[p] + span[3], "real")
            elif not groups.get((p, "Pdob")):
                dob_manual.append((p, span[3]))   # he never touched it: nothing to read

        # Created players: no real anchor exists, but the span the author gave
        # (career last year minus year of birth) is a property of the PLAYER, and
        # he restates it every time he relabels. So the span he states MOST OFTEN
        # is the one he means, and a single pass that disagrees is the slip. Ties
        # go to the build that created the record - there he typed the career and
        # the age together, deliberately (Platini: 28 at FM17, 27 at FM19, and 28
        # is the real one).
        for p, (rows_, notes_) in rebuilt.items():
            seq = sorted((dob_seq.get(p) or {}).items())
            both = [d for _, d in seq if d.get("dob") is not None and d.get("year") is not None]
            typed = [d["dob"] for _, d in seq if d.get("dob") is not None]
            if not both or not typed:
                continue
            spans = [d["year"] - d["dob"] for d in both]
            n = Counter(spans)
            best = max(n.values())
            want = max(r["year"] for r in rows_) - next(s for s in spans if n[s] == best)
            if want != typed[-1]:
                set_dob(p, want + offsets.get(p, 0), "created")

        # whatever is still implausible after both repairs
        guarded = {p for p, _, _, _, _ in dob_guarded}
        for p, first in first_senior.items():
            recs = groups.get((p, "Pdob")) or []
            last = recs[-1].find('*[@id="new_value"]') if recs else None
            if last is None or last.tag != "date" or p in guarded:
                continue
            # measured at his first SENIOR season: a youth row at 15 is normal
            age = first - int(last.get("year"))
            if age < 15 or age > 48:
                dob_odd.append((p, int(last.get("year")), first, age))

    rebuild_stats = {"players": 0, "removed": 0, "written": 0}
    spell_dates = 0
    spells_rebuilt = spells_rebuilt_people = 0   # created players' spell grids rebuilt
    if rebuilt:
        import clean_import as ci
        # A created player's SPELLS are rebuilt too, from the career that was just
        # rebuilt, and the ops they replace have to be listed here or the author's
        # own would survive beside them. USER DECISION 2026-09-09: this is what
        # fixes a spell grid reading 0 (Eduardo Luis - the author wrote year-only
        # dates, which the editor cannot show) and it removes the whole "club
        # spells disagree with the career rows" class by construction, since both
        # grids now come from the same rows. Clear-and-rewrite is also the ONLY
        # safe shape for this grid - editing his snapshots in place loses rows.
        spell_ops = {}
        old_recs = {id(r): p for p in rebuilt for r in rebuilt_ops[p]}
        new_ops = {}
        for p, (rows, notes) in rebuilt.items():
            o = offsets.get(p, 0)
            rows_shifted = []
            for r in rows:
                r2 = dict(r)
                r2["year"] = r["year"] + o
                for f in ("join", "leaving"):
                    if r[f] is not None:
                        d = copy.deepcopy(r[f])
                        shift_date_year(d, o)
                        # a row is ONE season and its dates belong inside it, here
                        # for the same reason as in real_career
                        m = int(d.get("month") or 0)
                        d.set("year", str(r2["year"] if m >= 7 or m < 1 else r2["year"] + 1))
                        if not usable_date(d):
                            # the author wrote a year with no day or month, which the
                            # editor shows as 0: give it the season's own boundary
                            club = ci.club_key(r2) if r2["club"] is not None else None
                            lo, hi = seasons.bounds(club, r2["year"])
                            when = lo if f == "join" else hi
                            d.set("day", str(when.day))
                            d.set("month", str(when.month))
                            d.set("year", str(when.year))
                            year_only_dated += 1
                        r2[f] = d
                rows_shifted.append(r2)
            youth_unticked += untick_played_youth(rows_shifted, dob_year.get(p))
            divisions_filled += fill_blank_divisions(rows_shifted)
            # The author leaves most created careers with no join or leave dates
            # on the rows at all (Di Gennaro). Derive them the same way a real
            # record's are: consecutive seasons at one club are one spell, the
            # first row of the run carries the join and the last one the leave.
            # Only the ROWS are taken - his own spells grid is his and stays.
            pnph = groups.get((p, "Pnph"), [])
            first_row = min((r for r in rows_shifted if r["club"] is not None),
                            key=lambda r: (r["year"], r["yror"]), default=None)
            seasons.for_player(p, player_nation.get(p),
                               ci.club_key(first_row) if first_row is not None else None)
            sp = spells_from_career(rows_shifted, pnph, o, o, namer, authored_left=True,
                                    seasons=seasons)
            spell_dates += dates_from_spells(sp, replay_spells(pnph), seasons)
            derived_spells[p] = sp
            # A created legend the author placed at a club without a contract
            # arrives with an empty one - no expiry, no salary (Cristiano Doni,
            # found by the user 2026-09-08). Only the real-record rebuild used to
            # fill that in, so give the created path the same treatment.
            #
            # Rule 1.1: Date Joined is the DEFINITIVE join, so only NON-LOAN runs
            # count. A loan IN does not make him a member of the club (his real
            # arrival is the permanent move that follows); loans OUT do not
            # interrupt the run, which `spells_from_career` already folds into the
            # parent spell, so a youth arrival stays the date he joined.
            own = [x for x in sp if not x.get("loan")]
            now = next((x for x in own if x["left"] is None), own[-1] if own else None)
            if now is not None:
                mine = {q: groups[(p, q)] for q in JOINED_PROPS + (START_PROP, EXPIRY_PROP)
                        if (p, q) in groups}
                nc = club_of(now["ref"])
                add, gone = sync_contract_dates(members[p][0], mine, now["join"], file_build,
                                                target_season, seasons,
                                                nc[1] if nc else None)
                tail_ops.extend(add)
                contract_drop.update(id(r) for r in gone)
                contracts_filled += len(add)
            new_ops[p] = ci.emit_rows(members[p][0], rows_shifted, file_build)
            if sp and p in spell_rebuild:
                new_ops[p] = new_ops[p] + emit_spells(members[p][0], sp, file_build)
                spell_ops[p] = list(pnph)
                for r in pnph:
                    old_recs[id(r)] = p
                spells_rebuilt += len(sp)
                spells_rebuilt_people += 1
            rebuild_stats["players"] += 1
            rebuild_stats["removed"] += len(rebuilt_ops[p]) + len(spell_ops.get(p, ()))
            rebuild_stats["written"] += len(new_ops[p])
        # A zero in the spells grid is FM's unset date and a SENTINEL, so it came
        # through the shift untouched and can be filled now from the career - which
        # is already in the target frame. Filling before the shift would let the
        # shift run over the value just written.
        for q, spl in derived_spells.items():
            if q in spell_ops:
                continue                      # rebuilt from the career, nothing to fill
            got = fill_zero_spell_dates(groups.get((q, "Pnph"), []), spl)
            if got:
                zero_dates_filled += got
                zero_dates_people += 1
        rebuilt_list, done = [], set()
        for rec in list(changes):
            if id(rec) in contract_drop:        # superseded by a tail contract op
                continue
            p = old_recs.get(id(rec))
            if p is None:
                rebuilt_list.append(rec)
                continue
            if p not in done:
                rebuilt_list.extend(new_ops[p])
                done.add(p)
        for rec in list(changes):
            changes.remove(rec)
        for rec in rebuilt_list:
            changes.append(rec)

    if real_rebuilt:
        old_recs = {id(r): p for p in real_rebuilt for r in real_ops[p]}
        new_list, done = [], set()
        for rec in list(changes):
            p = old_recs.get(id(rec))
            if p is None:
                new_list.append(rec)
                continue
            if p not in done:
                new_list.extend(real_rebuilt[p][0])
                done.add(p)
        for rec in list(changes):
            changes.remove(rec)
        for rec in new_list:
            changes.append(rec)

    # One person, several record ids: an op left on a CONTINUATION id is lost when
    # the target game does not map that id to the person. FM26 does honour the chain
    # from an FM24 file (Adelardo), but it plainly does NOT from this FM17 one:
    # Serafim Pereira Batista's spell and contract ops sit on his second id and the
    # user sees his FIRST id's older values instead - Date Joined 1/7/2017 where the
    # file's last word is 1/7/2019 (user, 2026-09-08). His career survived only
    # because the rebuild re-emits the ROWS onto the primary id.
    #
    # So move EVERY op onto that same primary id, in place and in order, which
    # changes nothing where the chain IS honoured (both ids are the one person) and
    # rescues the ops where it is not. Grids come too: a continuation's snapshots
    # describe the same person's grid, so once the ops sit on the id the game
    # resolves they land on the rows they were written against - that is what
    # brings Serafim's spell relabel (1/7/2018 -> 1/7/2019) back. A rebuilt career
    # has no leftovers to move: the rebuild already replaced every id's rows.
    moved_to_primary = 0
    for p, us in members.items():
        if len(us) < 2:
            continue
        primary = us[0]
        for rec in changes:
            el = rec.find('large[@id="db_unique_id"]')
            if el is None or el.get("value") == primary or el.get("value") not in us[1:]:
                continue
            el.set("value", primary)
            moved_to_primary += 1
    for rec in tail_ops:                        # after every other change
        changes.append(rec)
    # Years the editor cannot read: FM's unset date (0) and the author's own
    # typos (198, 201, 209 - a digit short). Left exactly as written, and listed.
    # Read off the FINISHED file, so an op the rebuild replaced is not counted.
    bad_years = []
    for rec in changes:
        if rec.find('integer[@id="database_table_type"]').get("value") != PERSON_TABLE:
            continue
        nv = rec.find('*[@id="new_value"]')
        if nv is None:
            continue
        for d in ([nv] if nv.tag == "date" else
                  [x for x in nv.iter("date") if x.get("id") == "value"]):
            if 0 <= int(d.get("year")) < 1000:
                bad_years.append((uf.find(rec_uid(rec)), rec_prop(rec), "%s/%s/%s" % dtup(d)))

    # A created record's ADDR row must not carry `nwui`. When that value
    # collides with something in FM26's own database the GAME silently declines
    # to add the person while the EDITOR shows him perfectly - the editor only
    # replays the changelist. Francesco Totti was lost to exactly this: his
    # nwui was 2000067971, Rocca's adjacent 2000067975 loads, and nothing in the
    # XML separates them (2026-09-10). Changing that one integer fixed him.
    #
    # Renumbering into a free block only routes around it. This drops the field,
    # which removes the failure mode: the shape below is what the merged
    # Portugal file already ships for 642 created players, all of which load,
    # and 12 Italy creates restyled into it load too. `id` goes with it and the
    # outer id becomes 4294967297, verbatim per that file.
    addr_restyled = []
    for rec in changes:
        if rec_prop(rec) != "ADDR":
            continue
        for nvr in rec.findall('record[@id="new_value"]'):
            nw = nvr.find('integer[@id="nwui"]')
            if nw is None:                       # already in the safe shape
                continue
            tt = nvr.find('integer[@id="database_table_type"]')
            if tt is None or tt.get("value") != PERSON_TABLE:
                continue                         # a CLUB create (table 3) is not a
                                                 # person; nothing says it is affected
                                                 # and restyling it would be a guess
            u = nvr.find('large[@id="db_unique_id"]')
            addr_restyled.append((u.get("value") if u is not None else "?",
                                  nw.get("value")))
            for child in list(nvr):
                if child.get("id") in ("id", "nwui"):
                    nvr.remove(child)
            outer = rec.find('large[@id="db_unique_id"]')
            if outer is not None:
                outer.set("value", "4294967297")

    # Always. The year shift happens in the tree, so a run that rebuilds nothing
    # still has an output to write - guarding this produced no file at all.
    tree.write(out_path, encoding="unicode", xml_declaration=False)

    shifted_uids = {u for p in shifted for u in members[p]}
    flagged = find_year_only_rows(changes, shifted_uids) if flag_year_only else []

    def label(p):
        for u in members[p]:
            if u in names:
                return names[u]
        return "(existing DB record, no name change)"

    dob_of, club_of_p = {}, {}
    for (p, prop), rs in groups.items():
        if prop == "Pdob":
            for rec in rs:
                nv = rec.find('*[@id="new_value"]')
                if nv is not None and nv.tag == "date":
                    dob_of[p] = "/".join(dtup(nv))
        elif prop == "Pcti":
            for rec in rs:
                nv = rec.find('*[@id="new_value"]')
                ref = club_of(nv) if nv is not None else None
                if ref:
                    club_of_p[p] = ref[1]
    # `Pcti` only exists where the author MOVED him, which is a minority of records,
    # and the "Players to check" table is worth much less with an empty club column.
    # Fall back to the club he ends at: the open spell first (that is what "current
    # club" means in the grid), otherwise the last club in the playing history.
    for p in members:
        if p in club_of_p:
            continue
        spells = replay_spells(groups.get((p, "Pnph"), []))
        open_spell = next((sp for sp in reversed(spells) if sp["left"] is None), None)
        if open_spell is not None:
            club_of_p[p] = open_spell["team"][1]
            continue
        if spells:
            club_of_p[p] = spells[-1]["team"][1]
            continue
        last, best = None, None
        for rec in groups.get((p, "Plhs"), []):
            lsop, col, val, st = parse_op(rec)
            ref = club_of(val) if val is not None and val.tag == "record" else None
            if ref:
                last = ref[1]
            if lsop == "1" and col == YEAR_COL and val is not None and val.get("value"):
                y = int(val.get("value"))
                if y not in SENTINELS and (best is None or y >= best[0]) and last:
                    best = (y, last)
        if best:
            club_of_p[p] = best[1]
        elif last:
            club_of_p[p] = last

    root_of = {u: p for p, us in members.items() for u in us}
    builds_uid = build_of
    return {
        "members": members, "label": label, "root_of": root_of, "builds_uid": builds_uid, "builds": builds, "props_of": props_of,
        "staff": staff, "staff_shifted": shift_staff, "majority": majority,
        "spread": spread, "anchors": anchors, "offsets": offsets,
        "anomalies": anomalies, "anchorless": anchorless, "ambiguous": ambiguous,
        "year_only": flagged, "other_tables": other_tables, "names": names,
        "n_changes": len(changes), "n_person_recs": len(person_recs),
        "target_season": target_season, "uniform": off, "created": created,
        "live": live, "dead": dead, "file_build": file_build, "continuations": continuations,
        "rebuilt": rebuilt, "rebuild_stats": rebuild_stats, "dropped": dropped,
        "spell_dates": spell_dates,
        "zero_dates_filled": zero_dates_filled, "zero_dates_people": zero_dates_people,
        "seasons": seasons, "cal_evidence": cal_evidence, "comp_ties": comp_ties,
        "spell_row_odd": spell_row_odd,
        "real_rebuilt": real_rebuilt, "real_skipped": real_skipped, "namer": namer,
        "era_flagged": era_flagged,
        "joined_synced": joined_synced, "contracts_filled": contracts_filled,
        "divisions_filled": divisions_filled,
        "moved_to_contract_club": moved_to_contract_club,
        "spells_rebuilt": spells_rebuilt, "spells_rebuilt_people": spells_rebuilt_people,
        "moved_to_primary": moved_to_primary, "year_only_dated": year_only_dated,
        "addr_restyled": addr_restyled,
        "youth_unticked": youth_unticked, "expiry_pushed": pushed, "dob_odd": dob_odd,
        "dob_fixed": dob_fixed, "dob_guarded": dob_guarded, "dob_manual": dob_manual,
        "bad_years": bad_years,
        "dob_of": dob_of, "club_of": club_of_p,
        "real_ops": {p: len(v) for p, v in real_ops.items()},
    }


# ---------------------------------------------------------------- report ----

def uf_label(r, uid):
    return r["root_of"][uid]


def editions(bset):
    return ", ".join(sorted({EDITION_BY_BUILD.get(b, f"build {b}") for b in bset},
                            key=lambda s: (s[:2] != "FM", s)))


def write_report(r, path, in_path, out_path):
    base, namer = r["label"], r.get("namer")

    def L(p):
        """A record's name. Real records are never renamed, so the file holds no
        name for them - the FM search index does (see fm_names.py).

        EVERY member id is tried, not just the primary: a person's ids often
        include continuations the index does not know, and asking only the first
        left rows in the "Players to check" table labelled "(existing DB record)"
        with nothing but a number to work from (user, 2026-09-09)."""
        lab = base(p)
        if namer is not None and lab.startswith("("):
            for u in (r["members"].get(p) or [p]):
                got = namer.person(u)
                if got:
                    return got
        return lab

    if namer is not None:
        namer.fetch([("person", fm_names.dbid(us[0])) for us in r["members"].values()
                     if us and fm_names.dbid(us[0]) is not None])
    lines = [f"# Conversion report\n", f"- Source: `{in_path}`", f"- Output: `{out_path}`"]
    if r["target_season"] is not None:
        t = r["target_season"]
        lines.append(f"- Mode: target season {t} ({t % 100:02d}/{(t + 1) % 100:02d}), per-person offset")
    else:
        lines.append(f"- Mode: uniform offset +{r['uniform']}")
    multi = [p for p, us in r["members"].items() if len(us) > 1]
    lines += [f"- File saved by editor build {r['file_build']} ({EDITION_BY_BUILD.get(r['file_build'], 'unknown edition')})",
              f"- Changes in file: {r['n_changes']} ({r['n_person_recs']} on people)",
              f"- Distinct person record ids: {sum(len(u) for u in r['members'].values())}, "
              f"linked into {len(r['members'])} people ({len(multi)} people span several ids)",
              f"- Staff: {len(r['staff'])} ({'shifted at majority +%d' % r['majority'] if r['staff_shifted'] else 'left intact'})",
              ""]
    lines.append("## Offset spread (people shifted)\n")
    lines.append("| Offset | People |\n|---|---|")
    for o, n in sorted(r["spread"].items()):
        lines.append(f"| +{o} | {n} |")
    lines.append("")

    lines.append(f"## People spanning several record ids ({len(multi)})\n")
    lines.append("Same person edited under different ids across editions; linked via old-value snapshots. "
                 "One offset per person. Continuation ids (not created in this file) are LIVE only when the "
                 f"saving editor can map them back to the record: policy `{r['continuations']}` -> "
                 f"{len(r['live']) - len(r['members'])} live continuation ids, {len(r['dead'])} dead. "
                 "Dead ids are still shifted with their person but do not influence the anchor.\n")
    lines.append("| Person | Ids (edition, live/dead) | Anchor | Offset |\n|---|---|---|---|")
    for p in sorted(multi, key=L):
        a = r["anchors"].get(p)
        o = r["offsets"].get(p)
        ids = "; ".join(f"{u} ({editions(r['builds_uid'][u])}, {'live' if u in r['live'] else 'dead'})"
                        for u in r["members"][p])
        lines.append(f"| {L(p)} | {ids} | {a if a is not None else '-'} | "
                     f"{('+%d' % o) if o is not None else 'not shifted'} |")
    lines.append("")

    if r["dropped"]:
        n = sum(x[2] for x in r["dropped"])
        by_type = Counter(t for _, t, _ in r["dropped"])
        lines.append(f"## Dead-weight records removed ({len(r['dropped'])} records, {n} changes)\n")
        lines.append("; ".join(f"{t}: {c}" for t, c in sorted(by_type.items())) + ". Adapted retired-player "
                     "records no longer resolve in later databases; shells carry nothing but names. "
                     "Every change on them was removed. Recreated legends and staff adaptations stay.\n")
        for u, t, c in sorted(r["dropped"], key=lambda x: -x[2]):
            lines.append(f"- {u}: {c} changes ({t})")
        lines.append("")
    if r["real_rebuilt"] or r["real_skipped"]:
        before = sum(r["real_ops"].values())
        after = sum(len(v[0]) for v in r["real_rebuilt"].values())
        lines.append(f"## Real database records: playing history rebuilt ({len(r['real_rebuilt'])} of "
                     f"{len(r['real_rebuilt']) + len(r['real_skipped'])})\n")
        lines.append("These are legends adapted from someone already in the FM database, so the career rows "
                     "are NOT in the file. What the file does carry is every op's old-value snapshot, and the "
                     "author touches every row: he deletes the rows from the prime season on and relabels the "
                     "rest by one constant. So each snapshot reveals that row's real year, club, apps and goals, "
                     "and the career can be rebuilt as the author's own deletes plus ONE year op per kept row "
                     f"(and its join/leave dates moved by the same shift). {before} ops -> {after}. "
                     "No grid Clear: a row the author never touched is invisible here and must survive.\n")
        with_drop = [(p, v) for p, v in r["real_rebuilt"].items() if v[2]]
        if with_drop:
            lines.append(f"{len(with_drop)} of them also carried edits to other cells (apps, goals, youth, "
                         "division, row order) that this rebuild does NOT reproduce - the row keeps its real "
                         "values instead. Worth a look:\n")
            for p, v in sorted(with_drop, key=lambda kv: -kv[1][2])[:40]:
                lines.append(f"- {L(p)}: {v[2]} cell edit(s) not reproduced - {v[1]}")
            lines.append("")
        lines.append("| Player | Rebuild |\n|---|---|")
        for p, v in sorted(r["real_rebuilt"].items(), key=lambda kv: L(kv[0])):
            lines.append(f"| {L(p)} | {v[1]} |")
        lines.append("")
        # A real record is never renamed, so it has no name in the file. These are
        # the ones to check by hand: a hole in the run of seasons is where a row the
        # author never touched may have been, and the Clear has now removed it.
        holed = []
        for p, v in r["real_rebuilt"].items():
            years = v[3] if len(v) > 3 else []
            gaps = [(a, b) for a, b in zip(years, years[1:]) if b - a > 1]
            if gaps:
                holed.append((p, years, gaps))
        lines.append(f"### Rebuilt records with a hole in the career ({len(holed)}) - check these first\n")
        lines.append("A gap in the run of seasons is where a row the author never touched may have "
                     "been, and the Clear has now removed it. Some gaps are real careers (a spell at a "
                     "club the database does not carry), so these want an eye rather than a fix.\n")
        lines.append("| Player | Record id | Date of birth | Seasons | Missing |\n|---|---|---|---|---|")
        if namer is not None:
            namer.fetch([("person", fm_names.dbid(r["members"][p][0])) for p, _, _ in holed])
        for p, years, gaps in sorted(holed, key=lambda x: x[1][0]):
            uid = r["members"][p][0]
            who = (namer.person(uid) if namer is not None else None) or L(p)
            lines.append("| %s | %s | %s | %d-%d | %s |" % (
                who, uid, r["dob_of"].get(p, "-"), years[0], years[-1],
                ", ".join("%d to %d" % (a, b) for a, b in gaps)))
        lines.append("")
        def who_uid(p):
            uid = r["members"][p][0]
            return ((namer.person(uid) if namer is not None else None) or L(p)), uid

        def fetch(ps):
            if namer is not None:
                namer.fetch([("person", fm_names.dbid(r["members"][p][0])) for p in ps])

        WHY = {"real": "real date of birth + career shift",
               "created": "the author's own span, restored"}
        fixed = r.get("dob_fixed") or []
        if fixed:
            lines.append(f"### Date of birth corrected ({len(fixed)})\n")
            lines.append("A real record's career was rebuilt from its REAL years, and the real date of "
                         "birth is in the file too - the first Pdob op's `odvl` is the untouched database "
                         "value - so the date belongs at that value plus the same shift. A created player "
                         "has no such anchor, but the span he was given (career last year minus year of "
                         "birth) is the author's own, and a build that moved his career without moving "
                         "his date of birth broke it.\n")
            lines.append("| Player | Record id | Was | Now | Years | Read from |\n|---|---|---|---|---|---|")
            fetch([x[0] for x in fixed])
            for p, was, now, d, why in sorted(fixed, key=lambda x: (-abs(x[3]), x[1])):
                who, uid = who_uid(p)
                lines.append("| %s | %s | %d | %d | %+d | %s |" % (who, uid, was, now, d, WHY[why]))
            lines.append("")
        guarded = r.get("dob_guarded") or []
        if guarded:
            lines.append(f"### Correction refused by the age guard ({len(guarded)}) - fix by hand\n")
            lines.append("The computed date of birth would put a child, or a pensioner, in his first "
                         "senior season. That means the real career behind the record was misread, so "
                         "nothing is written and the record keeps what it had.\n")
            lines.append("| Player | Record id | Kept | Would have been | First season | Age it gave |"
                         "\n|---|---|---|---|---|---|")
            fetch([x[0] for x in guarded])
            for p, was, want, first, age in sorted(guarded, key=lambda x: x[4]):
                who, uid = who_uid(p)
                lines.append("| %s | %s | %d | %d | %d | %d |" % (who, uid, was, want, first, age))
            lines.append("")
        manual = r.get("dob_manual") or []
        if manual:
            lines.append(f"### Date of birth never edited ({len(manual)}) - add the years by hand\n")
            lines.append("The author moved these careers and never touched the date of birth, so the "
                         "record still carries the real one and the player is that many years too old. "
                         "Nothing in the file holds the real date - no Pdob op means no `odvl` - and the "
                         "FM reference index does not carry dates of birth. The editor shows you the "
                         "current value, so the fix is to add the years below to it.\n")
            lines.append("| Player | Record id | Years to add |\n|---|---|---|")
            fetch([x[0] for x in manual])
            for p, shift in sorted(manual, key=lambda x: -x[1]):
                who, uid = who_uid(p)
                lines.append("| %s | %s | **+%d** |" % (who, uid, shift))
            lines.append("")
        odd = r.get("dob_odd") or []
        if odd:
            lines.append(f"### Date of birth still does not fit the career ({len(odd)}) - fix by hand\n")
            lines.append("Neither repair reaches these: no real career to read the real date against, "
                         "and no build where the author set the date and the career together.\n")
            lines.append("| Player | Record id | Born | First season | Age |\n|---|---|---|---|---|")
            fetch([x[0] for x in odd])
            for p, born, first, age in sorted(odd, key=lambda x: x[3]):
                who, uid = who_uid(p)
                lines.append("| %s | %s | %d | %d | %d |" % (who, uid, born, first, age))
            lines.append("")
        bad = r.get("bad_years") or []
        if bad:
            lines.append(f"### Dates the editor cannot read ({len(bad)})\n")
            lines.append("Year 0 is FM's unset date; the rest are the author's own typos, a digit short. "
                         "They are never shifted - adding years to one only makes a different impossible "
                         "date - and never repaired, because nothing says which digit he dropped.\n")
            lines.append("| Player | Record id | Field | Date |\n|---|---|---|---|")
            fetch([x[0] for x in bad])
            for p, prop, d in sorted(bad, key=lambda x: (x[1], x[2])):
                who, uid = who_uid(p)
                lines.append("| %s | %s | %s | %s |" % (who, uid, prop, d))
            lines.append("")
        by_reason = defaultdict(list)
        for p, why, *_ in r["real_skipped"]:
            by_reason[why.split("(")[0].strip()].append(p)
        lines.append(f"### Left untouched ({len(r['real_skipped'])})\n")
        lines.append("Anything the model cannot account for is left exactly as it was, year-shifted only.\n")
        names = r.get("namer")
        if names is not None:
            want = [("person", fm_names.dbid(uid)) for _, _, uid, _ in r["real_skipped"]]
            want += [("team", fm_names.dbid(c)) for _, _, _, sk in r["real_skipped"]
                     for _, c, _, _ in sk[:14]]
            names.fetch([w for w in want if w[1] is not None])
        detail = {p: (uid, sketch_text(sk, names)) for p, _, uid, sk in r["real_skipped"]}
        for why, ps in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
            named = sorted(L(p) for p in ps if not L(p).startswith("("))
            lines.append(f"- **{why}** - {len(ps)} records" + (": " + ", ".join(named[:25]) if named else ""))
        lines.append("")
        lines.append("A real record carries no name in the changeset, so each one is listed by its "
                     "unique id with the career the file reveals - open the id in the editor to "
                     "recognise the player.\n")
        for why, ps in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
            lines.append(f"**{why}**\n")
            for p in sorted(ps, key=lambda q: detail.get(q, ("", ""))[0]):
                uid, sk = detail.get(p, ("?", ""))
                who = (names.person(uid) if names is not None else None) or ""
                lines.append(f"- `{uid}`{' **' + who + '**' if who else ''} - {sk}")
            lines.append("")
    if r["rebuilt"]:
        st = r["rebuild_stats"]
        flagged = {p: v for p, v in r["rebuilt"].items() if any(n.startswith("FLAG") for n in v[1])}
        lines.append(f"## Careers rebuilt ({st['players']} created players)\n")
        lines.append(f"Playing history recomputed by literal replay of every op of the person, cleaned "
                     f"(blank rows, exact duplicates, youth flag), and rewritten as a fresh sequence: "
                     f"{st['removed']} old ops removed, {st['written']} written. Anchor read from the rebuilt rows. "
                     f"{len(flagged)} players carry flags (same season and club with different stats, or a gap). "
                     f"{r.get('spell_dates', 0)} join/leave dates taken from the author's own club-spells "
                     f"grid, the rest derived from the club runs.\n")
        left_out = [(p, n) for p, (rw, ns) in r["rebuilt"].items() for n in ns
                    if n.startswith("linked real DB record")]
        if left_out:
            lines.append(f"### Ids left out of the rebuilt career ({len(left_out)}) - check these\n")
            lines.append("A linked id whose `Pdob` old value is a birthday this person never had acts on "
                         "ANOTHER database record, so its ops stay out of the replay. If that reading is "
                         "wrong the ops are not just missing - they run after the Clear and relabel the "
                         "rows it just wrote (Platini, before the birthday test).\n")
            for p, n in sorted(left_out, key=lambda x: L(x[0])):
                lines.append(f"- {L(p)} - ids {', '.join(r['members'][p])} - {n}")
            lines.append("")
        for p, (rows, notes) in sorted(flagged.items(), key=lambda x: L(x[0])):
            lines.append(f"### {L(p)} (offset {('+%d' % r['offsets'][p]) if p in r['offsets'] else 'none'})\n")
            lines += [f"- {n}" for n in notes]
            lines.append("")
            lines.append("| Year | Order | Club | Apps | Goals | Youth |\n|---|---|---|---|---|---|")
            for row in rows:
                club = row["club"].find('*[@id="Ttea"]').get("value") if row["club"] is not None else ""
                fmt = lambda v: '' if v is None else v
                lines.append(f"| {row['year'] + r['offsets'].get(p, 0)} | {row['yror'] or ''} | {club} | {fmt(row['apps'])} | {fmt(row['gols'])} | {'yes' if row['ytht'] else ''} |")
            lines.append("")
    lines.append(f"## Anomalies, left unshifted ({len(r['anomalies'])})\n")
    lines.append(f"Anchor is at or beyond the target season, or more than {MAX_OFFSET} years before it "
                 "(a real record whose old history was edited, not a transported legend). Hand check.\n")
    for p, cy, o in r["anomalies"]:
        lines.append(f"- {L(p)} - ids {', '.join(r['members'][p])} - reads current season {cy} (offset would be {o:+d}), editions {editions(r['builds'][p])}")
    lines.append("")

    lines.append(f"## Anchorless people with shiftable dates, left unshifted ({len(r['anchorless'])})\n")
    lines.append("No playing-history year to anchor on, but the record carries dates the converter would otherwise shift.\n")
    lines.append("| Person | Ids | Editions | Shiftable fields |\n|---|---|---|---|")
    for p in sorted(r["anchorless"], key=L):
        sf = ", ".join(sorted(r["props_of"][p] & (TOP_DATE_PROPS | GRID_PROPS)))
        lines.append(f"| {L(p)} | {', '.join(r['members'][p])} | {editions(r['builds'][p])} | {sf} |")
    lines.append("")

    lines.append(f"## Ambiguous identity links, not made ({len(r['ambiguous'])})\n")
    lines.append("The id's snapshots matched the state of more than one other person; it was kept separate.\n")
    for uid, cands in r["ambiguous"]:
        lines.append(f"- id {uid} ({L(uf_label(r, uid))}) matched: " +
                     "; ".join(f"{L(r['root_of'][c])} ({n} points)" for c, n in cands))
    lines.append("")

    lines.append(f"## Staff ({len(r['staff'])})\n")
    for p in sorted(r["staff"], key=L):
        lines.append(f"- {L(p)} - ids {', '.join(r['members'][p])} - editions {editions(r['builds'][p])}")
    lines.append("")

    sro = r.get("spell_row_odd") or []
    if sro:
        n = sum(len(v) for _, v in sro)
        lines.append(f"## Club spells that disagree with their own career rows "
                     f"({n} spells, {len(sro)} created players)\n")
        lines.append(
            "A created player's spells grid is the author's own and is carried through "
            "untouched, so a mistake in it survives the conversion. The rows at a club and "
            "the spell at that club should cover the same seasons; these do not. The usual "
            "cause is a relabel pass that moved the JOIN dates with the rows and left the "
            "LEAVE dates behind. Nothing is repaired - only he knows which of the two he "
            "meant. Real records are not listed: their spells are derived from the career, "
            "so the two grids cannot disagree.\n")
        for p, notes in sorted(sro, key=lambda e: L(e[0])):
            lines.append(f"- **{L(p)}**")
            for nte in notes:
                lines.append(f"  - {nte}")
        lines.append("")
    era = r.get("era_flagged") or []
    if era:
        lines.append(f"## Real records in a league that changed its calendar ({len(era)})\n")
        lines.append(
            "These leagues have not kept one season calendar - Argentina ran two championships "
            "inside a calendar year in the 70s and 80s, then moved to the European calendar, "
            "then back - so which boundary is right depends on the SEASON, not the country. "
            "Their derived dates are therefore left on the European default, the same one the "
            "author uses for them. What is listed here is the shape of the career FM itself "
            "holds: none of it is a converter fault and none of it has been repaired. Created "
            "players are not listed - their careers are the author's own and are coherent.\n")
        for p, primary, nations, odd in sorted(era, key=lambda e: L(e[0])):
            lines.append(f"- **{L(p)}** ({', '.join(nations)})")
            for o in odd:
                lines.append(f"  - {o}")
        lines.append("")
    seasons, ev = r.get("seasons"), r.get("cal_evidence") or {}
    if seasons is not None and seasons.seen:
        lines.append("## Season calendars used for derived dates\n")
        lines.append(
            "A club's season boundaries come from its NATION: a calendar-year league is "
            "dated 1/1 - 31/12, everything else 1/7 - 30/6. This applies only to dates the "
            "converter had to DERIVE - a date the author typed himself always wins - and a "
            "club whose nation is unknown gets the European calendar, which is what every "
            "derived date used before nations were read.\n")
        lines.append("| Nation | Calendar | Derived dates | His own join dates |")
        lines.append("|---|---|---|---|")
        rows = sorted(seasons.seen.items(), key=lambda kv: -kv[1])
        for na, n in rows:
            cal = seasons.seen_cal.get(na) or (
                "calendar year" if na in CALENDAR_YEAR_NATIONS else "European")
            e = ev.get(na or "(unknown)") or {}
            he = (f"{e.get('calyr', 0)} on 1/1, {e.get('euro', 0)} on 1/7"
                  if e else "-")
            lines.append(f"| {na or '(unknown club)'} | {cal} | {n} | {he} |")
        lines.append("")
        # a nation whose own evidence points the other way: either the table is
        # wrong, or he was inconsistent. Worth an eye either way.
        odd = []
        for na, n in rows:
            e = ev.get(na or "(unknown)") or {}
            eu, cy = e.get("euro", 0), e.get("calyr", 0)
            n_ev = eu + cy
            # A clear lean on a sample worth believing. Loose thresholds fire on
            # noise: 3-against-2 for Portugal and 2-against-1 for Romania are not
            # evidence of anything, while South Africa's 5-0 is.
            if not na:
                # Not a table error: these are clubs the search index cannot resolve,
                # so they take the European default. Where his own dates there lean
                # calendar-year, some of them are calendar-year clubs being dated
                # European - worth knowing, and nothing the converter can settle.
                if n_ev >= 5 and cy >= 0.7 * n_ev:
                    odd.append(f"- **Clubs the index does not resolve** get the European "
                               f"default, but his own join dates there read {cy} on 1/1 "
                               f"against {eu} on 1/7 - some are calendar-year clubs "
                               f"({n} derived dates affected)")
                continue
            against = eu if na in CALENDAR_YEAR_NATIONS else cy
            if n_ev < 5 or against < 0.7 * n_ev:
                continue
            odd.append(f"- **{na}** is dated as a {'calendar-year' if na in CALENDAR_YEAR_NATIONS else 'European'} "
                       f"league here, but his own join dates there read {cy} on 1/1 against "
                       f"{eu} on 1/7 ({n} derived dates affected)")
        if odd:
            lines.append("His own dates disagree with the table for these nations. Either the "
                         "entry in `CALENDAR_YEAR_NATIONS` is wrong, or he was inconsistent - "
                         "his own dates are kept wherever they are usable, so this only "
                         "affects the derived ones. Judged on the JOIN date: a spell's leave "
                         "date belongs to the club he is going to, not the one he is leaving.\n")
            lines.extend(odd)
            lines.append("")
    if seasons is not None and (seasons.club_from_comp or seasons.from_player
                               or r.get("comp_ties")):
        lines.append("## Extinct clubs placed without a nation\n")
        lines.append(
            "The index carries no nation for a club FM flags EXTINCT, so the calendar for one "
            "has to be recovered. First from the COMPETITION his playing-history row records "
            "for that season - FM's own statement of where he was playing, and the index does "
            "give a competition its nation. Failing that, and only for the FIRST club of a "
            "career (a home or youth club), from the player's own nation. Anything still "
            "unplaced keeps the European default. Only DERIVED dates are affected - a date he "
            "typed himself always wins.\n")
        if seasons.club_from_comp:
            lines.append("| Club | Nation | Named by | Derived dates |")
            lines.append("|---|---|---|---|")
            for club, na in sorted(seasons.club_from_comp.items(),
                                   key=lambda kv: (-seasons.from_comp.get(kv[0], 0),
                                                   (namer.club(kv[0]) if namer else "") or "")):
                comp = seasons.comp_basis.get(club)
                lines.append(f"| {(namer.club(club) if namer else None) or club} | "
                             f"{na} ({'calendar year' if na in CALENDAR_YEAR_NATIONS else 'European'}) | "
                             f"{(namer.get('competition', comp) if namer and comp else None) or '?'} | "
                             f"{seasons.from_comp.get(club, 0)} |")
            lines.append("")
        if seasons.from_player:
            lines.append("These had no competition on any row, and are the first club of a "
                         "career, so they took the player's own nation.\n")
            lines.append("| Club | Player | Nation taken |")
            lines.append("|---|---|---|")
            for club, (who, na) in sorted(seasons.from_player.items(),
                                          key=lambda kv: (namer.club(kv[0]) if namer else "") or ""):
                lines.append(f"| {(namer.club(club) if namer else None) or club} | "
                             f"{L(who) if who is not None else '?'} | "
                             f"{na} ({'calendar year' if na in CALENDAR_YEAR_NATIONS else 'European'}) |")
            lines.append("")
        for club, nations in (r.get("comp_ties") or []):
            lines.append(f"- **{(namer.club(club) if namer else None) or club}** is named by "
                         f"competitions in {' and '.join(nations)} in equal measure, so it was "
                         "left on the European default rather than guessed")
        if r.get("comp_ties"):
            lines.append("")
    if seasons is not None and seasons.inherited:
        lines.append("## B teams dated from their parent club\n")
        lines.append(
            "The search index carries no nation for a club FM flags EXTINCT, and no division "
            "either, though FM itself knows it. A B team is the one case that needs no map: it "
            "plays in its parent's country by definition, and FM's own short names say which "
            "club it belongs to (`Brondby IF II` against `Brondby IF`). So it takes the "
            "parent's season calendar. Only DERIVED dates are affected - a date he typed "
            "himself still wins.\n")
        lines.append("| B team | Parent | Calendar taken |")
        lines.append("|---|---|---|")
        for club, parent in sorted(seasons.inherited.items(),
                                   key=lambda kv: (namer.club(kv[0]) if namer else "") or ""):
            na = seasons.nation(club)
            lines.append(f"| {(namer.club(club) if namer else None) or club} | "
                         f"{(namer.club(parent) if namer and parent else None) or '?'} | "
                         f"{na} ({'calendar year' if na in CALENDAR_YEAR_NATIONS else 'European'}) |")
        lines.append("")
    if r["other_tables"]:
        lines.append("## Non-person tables in the file (never shifted)\n")
        for t, n in sorted(r["other_tables"].items(), key=lambda x: int(x[0])):
            lines.append(f"- table {t}: {n} change(s)")
        lines.append("")

    yo = r["year_only"]
    lines.append(f"## Year-only match keys ({len(yo)} grids)\n")
    lines.append("Rows whose match key holds a season-only date (0/0/YYYY). These do not round-trip in the editor "
                 "and revert on import; touch up by hand if they matter.\n")
    for uid, prop in yo:
        lines.append(f"- {uid} {prop} {r['names'].get(uid, '')}")
    lines.append("")

    # ------------------------------------------------------------- to check ---
    # Everything the report flags anywhere, gathered per player, so a file can be
    # worked through from one list instead of a dozen sections. Each row names the
    # club he is AT in this file, which is what you search for in the editor.
    todo = defaultdict(list)

    def flag(p, why):
        if why not in todo[p]:
            todo[p].append(why)

    for p, cy, _o in r["anomalies"]:
        flag(p, f"anchor reads {cy}, left unshifted")
    for p in r["anchorless"]:
        flag(p, "no anchor, dates left unshifted")
    for p, _primary, nations, _odd in (r.get("era_flagged") or []):
        flag(p, f"league changed calendar ({', '.join(nations)})")
    for p, notes in (r.get("spell_row_odd") or []):
        flag(p, f"{len(notes)} club spell(s) disagree with the career rows")
    for p, _note, _uid, _sk in r["real_skipped"]:
        flag(p, "playing history NOT rebuilt")
    for p, v in r["real_rebuilt"].items():
        ys = v[3] if len(v) > 3 else []
        if any(b_ - a_ > 1 for a_, b_ in zip(ys, ys[1:])):
            flag(p, "hole in the rebuilt career")
    for e in r.get("dob_guarded", []):
        flag(e[0], "date of birth: correction refused by the age guard")
    for e in r.get("dob_manual", []):
        flag(e[0], "date of birth: never edited, add the years by hand")
    for e in r.get("dob_odd", []):
        flag(e[0], "date of birth: still does not fit the career")
    for e in r.get("bad_years", []):
        flag(e[0], f"date the editor cannot read ({e[1]} {e[2]})")
    for e in r.get("ambiguous", []):
        # these are record ids, not person roots (the link was never made)
        flag(r["root_of"].get(e[0], e[0]), "identity link not made (ambiguous)")
    # A grid whose match key holds a season-only date does not round-trip: the ops
    # revert on import. It had a section of its own but never reached this table,
    # so working from the table alone missed it (user, 2026-09-09).
    for uid, prop in (r.get("year_only") or []):
        flag(r["root_of"].get(uid, uid),
             f"{prop} rows keyed on a season-only date, they revert on import")

    ar = r.get("addr_restyled") or []
    if ar:
        lines.append(f"## Created records: ADDR nwui dropped ({len(ar)})\n")
        lines.append("An `nwui` that collides with FM26's own data makes the GAME "
                     "silently refuse the record while the editor shows it (Totti, "
                     "2026-09-10). The field is removed rather than renumbered, so "
                     "there is nothing left to collide.\n")
        lines.append("| Player | Record id | nwui dropped |")
        lines.append("|---|---|---|")
        for uid, nw in ar:
            lines.append(f"| {L(r['root_of'].get(uid, uid))} | {uid} | {nw} |")
        lines.append("")

    if todo:
        lines.append(f"## Players to check ({len(todo)})\n")
        lines.append(
            "Every player this report flags anywhere, in one table. The club is the one he is "
            "AT in this file - what you search for in the editor - and not necessarily the club "
            "the problem is about. Nothing here has been repaired and none of it is necessarily "
            "wrong; these are the records worth an eye. The detail for each is in the section "
            "named by the reason.\n")
        lines.append("| Player | Record id | Club | What to check |")
        lines.append("|---|---|---|---|")
        for p in sorted(todo, key=lambda x: (L(x) or "").lower()):
            uid = (r["members"].get(p) or [p])[0]
            cid = r["club_of"].get(p)
            club = (namer.club(cid) if namer is not None and cid else None) or (cid or "-")
            lines.append(f"| {L(p)} | {uid} | {club} | {'; '.join(todo[p])} |")
        lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))


def main(argv=None):
    ap = argparse.ArgumentParser(description="FMPT Legends edition/season converter")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--offset", type=int, help="uniform years to add (e.g. 2)")
    ap.add_argument("--target-season", type=int, metavar="YEAR",
                    help="make every player current for this season (label year, "
                         "e.g. 2025 for 25/26); per-person offset is auto-computed")
    ap.add_argument("--shift-staff", action="store_true",
                    help="shift managers/staff (by the majority player offset)")
    ap.add_argument("--flag-year-only", action="store_true",
                    help="report rows whose match key holds a year-only date "
                         "(these won't round-trip in the editor)")
    ap.add_argument("--continuations", choices=["current", "none", "all"], default="all",
                    help="which continuation ids (same person, later id, no ADDR) count as live "
                         "for the anchor: 'current' = only those authored by the editor build that "
                         "saved the file (default), 'none' = none, 'all' = every linked id")
    ap.add_argument("--rebuild-careers", action="store_true",
                    help="created players: recompute the playing history by literal replay, clean it "
                         "and replace all old ops with a fresh sequence (see clean_import.py)")
    ap.add_argument("--rebuild-real-history", action="store_true",
                    help="real DB records: rebuild the playing history with the shift model - "
                         "the author's deletes plus one year op per kept row, no grid Clear")
    ap.add_argument("--drop-retired-adaptations", action="store_true",
                    help="remove every change on existing records adapted from an FM retired-player "
                         "entry (Ptyp 5 -> x, no ADDR); FM drops those records, the legends were recreated")
    ap.add_argument("--names", action="store_true",
                    help="name the records and clubs in the report, from the FM search index behind "
                         "fmref.com (a unique id is DBID * 4294967297, people and clubs alike); "
                         "cached in fm_names_cache.json, and ids stay ids when offline")
    ap.add_argument("--report", metavar="FILE.md",
                    help="write a markdown conversion report (explanations)")
    args = ap.parse_args(argv)
    if (args.offset is None) == (args.target_season is None):
        ap.error("give exactly one of --offset or --target-season")

    namer = fm_names.Names() if args.names else None
    r = convert(args.input, args.output, args.offset, args.shift_staff,
                args.flag_year_only, args.target_season, args.continuations, args.rebuild_careers,
                args.drop_retired_adaptations, args.rebuild_real_history,
                fm_names.Names() if args.names else None)
    if r["dropped"]:
        print(f"dead-weight records removed: {len(r['dropped'])} ({sum(x[2] for x in r['dropped'])} changes): "
              + ", ".join(f"{t} x{n}" for t, n in Counter(t for _, t, _ in r["dropped"]).items()))
    if r["real_rebuilt"]:
        before = sum(r["real_ops"].values())
        after = sum(len(v[0]) for v in r["real_rebuilt"].values())
        print(f"real records rebuilt: {len(r['real_rebuilt'])} of "
              f"{len(r['real_rebuilt']) + len(r['real_skipped'])} "
              f"({before} playing-history ops -> {after}); {len(r['real_skipped'])} left untouched")
    if r["rebuilt"]:
        st = r["rebuild_stats"]
        print(f"careers rebuilt: {st['players']} players, {st['removed']} Plhs ops removed, {st['written']} written")
    if r.get("divisions_filled"):
        print(f"blank divisions taken from his own other row at the same club: "
              f"{r['divisions_filled']}")
    if r.get("moved_to_contract_club"):
        print(f"contract club he only ever appeared at ON LOAN, dated as a new "
              f"signing for the target season: {r['moved_to_contract_club']}")
    if r.get("spells_rebuilt"):
        print(f"created players' club spells rebuilt from the career: "
              f"{r['spells_rebuilt']} spells on {r['spells_rebuilt_people']} people")
    if r.get("contracts_filled"):
        print(f"contract dates written for created players: {r['contracts_filled']}")
    if r.get("youth_unticked"):
        print(f"youth ticks removed from seasons that have figures: {r['youth_unticked']}")
    if r.get("year_only_dated"):
        print(f"year-only row dates given the season's own boundary: {r['year_only_dated']}")
    if r.get("moved_to_primary"):
        print(f"ops moved off a continuation id onto the person's primary: {r['moved_to_primary']}")
    if r.get("addr_restyled"):
        print(f"created records whose ADDR dropped its nwui (collision-proof shape): "
              f"{len(r['addr_restyled'])}")
    if r.get("zero_dates_filled"):
        print(f"spell dates filled from the career (were 0): {r['zero_dates_filled']} "
              f"on {r['zero_dates_people']} created players")
    L = r["label"]
    multi = [p for p, us in r["members"].items() if len(us) > 1]
    print(f"file saved by build {r['file_build']} ({EDITION_BY_BUILD.get(r['file_build'], '?')}); "
          f"continuation ids: {len(r['live']) - len(r['members'])} live, {len(r['dead'])} dead (policy {r['continuations']})")
    print(f"people: {len(r['members'])} ({len(multi)} span several record ids)  "
          f"staff: {len(r['staff'])} ({'shifted at majority +%d' % r['majority'] if r['staff_shifted'] else 'left intact'})")
    if args.target_season is not None:
        print("per-person offset spread: " +
              (", ".join(f"+{o}: {n}" for o, n in sorted(r["spread"].items())) or "(none)"))
        print(f"anchorless with shiftable dates (left intact): {len(r['anchorless'])}")
        if r["anomalies"]:
            print(f"ANOMALIES ({len(r['anomalies'])}) - future or >{MAX_OFFSET}y anchor, left intact, VERIFY:")
            for p, cy, o in r["anomalies"]:
                print(f"  {L(p)}: reads current season {cy} (offset would be {o:+d})")
    else:
        print(f"offset +{args.offset}")
    if r["ambiguous"]:
        print(f"ambiguous identity links not made: {len(r['ambiguous'])}")
    if args.flag_year_only:
        print(f"year-only rows: {len(r['year_only'])}")
    if args.report:
        write_report(r, args.report, args.input, args.output)
        print(f"report -> {args.report}")


if __name__ == "__main__":
    main()
