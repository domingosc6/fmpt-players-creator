"""Lift a club's people out of one changeset and into another.

Goal: take the work the author already did on a club - the legends he recreated
there and the existing people he moved there - and add it to a different file
without disturbing what that file already says.

WHO IS SELECTED. Everyone the OLD file places at one of the named clubs. The
club comes from `Pcti` (the contract club) first, which is the right primary
signal because that op only exists where he MOVED someone: in the Portugal file
492 of 808 people carry one, and every single created player does. Where it is
absent the club is taken from the grid instead - the open spell, then the last
spell, then the last club in the playing history - the same fallback the
conversion report uses for its "Players to check" table. A B team counts as its
parent club, so listing a club catches its reserves.

WHAT MOVES. Every change the old file makes to a selected person, in the order
it makes them, including the `ADDR` record that creates a player from scratch.
Order is preserved because it carries meaning: a club change resets Date Joined,
so the contract dates have to land after it.

WHAT CAN SILENTLY FAIL, AND WHAT ACTUALLY DECIDES IT. A grid op (`Plhs`,
`Pnph`, `PPsT`, `Pacl`) is a cell edit matched to a row by its `olvl` snapshot,
and the editor resolves it to the FIRST row that fits. A snapshot that fits
nothing is DROPPED with no error and no sign in the file.

But lifting an op does not change whether it resolves: the editor applies it
against the loaded GAME database, not against the file it sits in, so an op that
worked in the old file behaves the same in the new one. What decides resolution
is how old the DATABASE IMAGE in the snapshot is, and that is the build that
AUTHORED the op (each record's own `version`), not the build that saved either
file. Pre-FM21 snapshots name clubs and divisions with integer DBIDs that FM26
does not resolve, which is why the career rebuild has to Clear and rewrite.

The file HEADER cannot tell you any of this: `convert_edition.py` deliberately
never rewrites headers, so a converted FM26-ready file still reports the FM24
build (3569) that saved it. An earlier version of this script refused a lift
when the two headers disagreed - a guard that could never fire here and gave
false assurance. Instead the report now shows the authoring builds of everything
carried, so an op written by an old editor is visible: the England file alone
spans eight builds (2281 to 3569).

CONFLICTS are never resolved silently: if the new file already changes the same
property for the same person, nothing is written and the collision is reported.
"""
import argparse
import copy
import random
import re
import sys
import unicodedata
import importlib.util
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

import fm_names

HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
PERSON_TABLE = "1"
GRID_PROPS = {"Plhs", "Pnph", "PPsT", "Pacl"}
# FM's own placeholder, one record used freely in many countries. The author
# parks surplus existing players on it (114 people in the Portugal file), so
# selecting it pulls in a crowd rather than a squad.
PLACEHOLDER_CLUBS = {"Unknown Club"}


