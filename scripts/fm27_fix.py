"""Fix an FM27 converted file against the FM27 database (Part 1 of the FM27 work).

The converter (`--offset 1 --from-season 2025`) only moves dates. Between FM26 and
FM27 the DATABASE moved too: people were dropped, players were turned into staff,
and current players changed clubs. A change on a person the database no longer has,
or no longer has as a player, silently does nothing. This script finds every legend
in a converted file that FM27 broke, fixes what can be fixed in the file itself, and
records a status per legend.

    py scripts/fm27_fix.py "C:/DBC/FMPT/FM 27 converted files/FMPT Legends - Portugal - target2026.xml"

The file is fixed IN PLACE (user, 2026-11-13); the unfixed one is kept as
`old/<name> - unfixed.xml` next to it. Statuses go to legends/fm27_status.csv.

What a legend is: a created record, a record with a playing history in the file, or
one the file turns into a player. Everything else a file does to real people - the
retirements and released contracts that clear surplus players out of squads - is a
squad matter (Part 2) and is not touched here.

Per REAL legend (a created record is its own person and FM27 cannot break it):

  missing     FM27 does not have the person. When FM26 did not have him either, the
              legend was already broken in FM26, unless an FM26 pass copied him onto
              a created record (rebuild_lost_records: 151 of 242 in Portugal) or the
              Legends Creator recreated him (same date of birth); those are left
              alone. The rest are RECREATED: a fresh created id from
              creator/ids.json, an ADDR row, every change of his moved onto it, and
              what a created person lacks and the file does not say - name, positions,
              attributes - taken from the FM name index and from FM26's database.
  staff       FM27 has him as a non-player and the file never makes him a player
              (Adrien Silva). The type change is put FIRST among his changes - the
              editor refuses attributes and positions on a non-player, and a type
              change resets them - then his retirements are cleared, then the
              positions and attributes the file does not state are taken from FM26
              when FM26 still had him as a player.
  history     EVERY real legend's playing history and club spells are rebuilt, not
              patched: the converter's real-record rebuild (CLAUDE.md 5e) is run on
              the FM26 file straight to 2026, so the author's relabels are read against
              the rows he saw and every kept row is placed by his DOMINANT shift (Abel
              Ruiz: a slip that put two seasons on one year comes out right), then the
              grid is Cleared and written fresh - which also removes the seasons FM27's
              database added (Abdu Conte at Casa Pia). Spells are derived from that
              career. Past transfers are cleared (user, 2026-11-13).
  birth       Where the file sets no date of birth: FM26's date moved by the years the
              legend's career sits after the real one, matched season by season on
              club, appearances and goals (Marco Baixinho +15 -> 2004), never a flat +1.
  club        Where the file sets none: the Drive squad sheet's (work/<country>_sheet_clubs.json,
              a namesake settled by the club in his own career - Ricardo Velho is
              Farense), else his open club spell; contract dates written after it.
  PA          A player born in 2005 or later with a fixed PA gets the negative code
              whose range middle is closest to PA - 5 (Heldon 130 -> -7).
  manual      Flagged, not fixed: a profile whose attributes were last written before
              FM24, and a created career the converter never rebuilt (Acacio).
  positions   Written 20s first: the editor rates a new player 20 at centre back the
              moment another position is set while none is at 20 (Adrien Silva).

Byte layout of a people_db record, FM26 and FM27 alike (learned 2026-11-13 from the
first-touch odvl of every FM26-authored change in six files, people FM26 had as
players only - 100% agreement on every property below):
  4        person type (1 non-player, 2 player, 3 both)
  36..49   position ratings, 1-20, in the order of POSITIONS
  50..103  the 54 attributes, the FM18 layout moved by 6 (ATTRIBUTES)
CA, PA and the reputations are 16-bit fields near the start whose order is not
settled, so they are never read from the database: a recreated or restored player
keeps the file's own, and his status says so when the file has none.
"""
import argparse
import copy
import csv
import datetime
import json
import os
import random
import re
import shutil
import struct
import sys
import unicodedata
import zlib
from collections import Counter, defaultdict
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "creator"))
import convert_edition as c          # noqa: E402
import fm_db_people                  # noqa: E402
import fm_names                      # noqa: E402
import fm26_install                  # noqa: E402
import fm26_history                  # noqa: E402
import fm26_people                   # noqa: E402
import name_rebuilt_records as nrr   # noqa: E402
import rebuild_lost_records as rlr   # noqa: E402
import build                         # noqa: E402

S = 4294967297
SEASON = 2026                       # FM27's current season, 2026/27
IDS = os.path.join(ROOT, "creator", "ids.json")
STATUS = os.path.join(ROOT, "legends", "fm27_status.csv")
STATUS_COLS = ["file", "uid", "dbid", "name", "kind", "role", "status", "obs"]

POSITIONS = ["Pgoa", "Pdls", "Pdce", "Pdrs", "Pdmc", "Pmls", "Pmce", "Pmrs",
             "Paml", "Pamc", "Pamr", "Pace", "Pwbl", "Pwbr"]            # offsets 36..49
ATTRIBUTES = ["PDcr", "PDdr", "PDfn", "PDhd", "PDls", "PDmr", "PDmv", "PDps", "PDpn", "PDtk",
              "PDvs", "PDhn", "PDae", "PDca", "PDcm", "PDkc", "PDth", "PDan", "PDdc", "PDoo",
              "PDpt", "PDrf", "PDft", "PDtc", "PDlf", "PDri", "PDfl", "PDcs", "PDtm", "PDwr",
              "PDlt", "PDec", "PDro", "PDtp", "PDac", "PDfk", "PDst", "PDsm", "PDpc", "PDjm",
              "PDld", "PDdt", "PDbl", "PDbr", "PDcy", "PDag", "PDal", "PDim", "PDij", "PDvt",
              "PDnf", "PDde", "PDcp", "PDcc"]                             # offsets 50..103

# the 8 personality values in the order a people_db record keeps them
PERSONALITY = ["Pada", "Pamb", "Ploy", "Ppre", "Ppro", "Pspo", "Ptem", "Pcvy"]
LANG_COL, PROF_COL = "1818324583", "1886547814"      # "lang", "prof" columns of PElg


def language_ops(uid, langs, rng):
    """The languages grid (PElg) in the shape the FM27 editor writes it (user's
    probe, 2026-11-13): insert a row, set its language, then its fluency - each
    cell op citing the row as it then stands (a new row reads prof 10, proe 2)."""
    ops = []
    for lang, prof in langs:
        nv = ET.Element("record", id="new_value")
        ET.SubElement(nv, "integer", id="lsop", value="0")
        ops.append(build.grid_wrap(uid, "PElg", nv, rng))
        nv = ET.Element("record", id="new_value")
        ET.SubElement(nv, "unsigned", id="id", value=LANG_COL)
        v = ET.SubElement(nv, "record", id="value")
        ET.SubElement(v, "large", id="lang", value=str(lang * S))
        ET.SubElement(v, "integer", id="DBID", value=str(lang))
        ET.SubElement(nv, "integer", id="lsop", value="1")
        o = ET.SubElement(nv, "record", id="olvl")
        ET.SubElement(o, "null", id="lang")
        ET.SubElement(o, "integer", id="prof", value="10")
        ET.SubElement(o, "boolean", id="csln", value="false")
        ET.SubElement(o, "integer", id="proe", value="2")
        ops.append(build.grid_wrap(uid, "PElg", nv, rng))
        if prof != 10:
            nv = ET.Element("record", id="new_value")
            ET.SubElement(nv, "unsigned", id="id", value=PROF_COL)
            ET.SubElement(nv, "integer", id="value", value=str(prof))
            ET.SubElement(nv, "integer", id="lsop", value="1")
            o = ET.SubElement(nv, "record", id="olvl")
            lr = ET.SubElement(o, "record", id="lang")
            ET.SubElement(lr, "large", id="lang", value=str(lang * S))
            ET.SubElement(o, "integer", id="prof", value="10")
            ET.SubElement(o, "boolean", id="csln", value="false")
            ET.SubElement(o, "integer", id="proe", value="2")
            ops.append(build.grid_wrap(uid, "PElg", nv, rng))
    return ops


# the Comparativo legend, in the order the sheet lists it (user, 2026-11-13)
GREEN, ORANGE, YELLOW, RED, BLUE, PURPLE, PINK = (
    "green", "orange", "yellow", "red", "blue", "purple", "pink")


# ------------------------------------------------------------- databases ----