def converter():
    """convert_edition, imported for its parsing helpers. Read-only: nothing
    here calls anything that writes the names cache."""
    path = __import__("os").path.join(HERE, "convert_edition.py")
    spec = importlib.util.spec_from_file_location("ce", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def op_key(ce, rec):
    """(person id, property) - what decides whether the target already says this.

    An `ADDR` record needs care: it is table type 55 and its own
    `db_unique_id` is a constant (4294967297) shared by EVERY creation in every
    file, while the person being created is the `db_unique_id` NESTED in
    `new_value`. Keying on the outer one makes all 186 creations in a file look
    like the same change, which silently dropped every created player on the
    first run of this script.
    """
    prop = ce.rec_prop(rec)
    if prop == "ADDR":
        for nvr in rec.findall('record[@id="new_value"]'):
            u = nvr.find('large[@id="db_unique_id"]')
            if u is not None:
                return u.get("value"), prop
    u = rec.find('large[@id="db_unique_id"]')
    return (u.get("value") if u is not None else None), prop


def file_build(root):
    """The editor build that saved the file - what decides 'same edition'."""
    el = root.find('integer[@id="version"]')
    return el.get("value") if el is not None else None


def clubs_wanted(tokens, nm):
    """Resolve each token - a club id or a name - to a DBID. Names come from
    FM's own short names in the search index, which is also how an EXTINCT club
    is still findable: the index drops its nation, never its name."""
    want, unknown = {}, []
    by_name = nm._by_name()                      # name -> scaled ids, over the cache
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        if tok.isdigit():
            d = fm_names.dbid(tok)
            if d is not None:
                want[str(d)] = nm.club(tok) or tok
                continue
        hits = by_name.get(tok.lower()) or set()
        if len(hits) == 1:
            cid = next(iter(hits))
            want[str(fm_names.dbid(cid))] = nm.club(cid) or tok
        elif hits:
            # Ambiguity here is real and worth refusing: "Liverpool" is both the
            # English club (676) and Liverpool Futbol Club of Uruguay (1920), and
            # they are not even on the same season calendar. Name the nation so the
            # choice is obvious, and give the id to use.
            who = sorted("%s, %s (id %s)"
                         % (nm.club(c) or "?", nm.nation(c) or "no nation in the index",
                            fm_names.dbid(c)) for c in hits)
            unknown.append((tok, "matches %d clubs, so it was not used - pass the id of "
                                 "the one you mean: %s" % (len(hits), "; ".join(who))))
        else:
            unknown.append((tok, "no club in the names cache answers to this"))
    return want, unknown


def club_of_people(ce, groups, members, nm, contract_only=False):
    """person -> (club dbid, how we know). `Pcti` first; the grid after it.

    `contract_only` drops the grid fallback, which is the right selector for a
    club list wide enough to cover a whole country: the fallback answers "played
    there once", and over 102 Portuguese clubs that is nearly every person the
    file touches. `Pcti` answers "the author put him there", and every created
    player carries one (user rule, 2026-09-08)."""
    out = {}
    for p in members:
        ref = None
        for rec in groups.get((p, "Pcti"), []):
            nv = rec.find('*[@id="new_value"]')
            r = ce.club_of(nv) if nv is not None else None
            if r:
                ref = r[1]
        if ref is not None:
            out[p] = (str(fm_names.dbid(ref)), "moved there (Pcti)")
            continue
        if contract_only:
            continue
        spells = ce.replay_spells(groups.get((p, "Pnph"), []))
        openspell = next((s for s in reversed(spells) if s["left"] is None), None)
        if openspell is not None:
            out[p] = (str(fm_names.dbid(openspell["team"][1])), "open club spell")
            continue
        if spells:
            out[p] = (str(fm_names.dbid(spells[-1]["team"][1])), "last club spell")
            continue
        last, best = None, None
        for rec in groups.get((p, "Plhs"), []):
            lsop, col, val, st = ce.parse_op(rec)
            r = ce.club_of(val) if val is not None and val.tag == "record" else None
            if r:
                last = r[1]
        if last is not None:
            out[p] = (str(fm_names.dbid(last)), "last club in the playing history")
    return out


def matches(club, want, nm):
    """Is this club one we want, directly or as somebody's B team?"""
    if club in want:
        return club, None
    scaled = int(club) * fm_names.UID_SCALE
    parent = nm.parent_of(scaled)
    if parent is not None:
        pd = str(fm_names.dbid(parent))
        if pd in want:
            return pd, nm.club(parent)
    return None, None


def norm_name(s):
    """A name folded down to what two editions of the same man will agree on:
    accents stripped, punctuation gone, case and spacing normalised. `Vitória`
    and `Vitoria` are the same string here, which matters because the FM17 file
    and the index do not always agree on the diacritics."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s.lower()).split())


def dob_of(ce, groups, p):
    """(day, month, year) this file leaves the person on, or None.

    The LAST `Pdob` op wins, the way the editor applies them. Only the file can
    answer: FM's search index carries no dates of birth, so a real record nobody
    re-dated has none available at all - which is why a name+DOB test can only
    ever decide the people both files re-dated.
    """
    d = None
    for rec in groups.get((p, "Pdob"), []):
        el = rec.find('*[@id="new_value"]')
        if el is not None and el.tag == "date":
            y = el.get("year")
            if y and int(y) in ce.SENTINELS:
                continue
            d = ce.dtup(el)
    return d


def people_index(ce, nm, root, contract_only=False):
    """Everything one changeset says about its people, keyed by identity group.

    Both sides of a merge need exactly this - who is in the file, what each of
    them is called, when he was born and where he plays - so it is built once and
    used twice rather than open-coded for the source alone.
    """
    changes = list(root.find('list[@id="db_changes"]'))
    person_recs = [(i, rec) for i, rec in enumerate(changes)
                   if rec.find('integer[@id="database_table_type"]') is not None
                   and rec.find('integer[@id="database_table_type"]').get("value") == PERSON_TABLE]
    created = set()
    for rec in changes:
        if ce.rec_prop(rec) == "ADDR":
            for nvr in rec.findall('record[@id="new_value"]'):
                u = nvr.find('large[@id="db_unique_id"]')
                if u is not None:
                    created.add(u.get("value"))
    uf, ambiguous = ce.link_identities(person_recs, created)
    members = defaultdict(list)
    for _, rec in person_recs:
        u = ce.rec_uid(rec)
        if u not in members[uf.find(u)]:
            members[uf.find(u)].append(u)
    groups, ops_of = defaultdict(list), defaultdict(list)
    for _, rec in person_recs:
        p = uf.find(ce.rec_uid(rec))
        groups[(p, ce.rec_prop(rec))].append(rec)
        ops_of[p].append(rec)
    # an ADDR record is filed under no property group of its own, but it has to
    # travel with its person - and be written before anything that edits him
    for rec in changes:
        if ce.rec_prop(rec) != "ADDR":
            continue
        for nvr in rec.findall('record[@id="new_value"]'):
            u = nvr.find('large[@id="db_unique_id"]')
            if u is not None and u.get("value") in uf.parent:
                p = uf.find(u.get("value"))
                if rec not in ops_of[p]:
                    ops_of[p].insert(0, rec)
    file_names = ce.person_names(changes)

    def name(p):
        for u in members[p]:
            if file_names.get(u):
                return file_names[u]
        for u in members[p]:
            n = nm.person(u)
            if n:
                return n
        return None
    where = club_of_people(ce, groups, members, nm, contract_only=contract_only)
    return {"changes": changes, "created": created, "uf": uf, "members": members,
            "groups": groups, "ops_of": ops_of, "where": where, "name": name,
            "ambiguous": ambiguous,
            "names": {p: name(p) for p in members},
            "dob": {p: dob_of(ce, groups, p) for p in members}}


def identity_conflicts(oldix, newix, picked):
    """Which selected people the TARGET already holds, and on what evidence.

    Three tests, in the order the user set them (2026-09-08):

      1. the same DATABASE id - a real FM person edited in both files. Decisive
         on its own; 173 of them between the FM17 Portugal file and the FM24 one.
      2. name + date of birth + current club - certainly the same man.
      3. name + date of birth at DIFFERENT clubs - still the same man, moved
         between the two editions. Kept from the target, but worth reporting.

    Name alone is deliberately NOT a match: Portuguese naming repeats far too
    heavily here to drop a legend over it, so those are carried as new records and
    reported so nothing is silently duplicated.

    Only DAY and MONTH of the birth date are compared. The converter shifts every
    year onto the target season, so two editions of the same man disagree on the
    year by construction - the day and month are what survive the transport.
    """
    by_id, by_nd = {}, defaultdict(list)
    for q in newix["members"]:
        for u in newix["members"][q]:
            by_id[u] = q
        n, d = newix["names"].get(q), newix["dob"].get(q)
        if n and d:
            by_nd[(norm_name(n), d[0], d[1])].append(q)
    by_name = defaultdict(list)
    for q in newix["members"]:
        if newix["names"].get(q):
            by_name[norm_name(newix["names"][q])].append(q)

    verdicts = {}
    for p in picked:
        hit = next((by_id[u] for u in oldix["members"][p] if u in by_id), None)
        if hit is not None:
            verdicts[p] = ("same database id", hit, True)
            continue
        n, d = oldix["names"].get(p), oldix["dob"].get(p)
        if n and d:
            for q in by_nd.get((norm_name(n), d[0], d[1]), []):
                same = (oldix["where"].get(p, (None,))[0]
                        == newix["where"].get(q, (None,))[0]
                        != None)
                verdicts[p] = ("name + birthday + club" if same
                               else "name + birthday, different club", q, True)
                break
            if p in verdicts:
                continue
        if n:
            q = next(iter(by_name.get(norm_name(n), [])), None)
            if q is not None:
                verdicts[p] = ("name only - carried as a NEW record", q, False)
    return verdicts


def spell_add_ops(ce, uid, club_dbid, joined, build, fresh_rid):
    """Ops that append one open club spell at `club_dbid`, joined on `joined`
    (a (day, month, year) tuple). Add, then set the club, then set the join date -
    in that order, each citing the state the row is actually in.

    `Ttea` carries the club's DBID, not the scaled uid: the grid stores what
    `club_of`/`team_dbid` normalise to, and writing the scaled value leaves the
    editor showing a bare number instead of the club.
    """
    import clean_import as ci
    SPELL = {"row": "1853322860", "team": "1952801133", "join": "1785686382",
             "left": "1818584692", "tjob": "1953132386"}
    ops, state = [], {"team": None, "join": None}

    def wrap(nv):
        rec = ci.wrap(uid, nv, build)
        rec.find('unsigned[@id="property"]').set("value", str(ce.prop_id("Pnph")))
        r = rec.find('integer[@id="db_random_id"]')
        if r is not None:
            r.set("value", fresh_rid())
        return rec

    def snapshot(nv):
        o = ci.sub(nv, "record", id="olvl")
        ci.sub(o, "unsigned", id="id", value="1869379180")
        if state["team"] is None:
            ci.sub(o, "null", id="team")
        else:
            t = ci.sub(o, "record", id="team")
            ci.sub(t, "integer", id="Ttea", value=state["team"])
        for f in ("join", "left"):
            d = state.get(f)
            if d is None:
                ci.sub(o, "date", id=f, day=1, month=1, year=1900, time=0)
            else:
                ci.sub(o, "date", id=f, day=d[0], month=d[1], year=d[2], time=0)
        ci.sub(o, "integer", id="tjob", value=11)

    nv = ET.Element("record", id="new_value")
    ci.sub(nv, "unsigned", id="id", value=SPELL["row"])
    ci.sub(nv, "integer", id="lsop", value=0)
    ops.append(wrap(nv))

    nv = ET.Element("record", id="new_value")
    ci.sub(nv, "unsigned", id="id", value=SPELL["team"])
    ci.sub(nv, "integer", id="lsop", value=1)
    v = ci.sub(nv, "record", id="value")
    ci.sub(v, "integer", id="Ttea", value=str(club_dbid))
    snapshot(nv)
    ops.append(wrap(nv))
    state["team"] = str(club_dbid)

    nv = ET.Element("record", id="new_value")
    ci.sub(nv, "unsigned", id="id", value=SPELL["join"])
    ci.sub(nv, "integer", id="lsop", value=1)
    ci.sub(nv, "date", id="value", day=joined[0], month=joined[1], year=joined[2], time=0)
    snapshot(nv)
    ops.append(wrap(nv))
    return ops



def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old", help="the changeset to take changes FROM")
    ap.add_argument("new", nargs="?",
                    help="the changeset to add them TO (never modified in place). Omit it "
                         "with --standalone to get a file holding nothing but the lifted "
                         "people")
    ap.add_argument("out", nargs="?", help="where to write the result (default: alongside NEW)")
    ap.add_argument("--clubs", default="", help="comma-separated club ids or names")
    ap.add_argument("--clubs-file", help="a file of club ids or names, one per line")
    ap.add_argument("--out", dest="out_opt",
                    help="where to write the result. Prefer this over the positional "
                         "form with --standalone, where a second bare path would be "
                         "read as the target changeset")
    ap.add_argument("--report", help="write a markdown report of what was lifted")
    ap.add_argument("--normalise-addr", action="store_true",
                    help="rewrite each carried ADDR creation into the shape the FM24-era "
                         "editor writes, which is the shape already proven to load in "
                         "FM26: wrapper `db_unique_id` 4294967297 instead of -1, and drop "
                         "the older editor's `nwui` counter and `nwvl` marker. Use when "
                         "created players arrive without their careers")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--standalone", action="store_true",
                    help="write a file containing ONLY the lifted people, instead of adding "
                         "them to an existing changeset. Small enough to judge in the "
                         "editor: if a career arrives empty you see it at once")
    ap.add_argument("--header-from",
                    help="with --standalone, the file whose header the new one copies "
                         "(default: the OLD file). Prefer a file that has already loaded "
                         "in the target game - the editor rewrites header stamps on load, "
                         "but there is no reason to start from an older one than you must")
    ap.add_argument("--contract-only", action="store_true",
                    help="select on the contract club (`Pcti`) alone, without the grid "
                         "fallback. Right for a club list wide enough to cover a whole "
                         "country, where 'played there once' selects almost everybody")
    ap.add_argument("--merge-identities", action="store_true",
                    help="before carrying anyone, ask whether the TARGET already holds "
                         "him - by database id, then by name + birthday (+ club). Where "
                         "it does, the target's version stands and nothing of his is "
                         "carried. A name-only match is carried and reported, never "
                         "dropped")
    ap.add_argument("--target-season", type=int, default=2025,
                    help="the season both files are on. Used to date the club spell "
                         "added for a person whose own grid is not carried")
    ap.add_argument("--no-move-spell", action="store_true",
                    help="do not add a club spell for a moved person whose history "
                         "grid was left behind")
    ap.add_argument("--keep-authored-grids", action="store_true",
                    help="carry an EXISTING record's history grids even where the "
                         "converter did not rebuild them. Off by default: those ops "
                         "describe FM's database as it was in the SOURCE edition, so in "
                         "the target they insert rows on top of a career the game "
                         "already holds - Danilo Pereira gained a year-1900 row, "
                         "duplicate 2016 Parma rows and twin 2022 Estoril youth rows; "
                         "Jose Martins gained 1993 four times over. A grid the converter "
                         "REBUILT starts with a Clear and is carried either way")
    ap.add_argument("--scalars-only", action="store_true",
                    help="carry attributes and other single-value changes, leave the "
                         "history grids alone")
    a = ap.parse_args(argv)

    ce = converter()
    nm = fm_names.Names(offline=True)            # the converter owns cache writes
    tokens = list(a.clubs.split(","))
    if a.clubs_file:
        tokens += [ln.strip() for ln in open(a.clubs_file) if ln.strip()
                   and not ln.startswith("#")]
    want, unknown = clubs_wanted(tokens, nm)
    if not want:
        # print WHY before giving up - an ambiguous name is the usual reason, and
        # the explanation is what the user needs
        for tok, why in unknown:
            print("  ! %r: %s" % (tok, why), file=sys.stderr)
        sys.exit("no club resolved from %r - nothing to select"
                 % (a.clubs or a.clubs_file))

    if not a.new and not a.standalone:
        sys.exit("give a target changeset, or --standalone to write a file of only the "
                 "lifted people")
    old_root = ET.parse(a.old).getroot()
    if a.standalone:
        # A header-only copy of a real file: the change list is emptied and only the
        # lifted people go in. The header stamps (`version`, `EdBr`, `EdDt`) are left
        # exactly as the donor wrote them - the target editor rewrites them on load,
        # and inventing values here is how a file stops loading.
        new_tree = ET.parse(a.header_from or a.old)
        new_root = new_tree.getroot()
        lst = new_root.find('list[@id="db_changes"]')
        for el in list(lst):
            lst.remove(el)
    else:
        new_tree = ET.parse(a.new)
        new_root = new_tree.getroot()
    ob, nb = file_build(old_root), file_build(new_root)
    cross = ob != nb
    scalars_only = a.scalars_only

    oldix = people_index(ce, nm, old_root, contract_only=a.contract_only)
    changes = oldix["changes"]
    created, members, groups, ops_of = (oldix["created"], oldix["members"],
                                        oldix["groups"], oldix["ops_of"])
    where = oldix["where"]
    ambiguous = oldix["ambiguous"]
    picked = {}
    for p, (club, how) in where.items():
        hit, via_b = matches(club, want, nm)
        if hit:
            picked[p] = {"club": hit, "how": how, "b_team": via_b}

    # Whom the target already holds. Decided BEFORE anything is emitted and on the
    # whole person, not per property: a history grid is hundreds of interdependent
    # cell ops, so a record half-written by one edition and half by the other is
    # not a career, it is wreckage (user rule, 2026-09-08).
    verdicts, dropped = {}, {}
    if a.merge_identities and not a.standalone:
        newix = people_index(ce, nm, new_root)
        verdicts = identity_conflicts(oldix, newix, picked)
        dropped = {p: v for p, v in verdicts.items() if v[2]}

    # what the target already says, so nothing is overwritten by accident
    new_changes = new_root.find('list[@id="db_changes"]')
    # `db_random_id` is the editor's own per-op key, so a fresh one is drawn for
    # every carried op - but drawing blind collides: 14 of 193,000 on the first
    # Portugal merge. Remember what is in use, the target's ids included.
    used_rids = {e.get("value") for e in new_root.iter("integer")
                 if e.get("id") == "db_random_id"}

    def fresh_rid():
        while True:
            v = str(random.randint(1, 2 ** 31 - 1))
            if v not in used_rids:
                used_rids.add(v)
                return v
    taken = set()
    for rec in list(new_changes):
        taken.add(op_key(ce, rec))

    # The conflict decision is made ONCE per (person, property), against what the
    # target said BEFORE we started. It cannot be updated as we emit: a history
    # grid is hundreds of cell ops sharing one key, so a running set makes a
    # person's second op collide with his own first and carries a broken half of
    # his career.
    carried, skipped_grids = Counter(), Counter()
    authored_skipped = Counter()
    move_spells = 0
    conflict_pairs = set()
    # Which editor build AUTHORED each op we carry. This is the real predictor of
    # a snapshot that will not resolve - an old build's snapshot describes an old
    # database image - and it is per record, not per file.
    builds_carried = Counter()
    grid_builds = Counter()
    normalised = Counter()
    # The build stamp alone is NOT the risk signal, and reading it that way
    # overstated the danger 17-fold on the first FM17 extract (8,673 "at risk"
    # against a true 498). `emit_rows` stamps a REBUILT op with the source file's
    # build, so a safe Clear-and-rewrite op looks as old as an untouched one.
    # What actually decides it is whose rows the snapshot describes:
    #   - rebuilt in the source (the group carries an `lsop=3` Clear): the cell ops
    #     land on blank rows, so there is nothing to fail to match;
    #   - a CREATED player's own grid: his rows are inserted by this same file, so
    #     his snapshots describe rows that exist wherever it is applied;
    #   - an EXISTING record carried as the author wrote it: the snapshot is an
    #     image of FM's database in the SOURCE edition. These are the ones that can
    #     match nothing and be dropped in silence.
    risk = Counter()
    at_risk_people = set()
    REBUILT_PROPS = {"Plhs", "Pnph"}     # the only grids the converter rebuilds

    def group_has_clear(person, prop):
        for rec in groups.get((person, prop), []):
            nv = rec.find('record[@id="new_value"]')
            e = nv.find('integer[@id="lsop"]') if nv is not None else None
            if e is not None and e.get("value") == "3":
                return True
        return False
    # An EXISTING record's grid is only safe to carry when the converter REBUILT
    # it: a rebuild opens with a Clear, so its cell ops land on rows it made
    # itself. Carried as the author wrote them, the same ops describe the SOURCE
    # edition's rows and simply add to whatever the target game holds.
    authored_grid = set()
    if not a.keep_authored_grids:
        for p in picked:
            if any(u in created for u in members[p]):
                continue
            for prop in GRID_PROPS:
                if groups.get((p, prop)) and not group_has_clear(p, prop):
                    authored_grid.add((p, prop))
        # `Plhs` and `Pnph` are two views of ONE career, so they travel together:
        # carrying a rebuilt spells grid beside a dropped playing history leaves the
        # two describing different careers. 11 existing records in the Portugal merge
        # are split this way, Danilo Pereira and Eduardo Luis among them. `Pacl` is
        # judged alone - achievements say nothing about which seasons he played.
        for p in picked:
            pair = [g for g in ("Plhs", "Pnph") if groups.get((p, g))]
            if len(pair) == 2 and any((p, g) in authored_grid for g in pair):
                authored_grid.update((p, g) for g in pair)
    for p in sorted(picked, key=lambda q: -len(ops_of[q])):
        if p in dropped:
            continue
        for rec in ops_of[p]:
            uid, prop = op_key(ce, rec)
            if scalars_only and prop in GRID_PROPS:
                skipped_grids[prop] += 1
                continue
            if (p, prop) in authored_grid:
                authored_skipped[prop] += 1
                continue
            if (uid, prop) in taken:
                conflict_pairs.add((p, uid, prop))
                continue
            out = copy.deepcopy(rec)
            if a.normalise_addr and prop == "ADDR":
                # The FM17-era editor writes a creation differently from the FM24 one:
                # wrapper id -1 against 4294967297, plus an `nwui` counter (a sequential
                # "new unique id") and sometimes an `nwvl` marker child. The FM24 shape
                # is the one known to load in FM26, and it carries none of that, so this
                # reduces a creation to the three fields that shape uses.
                w = out.find('large[@id="db_unique_id"]')
                if w is not None and w.get("value") == "-1":
                    w.set("value", "4294967297")
                    normalised["wrapper id -1 -> 4294967297"] += 1
                for nvr in out.findall('record[@id="new_value"]'):
                    for kid in list(nvr):
                        if kid.get("id") in ("nwui", "id"):
                            nvr.remove(kid)
                            normalised["dropped %s" % kid.get("id")] += 1
            r = out.find('integer[@id="db_random_id"]')
            if r is None:
                r = ET.SubElement(out, "integer")
                r.set("id", "db_random_id")
            r.set("value", fresh_rid())
            if not a.dry_run:
                new_changes.append(out)
            carried[prop] += 1
            b = rec.find('integer[@id="version"]')
            b = b.get("value") if b is not None else "?"
            builds_carried[b] += 1
            if prop in GRID_PROPS:
                grid_builds[b] += 1
                if prop in REBUILT_PROPS and group_has_clear(p, prop):
                    risk[(prop, "rebuilt in the source file (Clear + rewrite)")] += 1
                elif any(u in created for u in members[p]):
                    risk[(prop, "created player's own rows")] += 1
                else:
                    risk[(prop, "EXISTING record, the author's original snapshots")] += 1
                    at_risk_people.add(p)

    # A person whose grid we left behind still has his CONTRACT carried, so the
    # target game will place him at the new club with no spell saying he ever
    # arrived. Add one: an Add op appends a blank row and the cell ops that follow
    # cite that blank state, which the editor resolves to the LAST matching row -
    # the one we just made - so this does not depend on what the target already
    # holds. That is also its limit: the club he is LEAVING cannot be closed,
    # because finding his open spell would mean matching a row only the target
    # game knows. See the report.
    if not a.no_move_spell and not a.dry_run:
        for p in sorted(picked, key=lambda q: members[q][0]):
            if p in dropped or not any((p, g) in authored_grid for g in ("Plhs", "Pnph")):
                continue
            club = picked[p]["club"]
            # His own Date Joined is the author's statement about when he arrived,
            # so the spell agrees with the contract rather than contradicting it.
            # Only where he never set one does the target season's opening day stand.
            joined = (1, 7, a.target_season)
            for rec in groups.get((p, "Pcjd"), []):
                nv = rec.find('*[@id="new_value"]')
                if nv is not None and nv.tag == "date" \
                        and (nv.get("year") or "").isdigit() and int(nv.get("year")) > 1000:
                    joined = (nv.get("day"), nv.get("month"), nv.get("year"))
            for rec in spell_add_ops(ce, members[p][0], club, joined,
                                     file_build(new_root) or "3569", fresh_rid):
                new_changes.append(rec)
                carried["Pnph"] += 1
            move_spells += 1

    out_path = a.out_opt or a.out or ((a.new or a.old).replace(
        ".xml", " - lifted squad.xml" if a.standalone else " - with lifted squad.xml"))
    if not a.dry_run:
        new_tree.write(out_path, encoding="utf-8", xml_declaration=False)

    # A created id was invented by an editor, so the search index cannot name it -
    # his name is in the FILE, and often only in the name PARTS rather than a full
    # name (`Pfna` + `Psna`, no `Pfln`). Reading the file first and the index
    # second names both populations: without this every created legend in the
    # report read "(no name in either file)", which is useless for checking a squad.
    file_names = ce.person_names(changes)

    def name(p):
        for u in members[p]:
            if file_names.get(u):
                return file_names[u]
        for u in members[p]:
            n = nm.person(u)
            if n:
                return n
        return "(unnamed) %s" % members[p][0]

    if a.standalone:
        print("standalone target: header copied from %s, no other changes"
              % (a.header_from or a.old))
    print("clubs wanted: %s" % ", ".join(sorted(want.values())))
    for tok, why in unknown:
        print("  ! %r: %s" % (tok, why))
    print("people selected: %d (%d created, %d existing)"
          % (len(picked), sum(1 for p in picked if any(u in created for u in members[p])),
             sum(1 for p in picked if not any(u in created for u in members[p]))))
    print("changes carried: %d over %d properties" % (sum(carried.values()), len(carried)))
    if verdicts:
        why = Counter(v[0] for v in verdicts.values())
        print("already in the target, kept as the target has them: %d" % len(dropped))
        for k, n in why.most_common():
            print("    %-42s %d%s" % (k, n, "" if k.startswith("name only")
                                      else "  (not carried)"))
    n_risk = sum(n for k, n in risk.items() if k[1].startswith("EXISTING"))
    if n_risk:
        print("grid ops that can silently fail: %d, on %d existing record(s) whose grids "
              "were carried as the author wrote them (the rest are rebuilt or belong to "
              "created players, and resolve)" % (n_risk, len(at_risk_people)))
    if move_spells:
        print("club spell added at the new club for %d moved people whose own grid "
              "was left behind (the club they LEFT cannot be closed from here - see "
              "the report)" % move_spells)
    if authored_skipped:
        print("existing records' UNREBUILT grids left behind (they would stack on the "
              "career the target game already holds): %s  - on %d people"
              % (", ".join("%s x%d" % kv for kv in authored_skipped.most_common()),
                 len({p for p, _ in authored_grid})))
    if skipped_grids:
        print("grids NOT carried (%s): %s"
              % ("different editions" if cross else "--scalars-only",
                 ", ".join("%s x%d" % kv for kv in skipped_grids.most_common())))
    if normalised:
        print("ADDR creations normalised to the FM24 shape: %s"
              % ", ".join("%s x%d" % (k, v) for k, v in normalised.most_common()))
    if conflict_pairs:
        print("left alone: %d person+property pairs the new file already changes"
              % len(conflict_pairs))
    if not a.dry_run:
        print("written -> %s" % out_path)

    if a.report:
        lines = ["# Lifted squad\n",
                 "- From: `%s` (build %s)" % (a.old, ob),
                 "- Into: %s (build %s)" % ("a standalone file, header from `%s`"
                                            % (a.header_from or a.old) if a.standalone
                                            else "`%s`" % a.new, nb),
                 "- Result: `%s`" % ("nothing written (dry run)" if a.dry_run else out_path),
                 "- Clubs: %s\n" % ", ".join(sorted(want.values()))]
        if cross:
            lines.append("The two files were last saved by different editor builds (%s and "
                         "%s). That is worth an eye but decides nothing on its own - what "
                         "matters is the build that authored each op, in the table below.\n"
                         % (ob, nb))
        for tok, why in unknown:
            lines.append("- **%s** was not used: %s" % (tok, why))
        if unknown:
            lines.append("")
        if any(nm.club(int(c) * fm_names.UID_SCALE) in PLACEHOLDER_CLUBS for c in want):
            lines.append("**One of these clubs is FM's `Unknown Club` placeholder.** It is a "
                         "single record used freely across the database - he parks surplus "
                         "existing players on it - so this selection is a crowd, not a "
                         "squad.\n")
        if verdicts:
            lines.append("## Already in the FM24 file (%d)\n" % len(verdicts))
            lines.append(
                "Matched on the database id first, then on name + birthday, then on "
                "name + birthday + current club. Only DAY and MONTH of the birthday are "
                "compared: the converter shifts every year onto the target season, so two "
                "editions of the same man disagree on the year by construction.\n\n"
                "A match means the FM24 record STANDS and nothing of his is carried over "
                "it. A name-only match is not treated as a match - Portuguese naming "
                "repeats too heavily in this file - so he is carried as a new record and "
                "listed here so you can check he really is somebody else.\n")
            lines.append("| Person (FM17) | Evidence | Carried? | FM24 record | FM17 record |")
            lines.append("|---|---|---|---|---|")
            for p in sorted(verdicts, key=lambda q: (verdicts[q][0], (name(q) or "").lower())):
                ev, q, drop = verdicts[p]
                lines.append("| %s | %s | %s | `%s` | `%s` |"
                             % (name(p), ev, "no - FM24 kept" if drop else "**yes, as new**",
                                newix["members"][q][0], members[p][0]))
            lines.append("")
        lines.append("## People carried (%d)\n" % (len(picked) - len(dropped)))
        # Name the CLUB, not only how it was determined. Without it the table
        # cannot answer "who did I get from Estrela da Amadora", which is the
        # question a squad list exists to answer.
        lines.append("| Person | Record id | Created | Club | Known from | Changes |")
        lines.append("|---|---|---|---|---|---|")
        for p in sorted(picked, key=lambda q: (name(q) or "").lower()):
            if p in dropped:
                continue
            info = picked[p]
            n_ops = sum(1 for rec in ops_of[p]
                        if not (scalars_only and ce.rec_prop(rec) in GRID_PROPS))
            lines.append("| %s | %s | %s | %s%s | %s | %d |"
                         % (name(p), members[p][0],
                            "yes" if any(u in created for u in members[p]) else "-",
                            nm.club(int(info["club"]) * fm_names.UID_SCALE) or info["club"],
                            " (B team of %s)" % info["b_team"] if info["b_team"] else "",
                            info["how"], n_ops))
        lines.append("")
        if risk:
            lines.append("## Which history grids can silently fail (%d ops at risk)\n"
                         % n_risk)
            lines.append(
                "A grid op is matched to a row by its `olvl` snapshot and dropped without "
                "a word if nothing fits. What decides that is whose rows the snapshot "
                "describes - NOT the build stamp, which a rebuilt op inherits from the "
                "source file and which therefore makes safe ops look old.\n")
            lines.append("| Grid | Kind | Ops |")
            lines.append("|---|---|---|")
            for (prop, kind), n in sorted(risk.items(), key=lambda kv: -kv[1]):
                lines.append("| `%s` | %s | %d |" % (prop, kind, n))
            lines.append("")
            if at_risk_people:
                lines.append("The %d record(s) to check first in the editor - existing FM "
                             "people whose careers or spells were carried as the author "
                             "wrote them, against an older database:\n"
                             % len(at_risk_people))
                for q in sorted(at_risk_people, key=lambda q: name(q).lower()):
                    lines.append("- %s (`%s`)" % (name(q), members[q][0]))
                lines.append("")
        lines.append("## Authoring builds of what was carried\n")
        lines.append(
            "The build that authored each op. The file HEADER cannot tell you this - it "
            "names only the build that last SAVED the file, and `convert_edition.py` "
            "never rewrites headers, so a converted FM26-ready file still reports the "
            "build that saved the original.\n")
        lines.append("| Authoring build | Ops carried | of which history grids |")
        lines.append("|---|---|---|")
        for b, n in builds_carried.most_common():
            lines.append("| %s | %d | %d |" % (b, n, grid_builds.get(b, 0)))
        lines.append("")
        lines.append("Context only. A rebuilt op keeps the SOURCE file's build stamp, so an "
                     "old number here does not mean an op is at risk - the table above is "
                     "the one that says which are.\n")
        lines.append("## Changes carried, by property\n")
        for prop, n in carried.most_common():
            lines.append("- `%s`: %d" % (prop, n))
        lines.append("")
        conflicts = sorted(conflict_pairs, key=lambda c: (name(c[0]).lower(), c[2]))
        if conflicts:
            lines.append("## Left alone - the new file already changes these (%d)\n"
                         % len(conflicts))
            lines.append("Nothing was overwritten. Decide each one by hand.\n")
            lines.append("| Person | Record id | Property |")
            lines.append("|---|---|---|")
            for p, uid, prop in conflicts:
                lines.append("| %s | %s | `%s` |" % (name(p), uid, prop))
            lines.append("")
        if ambiguous:
            lines.append("## Identity links not made (%d)\n" % len(ambiguous))
            lines.append("These ids could not be tied to a person with confidence, so each "
                         "was treated on its own.\n")
        open(a.report, "w").write("\n".join(lines) + "\n")
        print("report -> %s" % a.report)


if __name__ == "__main__":
    main()