class Edition:
    """One release database: person types and the player block, by DBID."""

    def __init__(self, ed):
        self.db = fm_db_people.PeopleDB(fm26_install.db_dir(ed),
                                        cache=os.path.join(ROOT, "work", "fm%d_people.pkl" % ed))

    def has(self, d):
        return d in self.db.prows

    def type(self, d):
        return self.db.people[self.db.prows[d][0] + 4] if d in self.db.prows else None

    def player_block(self, d):
        """{property: value} for positions and attributes, or {} for a non-player."""
        if self.type(d) not in (2, 3):
            return {}
        s = self.db.prows[d][0]
        rec = self.db.people
        out = {p: rec[s + 36 + i] for i, p in enumerate(POSITIONS)}
        out.update({p: rec[s + 50 + i] for i, p in enumerate(ATTRIBUTES)})
        return {p: v for p, v in out.items() if v}

    def height(self, d):
        """Height in cm, byte 132 (user's examples 2026-11-13: Cicero 189, Adrien
        Silva 175, Baba 182 - all three exact). Byte 134 is the body type, 1
        ectomorph to 5 endomorph, but its property is not known yet."""
        if d not in self.db.prows:
            return None
        h = self.db.people[self.db.prows[d][0] + 132]
        return h if 120 <= h <= 230 else None

    def home_grown(self, d):
        """(club DBIDs, nation DBIDs) of his home-grown status. Each is a 16-byte
        reference entry - row index, DBID, then 00 00, a kind (01 club, 08 nation),
        48 / 46, and 01 ff 00 ff. Verified on Cicero (Braga + Portugal), Adrien
        Silva (Sporting + Portugal), Heldon (Cape Verde + Portugal) and Gyokeres
        (Brommapojkarna + Sweden). A club entry can also come in a short form that
        is not read (Baba's Jeanne d'Arc), so a club list may come up short."""
        if d not in self.db.prows:
            return [], []
        s, e = self.db.prows[d]
        r = self.db.people[s:e]
        clubs, nations = [], []
        for i in range(8, len(r) - 8):
            if r[i:i + 2] == b"\x00\x00" and r[i + 4:i + 8] == b"\x01\xff\x00\xff":
                dbid = struct.unpack_from("<I", r, i - 4)[0]
                if (r[i + 2], r[i + 3]) == (1, 0x48):
                    clubs.append(dbid)
                elif (r[i + 2], r[i + 3]) == (8, 0x46):
                    nations.append(dbid)
        return clubs, nations

    def birth_block(self, d):
        """What follows the date of birth (FM26 only - it is found through
        fm26_people.dob): ethnicity at +5, skin tone at +8, then the nationality (row index, DBID)
        at +13, the 8 personality values at +21, the birth city (row index, DBID)
        at +29. Checked on Baba (Senegal), Adrien Silva (Portugal), Heldon (Cape
        Verde) and Cicero; the personality and skin offsets against first-touch
        odvl in five files (user's probe, 2026-11-13)."""
        b = fm26_people.dob(d)
        if not b or d not in self.db.prows:
            return None
        try:
            dd = datetime.date(b[2], b[1], b[0])
        except ValueError:
            return None
        s, e = self.db.prows[d]
        r = self.db.people[s:e]
        i = r.find(struct.pack("<HH", dd.timetuple().tm_yday, dd.year))
        if i < 0 or i + 37 > len(r):
            return None
        return {"Peth": r[i + 5], "Pskt": r[i + 8], "nation": struct.unpack_from("<I", r, i + 17)[0],
                "personality": dict(zip(PERSONALITY, r[i + 21:i + 29])),
                "city": struct.unpack_from("<I", r, i + 33)[0]}

    def languages(self, d):
        """[(language DBID, fluency)]: a count, then 9-byte entries of row index,
        language DBID and fluency (Baba 19/5 and 88/10, Cicero 21/2, Adrien Silva
        8/5 19/10 15/2 10/5, the user's probe player 24/4 66/5). The NATIVE
        language is not in it - the game works that out itself."""
        if d not in self.db.prows:
            return []
        s, e = self.db.prows[d]
        r = self.db.people[s:e]
        for p in range(104, len(r) - 10):
            n = r[p]
            if not 1 <= n <= 8 or p + 1 + 9 * n > len(r):
                continue
            ents = []
            for k in range(n):
                q = p + 1 + 9 * k
                idx, lang = struct.unpack_from("<II", r, q)
                if not (0 < lang < 400 and idx < lang <= idx + 4 and 1 <= r[q + 8] <= 20):
                    break
                ents.append((lang, r[q + 8]))
            if len(ents) == n:
                return ents
        return []

    def profile_ops(self, uid, d, props, rng, full=False):
        """Height and home-grown status from this database, where the file says
        nothing. Written after the type change, which clears home-grown status."""
        import repair_type_change as rtc
        ops, done = [], []
        h = self.height(d)
        if h and "Phes" not in props:
            ops.append(build.int_op(uid, "Phes", h, rng, odvl=0))
            done.append("height %d" % h)
        clubs, nations = self.home_grown(d)
        if clubs and "Phgc" not in props:
            ops += rtc.hg_ops(str(uid), "Phgc", rtc.HG_CLUB_COL, "Cclu", clubs, build.BUILD, rng)
        if nations and "Phgn" not in props:
            ops += rtc.hg_ops(str(uid), "Phgn", rtc.HG_NATION_COL, "Nnat", nations, build.BUILD, rng)
        if clubs or nations:
            done.append("home-grown %d club(s), %d nation(s)" % (len(clubs), len(nations)))
        if not full:
            return ops, done
        # a recreated person starts empty: everything a database record carries
        # by itself has to be written (user, 2026-11-13: Hugo Seco, Cicero, Baba)
        s, e = self.db.prows[d]
        bt = self.db.people[s + 134]
        if 1 <= bt <= 5 and "Pbdt" not in props:
            ops.append(build.int_op(uid, "Pbdt", bt, rng, odvl=0))
            done.append("body type")
        blk = self.birth_block(d)
        if blk:
            if blk["nation"] and "Pnti" not in props:
                ops.append(nrr.nation_op(uid, blk["nation"], rng))
                done.append("nationality")
            if blk["city"] and "Pcbi" not in props:
                ops.append(build.city_op(uid, blk["city"], rng))
                done.append("birth city")
            for p, v in blk["personality"].items():
                if v and p not in props:
                    ops.append(build.int_op(uid, p, v, rng, odvl=0))
            done.append("personality")
            # ethnicity and skin tone are stored as the editor's own codes (user's
            # probe and FM26 labels, 2026-11-13: Pepe 1 Mediterranean/Hispanic, Baba,
            # Cicero and Heldon 3 African/Caribbean; skin code 10 shows as "Skin
            # Tone 11"). Hair colour and length are NOT in this block - five
            # labelled players fit no byte - so they stay a hand fix.
            if 1 <= blk["Peth"] <= 10 and "Peth" not in props:
                ops.append(build.int_op(uid, "Peth", blk["Peth"], rng, odvl=0))
                done.append("ethnicity")
            if blk["Pskt"] and "Pskt" not in props:
                ops.append(build.int_op(uid, "Pskt", blk["Pskt"], rng, odvl=-1))
                done.append("skin tone")
        langs = self.languages(d)
        if langs and "PElg" not in props:
            ops += language_ops(uid, langs, rng)
            done.append("%d language(s)" % len(langs))
        return ops, done


class Ids:
    """Created ids from creator/ids.json, kept clear of FM26's AND FM27's people:
    `mint_id` only knew FM26, and a high word naming an FM27 person collides."""

    class _Both:
        def __init__(self, bufs):
            self.bufs = bufs

        def find(self, pat):
            return max(b.find(pat) for b in self.bufs)

    def __init__(self, fm26, fm27):
        self.dbs = self._Both([fm26.db.basic, fm27.db.basic])

    def mint(self, key):
        build.seed_id_ledger(IDS)
        used_hi, used_lo, data = build.load_id_ledger(IDS)
        by_key = data.setdefault("by_key", {})
        if key in by_key:
            return int(by_key[key])
        uid, = rlr.free_ids(1, used_hi, used_lo, self.dbs, random.Random(zlib.crc32(key.encode())))
        by_key[key] = str(uid)
        build.save_id_ledger(IDS, used_hi, used_lo, data, [str(uid)])
        return uid


def index_docs(dbids):
    """The FM name index's person documents - FM27's for anyone FM27 still has
    (checked 2026-11-13: its classification agrees with FM27 on 40 of 40 people
    whose type changed, with FM26 on none), a stale FM26 one for the dropped."""
    return nrr.people(dbids)


# --------------------------------------------------------------- the file ---

def dbid_of(uid):
    n = int(uid)
    return n // S if n and n % S == 0 else None


def norm_words(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return {w for w in re.split(r"[\s\-]+", s) if len(w) > 2 and w not in ("dos", "das", "de", "da", "do")}


def fingerprint(rec):
    r = ET.fromstring(ET.tostring(rec))
    for tag in ('large[@id="db_unique_id"]', 'integer[@id="db_random_id"]', 'integer[@id="version"]'):
        e = r.find(tag)
        if e is not None:
            r.remove(e)
    return ET.tostring(r)


def date_of(rec):
    nv = rec.find('*[@id="new_value"]')
    if nv is not None and nv.tag == "date":
        return (int(nv.get("day")), int(nv.get("month")), int(nv.get("year")))
    return None


def plus_years(d, n):
    day, month, year = d
    if (day, month) == (29, 2):
        try:
            datetime.date(year + n, 2, 29)
        except ValueError:
            day = 28
    return (day, month, year + n)


# ------------------------------------------------------------------ ops ----

def attr_op(uid, prop, value, rng):
    """An attribute change in the shape the Legends files write it: a string."""
    return build.scalar_op(uid, prop, ET.Element("string", value=str(value)), rng,
                           ET.Element("string", value="0"))


def position_op(uid, prop, value, rng):
    return build.int_op(uid, prop, value, rng, odvl=0)


def club_ops(uid, club, join, rng):
    """His club, then Date Joined and Date Moved To Nation: setting a club resets
    Date Joined, so the dates have to come after it."""
    ops = [build.ref_op(uid, "Pcti", build.team_ref(club), "Ttea", rng)]
    if join:
        ops.append(build.date_op(uid, "Pcjd", join, rng))
        ops.append(build.date_op(uid, "PCNj", join, rng))
    return ops


# ---------------------------------------------------------------- legends ---

def scan(path):
    tree = ET.parse(path)
    changes = tree.getroot().find('list[@id="db_changes"]')
    created, recs = set(), defaultdict(list)
    for rec in changes:
        if c.rec_prop(rec) == "ADDR":
            for nv in rec.findall('record[@id="new_value"]'):
                u = nv.find('large[@id="db_unique_id"]')
                if u is not None:
                    created.add(u.get("value"))
        t = rec.find('integer[@id="database_table_type"]')
        if t is not None and t.get("value") == "1":
            recs[c.rec_uid(rec)].append(rec)
    return tree, changes, created, recs, c.detect_staff(changes), c.person_names(changes)


def makes_player(rs):
    return any(c.rec_prop(r) == "Ptyp" and r.find('*[@id="new_value"]') is not None
               and r.find('*[@id="new_value"]').get("value") == "2" for r in rs)


def is_legend(uid, rs, created):
    return uid in created or makes_player(rs) or any(c.rec_prop(r) == "Plhs" for r in rs)


def file_club(rs):
    """(club set by Pcti, club of the open spell, its join date)."""
    pcti = None
    for r in rs:
        if c.rec_prop(r) == "Pcti":
            ref = c.club_of(r.find('*[@id="new_value"]'))
            pcti = ref[1] if ref else None
    spells = c.replay_spells([r for r in rs if c.rec_prop(r) == "Pnph"])
    open_sp = next((sp for sp in reversed(spells) if sp["left"] is None and sp.get("team")), None)
    join = None
    j = open_sp.get("join") if open_sp else None
    if j is not None and getattr(j, "tag", None) == "date":
        dd = tuple(int(x) for x in c.dtup(j))
        if dd[2] not in (1900, 1901) and dd[2] >= 1000:
            join = dd
    return pcti, (open_sp["team"][1] if open_sp else None), join


def career_season(rs):
    plhs = [r for r in rs if c.rec_prop(r) == "Plhs"]
    return c.current_season(plhs, None, SEASON) if plhs else None


def twin_of(uid, rs, created, recs, names, dob_of):
    """A created record in the same file that already carries this lost person:
    a copy of his changes (rebuild_lost_records), or the same date of birth and a
    shared name word, or the same date of birth on an unnamed record."""
    mine = [fingerprint(r) for r in rs]
    best, share = None, 0.0
    if mine:
        for cu in created:
            if cu not in _FP:
                _FP[cu] = {fingerprint(r) for r in recs.get(cu, [])}
            n = sum(1 for f in mine if f in _FP[cu])
            if n / len(mine) > share:
                best, share = cu, n / len(mine)
    if share >= 0.3:
        return best, "his changes were copied onto created record %s in FM26" % best
    d = dob_of.get(uid)
    if d:
        for cu in created:
            if dob_of.get(cu) == d:
                nm = names.get(cu)
                if not nm or (norm_words(nm) & norm_words(_NAME.get(uid, ""))):
                    return cu, "already recreated in FM26 as %s (%s)" % (nm or "unnamed", cu)
    return None, None


_FP, _NAME = {}, {}


# Negative PA codes and the middle of the range each stands for (user, 2026-11-13:
# a young player with a fixed PA gets the code whose middle is closest to PA - 5;
# Heldon 130 -> 125 -> -7)
NEG_PA = [(-10, 185), (-95, 175), (-9, 165), (-85, 155), (-8, 145), (-75, 135), (-7, 125),
          (-65, 115), (-6, 105), (-55, 95), (-5, 85), (-45, 75), (-4, 65), (-35, 55), (-3, 45),
          (-25, 35), (-2, 25), (-15, 17), (-1, 10)]
YOUNG_FROM = 2005                    # 21 or younger at the end of 2026
OLD_PROFILE_BEFORE = 3569            # attributes last written before FM24: redo by hand


def negative_pa(pa):
    return min(NEG_PA, key=lambda cm: (abs(cm[1] - (pa - 5)), cm[0]))[0]


def last_int(rs, prop):
    v = None
    for r in rs:
        if c.rec_prop(r) == prop:
            nv = r.find('*[@id="new_value"]')
            if nv is not None and (nv.get("value") or "").lstrip("-").isdigit():
                v = int(nv.get("value"))
    return v


def last_dob(rs):
    d = None
    for r in rs:
        if c.rec_prop(r) == "Pdob" and date_of(r):
            d = date_of(r)
    return d


def player_block_ops(uid, block, props, rng):
    """Positions first - the 20s before the rest, so the editor never puts in its
    own default (it rates a new player 20 at centre back the moment any other
    position is set while none is at 20; user, 2026-11-13: Adrien Silva) - then
    the attributes. Only what the file does not state itself."""
    ops = []
    pos = sorted(((p, v) for p, v in block.items() if p in POSITIONS and p not in props),
                 key=lambda pv: -pv[1])
    for p, v in pos:
        ops.append(position_op(uid, p, v, rng))
    for p, v in block.items():
        if p in ATTRIBUTES and p not in props:
            ops.append(attr_op(uid, p, v, rng))
    return ops


def rebuild_real(fm26_file, out_dir, country):
    """The converter's real-record rebuild (CLAUDE.md 5e) run on the FM26 file,
    straight to FM27's season: the author's deletes and relabels read against the
    rows he saw, every kept row placed by his DOMINANT shift (Abel Ruiz: two rows
    relabelled to one season by a slip come out a season apart), then the club
    spells derived from that career. Returns {uid: (ops, shift)} for each real
    record it rebuilt, keyed by every id of the person."""
    out = os.path.join(out_dir, "fm27 rebuild - %s.xml" % country)
    r = c.convert(fm26_file, out, None, False, False, target_season=SEASON,
                  rebuild_real=True, namer=fm_names.Names())
    got = {}
    for p, v in r["real_rebuilt"].items():
        m = re.search(r"shift ([+-]\d+)", v[1])
        for u in r["members"][p]:
            # the shift is real years -> FM27 only where the rows were read off the
            # database; a career authored after a Clear is shifted from its own years
            real_based = "own Clear" not in v[1]
            got[u] = (v[0], int(m.group(1)) if m else None, real_based)
    return got


def sheet_clubs(country):
    """{player name: [(club id, youth)]} from the squad sheet extract in work/."""
    path = os.path.join(ROOT, "work", "%s_sheet_clubs.json" % country.lower())
    if not os.path.exists(path):
        return {}
    raw = json.load(open(path, encoding="utf-8"))
    cache = build._club_cache()
    out = {}
    for name, entries in raw.items():
        if name.startswith("_"):
            continue
        res = []
        for club, youth in entries:
            hit = build.resolve_club(club, country, cache)
            if hit:
                res.append((str(hit["id"]), youth))
        out[norm_name(name)] = res
    build._club_cache_save(cache)
    return out


def norm_name(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file", help="the FM27 converted file; fixed in place")
    ap.add_argument("--fm26", help="the FM26 file it was converted from (default: "
                    "C:/DBC/FMPT/fm_26_xml_files/FMPT Legends - <country> - Squads.xml)")
    ap.add_argument("--dry-run", action="store_true", help="classify and report, write nothing")
    ap.add_argument("--status-out", help="also write this run's statuses to this CSV (any mode)")
    a = ap.parse_args(argv)
    path = a.file
    country = re.sub(r"^FMPT Legends - (.*) - target\d+.*$", r"\1", os.path.basename(path)[:-4])
    rng = random.Random(zlib.crc32(country.encode()) ^ 20261113)
    # always start from the unfixed conversion, so a rerun never fixes a fix
    keep = os.path.join(os.path.dirname(os.path.abspath(path)), "old",
                        os.path.basename(path)[:-4] + " - unfixed.xml")
    src = keep if os.path.exists(keep) else path
    fm26_file = a.fm26 or os.path.join(r"C:\DBC\FMPT\fm_26_xml_files",
                                       "FMPT Legends - %s - Squads.xml" % country)

    tree, changes, created, recs, staff, names = scan(src)
    fm26, fm27 = Edition(26), Edition(27)
    namer = fm_names.Names()
    by_sheet = sheet_clubs(country)
    hist26 = fm26_history.History(26)
    rebuilt = rebuild_real(fm26_file, os.path.join(ROOT, "work"), country)

    dob_of = {u: last_dob(rs) for u, rs in recs.items() if last_dob(rs)}
    legends = {u: rs for u, rs in recs.items() if is_legend(u, rs, created)}
    real = [u for u in legends if u not in created and dbid_of(u)]
    docs = index_docs([dbid_of(u) for u in real])
    for u in real:
        doc = docs.get(dbid_of(u)) or {}
        _NAME[u] = names.get(u) or doc.get("name") or namer.person(u) or ""

    head = defaultdict(list)       # uid -> ops put right before his first change
    tail = []                      # ops appended at the end of the file
    move = {}                      # old uid -> new created uid
    replace = {}                   # uid -> fresh Plhs/Pnph ops replacing his own
    status = []
    ids = Ids(fm26, fm27)
    count = Counter()

    for uid, rs in legends.items():
        d = dbid_of(uid)
        kind = "created" if uid in created else ("real" if d else "session")
        role = "staff" if uid in staff else "player"
        name = _NAME.get(uid) or names.get(uid) or ""
        obs, st = [], GREEN
        props = {c.rec_prop(r) for r in rs}
        if kind == "session":
            continue                    # a created record's continuation: his own record carries the status
        plhs = [r for r in rs if c.rec_prop(r) == "Plhs"]
        if kind == "created" and role == "player" and plhs and not any(c.parse_op(r)[0] == "3" for r in plhs):
            st = PURPLE
            obs.append("created career never rebuilt by the converter - edit by hand")
            count["created, manual"] += 1
        new_uid = uid
        if kind == "real":
            t26, t27 = fm26.type(d), fm27.type(d)
            doc = docs.get(d) or {}
            fix = rebuilt.get(uid)
            if t27 is None:
                twin, why = (twin_of(uid, rs, created, recs, names, dob_of) if t26 is None else (None, None))
                if twin:
                    count["already recreated in FM26"] += 1
                    continue            # the created twin is the legend; this record is dead weight
                if role == "staff":
                    status.append({"file": country, "uid": uid, "dbid": d, "name": name, "kind": kind,
                                   "role": role, "status": RED,
                                   "obs": "gone from FM27%s; staff are not recreated" % ("" if t26 else " and FM26")})
                    count["staff gone, flagged"] += 1
                    continue
                new = (900000000 * S + len(move)) if a.dry_run else ids.mint("fm27-recreate:%s" % uid)
                move[uid] = new_uid = str(new)
                h = [rlr.addr_row(new, rng)]
                if not ({"Pfna", "Psna", "Pcna", "Pfln"} & props) and doc:
                    first, last, common = nrr.split_name(doc)
                    h.append(nrr.string_op(new, "Pfna", first, rng))
                    if last:
                        h.append(nrr.string_op(new, "Psna", last, rng))
                    if common and common != " ".join(x for x in (first, last) if x):
                        h.append(nrr.string_op(new, "Pcna", common, rng))
                elif not ({"Pfna", "Psna", "Pcna", "Pfln"} & props):
                    st = RED
                    obs.append("no name anywhere - name him by hand")
                block = fm26.player_block(d) if t26 in (2, 3) else {}
                h += player_block_ops(new, block, props, rng)
                prof, done = fm26.profile_ops(new, d, props, rng, full=True) if t26 else ([], [])
                h += prof
                head[uid] = h
                if not (props & set(ATTRIBUTES)) and not block:
                    st = RED
                    obs.append("neither the file nor FM26 has his attributes")
                obs.insert(0, "recreated as new player %s%s" % (new, "" if t26 else " (already missing in FM26)"))
                if done:
                    obs.append("from FM26: " + ", ".join(done))
                obs.append("hair colour, hair length "
                           "and preferred moves not copied yet")
                st = BLUE if st == GREEN else st
                count["recreated"] += 1
            elif role == "player" and t27 == 1 and not makes_player(rs):
                block = fm26.player_block(d) if t26 in (2, 3) else {}
                prof, done = fm26.profile_ops(int(uid), d, props, rng)
                head[uid] = [rlr.type_change(int(uid), rng)] + build.retirement_ops(int(uid), rng) \
                    + player_block_ops(uid, block, props, rng) + prof
                obs.append("staff in FM27: made a player first, retirements cleared"
                           + (", positions and attributes from FM26" if block else ""))
                if not block and not (props & set(ATTRIBUTES)):
                    st = PURPLE
                    obs.append("no attributes in the file or in FM26")
                if done:
                    obs.append("from FM26: " + ", ".join(done))
                obs.append("body type not copied yet")
                count["staff -> player"] += 1
            if role == "player":
                # every real legend: past transfers cleared (user, 2026-11-13)
                head[uid] = head.get(uid, []) + [build.past_transfers_clear(int(new_uid), rng)]
                if fix:
                    replace[uid] = fix[0]
                    count["history rebuilt"] += 1
                elif plhs:
                    st = ORANGE if st == GREEN else st
                    obs.append("playing history could not be rebuilt - check it")
                # age: FM26's date of birth moved by the same shift as the career
                if not dob_of.get(uid):
                    b = fm26_people.dob(d) if t26 else None
                    shift = real_shift(fix[0], d, hist26) if fix else None
                    if shift is None and fix and fix[2]:
                        shift = fix[1]          # no season with figures to match (Nehuen Perez)
                    if b and shift is not None:
                        dob_of[uid] = plus_years(b, shift)
                        tail.append(build.date_op(int(new_uid), "Pdob", dob_of[uid], rng))
                        obs.append("born %d/%d/%d: FM26's date moved by the career's %+d" % (dob_of[uid] + (shift,)))
                        count["birth date"] += 1
                    else:
                        st = PURPLE if st == GREEN else st
                        obs.append("no date of birth to move - set his age by hand")
                last_attr = max((c.rec_build(r) or 0 for r in rs if c.rec_prop(r) in ATTRIBUTES), default=None)
                if last_attr and last_attr < OLD_PROFILE_BEFORE:
                    st = PURPLE if st in (GREEN, BLUE) else st
                    obs.append("profile from %s - redo by hand" % c.EDITION_BY_BUILD.get(last_attr, last_attr))
                    count["old profile"] += 1
                # club: the squad sheet's, where the file does not set one
                pcti, open_club, join = file_club(rs)
                if not pcti:
                    team27 = str((doc.get("team") or {}).get("fm_id") or "")
                    career = {ci_club for ci_club in _career_clubs(fix[0] if fix else plhs)}
                    cands = by_sheet.get(norm_name(name), [])
                    want = next((cl for cl, _y in cands if cl in career), cands[0][0] if cands else None)
                    if want is None:
                        want = open_club
                    if want and want != team27:
                        tail.extend(club_ops(int(new_uid), int(want), join, rng))
                        obs.append("club set to %s%s" % (namer.club(want) or want,
                                                         " (squad sheet)" if cands else " (his open club spell)"))
                        count["club set"] += 1
                    elif not want and not cands:
                        obs.append("not in the squad sheet - club left as FM27 has it")
        # negative PA for the young (user, 2026-11-13)
        pa = last_int(rs, "PPAB")
        born = dob_of.get(uid)
        if role == "player" and pa and pa > 0 and born and born[2] >= YOUNG_FROM:
            code = negative_pa(pa)
            tail.append(build.int_op(int(new_uid), "PPAB", code, rng, odvl=pa))
            obs.append("PA %d -> %d" % (pa, code))
            count["negative PA"] += 1
        if role == "player" and uid not in replace:
            cs = career_season(rs)
            if cs is not None and cs != SEASON:
                st = ORANGE if st == GREEN else st
                obs.append("career reads season %d, not %d" % (cs, SEASON))
        status.append({"file": country, "uid": new_uid, "dbid": d or "", "name": name,
                       "kind": "recreated" if uid in move else kind, "role": role,
                       "status": st, "obs": "; ".join(obs)})

    print("%s: %d legends; %s" % (country, len(status), dict(count)))
    print("status:", dict(Counter(s["status"] for s in status)))
    if a.status_out:
        with open(a.status_out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=STATUS_COLS, lineterminator="\n")
            w.writeheader()
            w.writerows(status)
    if a.dry_run:
        return

    # write: head ops before each person's first change; his own playing history
    # and club spells swapped for the rebuilt ones where they were rebuilt;
    # moved records retargeted; tail ops at the very end (after every club change)
    out, started, placed = [], set(), set()
    for rec in list(changes):
        u = rec.find('large[@id="db_unique_id"]')
        uid = u.get("value") if u is not None else None
        if uid in head and uid not in started:
            out.extend(head[uid])
            started.add(uid)
        if uid in replace and c.rec_prop(rec) in ("Plhs", "Pnph"):
            if uid not in placed:
                for op in replace[uid]:
                    op = copy.deepcopy(op)
                    op.find('large[@id="db_unique_id"]').set("value", move.get(uid, uid))
                    out.append(op)
                placed.add(uid)
            continue
        if uid in move and c.rec_prop(rec) != "ADDR":
            u.set("value", move[uid])
        out.append(rec)
    out.extend(tail)
    for rec in list(changes):
        changes.remove(rec)
    changes.extend(out)

    os.makedirs(os.path.dirname(keep), exist_ok=True)
    if not os.path.exists(keep):
        shutil.copy2(path, keep)
    tree.write(path, encoding="unicode", xml_declaration=False)
    print("fixed in place: %s (%d records retargeted, %d histories rebuilt); unfixed copy: %s" % (
        path, len(move), len(placed), keep))

    rows = []
    if os.path.exists(STATUS):
        rows = [r for r in csv.DictReader(open(STATUS, encoding="utf-8")) if r["file"] != country]
    rows += status
    os.makedirs(os.path.dirname(STATUS), exist_ok=True)
    with open(STATUS, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=STATUS_COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["file"], r["name"].lower(), r["uid"])))
    print("statuses -> %s" % STATUS)


def real_shift(ops, d, hist):
    """How many years the legend's career sits after the real one: each season of
    the rebuilt career that records figures is matched to FM26's own row with the
    same club, appearances and goals, and the most common gap wins. Not the
    rebuild's own shift - a career the FM24 conversion already rewrote is read as
    written, so that shift is only FM26 -> FM27 (Marco Baixinho +1 against the
    +15 that puts his birth in 2004, user 2026-11-13)."""
    import clean_import as ci
    real = defaultdict(list)
    for r in hist.rows(d):
        if r["club"] and (r["apps"] or 0) > 0:
            real[(str(r["club"]), r["apps"], r["gols"] or 0)].append(r["year"])
    gaps = Counter()
    for r in ci.replay([o for o in ops if c.rec_prop(o) == "Plhs"]):
        k = (ci.club_key(r), r["apps"], r["gols"] or 0)
        if r["year"] and (r["apps"] or 0) > 0 and k in real:
            for y in real[k]:
                gaps[r["year"] - y] += 1
    return gaps.most_common(1)[0][0] if gaps else None


def _career_clubs(ops):
    """Club ids a playing-history op list names, in values or snapshots."""
    out = set()
    for r in ops:
        _l, _c, val, st = c.parse_op(r)
        for ref in ((st or {}).get("club"),
                    c.club_of(val) if val is not None and val.tag == "record" else None):
            if ref:
                out.add(str(ref[1]))
    return out


if __name__ == "__main__":
    main()
