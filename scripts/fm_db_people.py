"""People out of an FM database, keyed by DBID.

The editor changesets we write only carry the values an author changed. To
check a conversion - did this legend keep his birth date, his nationality,
his personality - we need the values the game itself ships, and those live in
two files of the release database.

`basic_people_db.dat` is a flat table: one 60-byte row per person, in DBID
order, holding the summary the game shows before a person is fully loaded.
`people_db.dat` is the real thing, one variable-length record per person with
the attributes and the name. Both are a 12-byte header and then one compressed
stream - zlib in FM18, Zstandard in FM26.

Row framing is the same in both files: the DBID is written twice in a row, and
that doubling is what a row can be found by and the check that it was read
correctly.

    basic_people_db  idx:u32 dbid:u32 dbid:u32 0x11 type:u8 <payload>

with the payload 46 bytes for types 1-3, 12 for type 4 and 4 for type 5. The
type byte is the editor's Ptyp.

    people_db        id:u32 type:u8 <payload> id:u32 dbid:u32 dbid:u32

The people_db payload has a fixed head (the player attribute block lives at a
constant offset for type 2) and then a variable tail of career history, so the
name and the birth date are found by signature rather than by offset:

    fna:u32 sna:u32 cna:u32 len:u32 full_name[len] doy:u16 year:u16 ...
    ... skin/hair bytes ... nation:u32 personality[8] city:u32

A date is a day-of-year and a year, with 1/1900 as the null date.

All of this was read off FM18 and only checked there. FM26 decompresses and its
people_db frames records the same way, but its basic_people_db row is a
different size, so the basic half of a lookup stops after one row.

Measured against the `odvl` values in the FM18 Portugal changeset, the date of
birth read this way is right for 712 of 718 people.

Nationality and city of birth are row numbers in tables that live in other
files of the release, so they come back as numbers; `fm_db_world` turns them
into names and into the DBIDs the editor writes. What is *not* decoded: the
second nationality, and the field at offset 18 of a basic_people_db row that
this module used to return as the city - it is a team, not a city.
"""
import datetime
import os
import pickle
import struct
import sys

NIL = 0xFFFFFFFF
NULL_DATE = (1, 1900)

# people_db, offset from the record start: the type-2 attribute block, one
# byte each, 1-20. Names verified against the changeset `odvl` except where
# the comment says otherwise.
PLAYER_ATTRS = {
    44: "crossing", 45: "dribbling", 46: "finishing", 47: "heading",
    48: "long_shots", 49: "marking", 50: "off_the_ball", 51: "passing",
    52: "penalty_taking", 53: "tackling", 54: "vision",
    55: "handling", 56: "aerial_reach", 57: "command_of_area",
    58: "communication", 59: "kicking", 60: "throwing",
    61: "anticipation", 62: "decisions", 63: "one_on_ones", 64: "positioning",
    65: "reflexes", 66: "first_touch", 67: "technique", 68: "left_foot",
    69: "right_foot", 70: "flair", 71: "corners", 72: "teamwork",
    73: "work_rate", 74: "long_throws", 75: "eccentricity",
    76: "rushing_out", 77: "tendency_to_punch",
    78: "acceleration", 79: "free_kick_taking", 80: "strength", 81: "stamina",
    82: "pace", 83: "jumping_reach", 84: "leadership", 85: "dirtiness",
    86: "balance", 87: "bravery", 88: "consistency", 89: "aggression",
    90: "agility", 91: "important_matches", 92: "injury_proneness",
    93: "versatility", 94: "natural_fitness", 95: "determination",
    96: "composure", 97: "concentration",
}

# people_db, offset from the birth date: the person-level personality block,
# carried by every person type, not just players. The order is the editor's
# Pada Pamb Ploy Ppre Ppro Pspo Ptem Pcvy; adaptability and pressure are
# placed by that order, the other six by changeset `odvl`.
PERSONALITY = [
    "adaptability", "ambition", "loyalty", "pressure",
    "professionalism", "sportsmanship", "temperament", "controversy",
]

BASIC_ROW = {1: 60, 2: 60, 3: 60, 4: 26, 5: 18}


def load(path):
    raw = open(path, "rb").read()
    z = raw.find(b"\x78\x9c")              # zlib, FM18 and older
    if 0 <= z <= 16:
        import zlib
        return zlib.decompressobj().decompress(raw[z:])
    from compression import zstd           # FM26
    return zstd.decompress(raw[12:])


def to_date(doy, year):
    if (doy, year) == NULL_DATE or not 1 <= doy <= 366:
        return None
    try:
        return datetime.date(year, 1, 1) + datetime.timedelta(days=doy - 1)
    except ValueError:
        return None


def _basic_start(buf, probe=200):
    """First row offset. The header length differs between editions."""
    best = (0, 53)
    for start in range(0, 160):
        pos, idx = start, 0
        while idx < probe and pos + 14 <= len(buf):
            i, a, b = struct.unpack_from("<III", buf, pos)
            if i != idx or a != b or buf[pos + 12] != 0x11 or buf[pos + 13] not in BASIC_ROW:
                break
            pos += BASIC_ROW[buf[pos + 13]]
            idx += 1
        if idx > best[0]:
            best = (idx, start)
        if idx == probe:
            break
    return best[1]


def walk_basic(buf):
    """dbid -> (offset, person type). Rows are sequential and self-numbered."""
    out, pos, idx = {}, _basic_start(buf), 0
    while pos + 14 <= len(buf):
        i, a, b = struct.unpack_from("<III", buf, pos)
        if i != idx or a != b or buf[pos + 12] != 0x11:
            break
        kind = buf[pos + 13]
        if kind not in BASIC_ROW:
            break
        out[a] = (pos, kind)
        pos += BASIC_ROW[kind]
        idx += 1
    if len(out) < 1000:
        return _walk_basic_framed(buf)
    return out


def _walk_basic_framed(buf):
    """The same table for FM26 and FM27, whose rows are no longer the FM18
    sizes in BASIC_ROW. The framing is unchanged - idx:u32 dbid:u32 dbid:u32
    0x11 type:u8 - so each row is found by its frame, and its index must be the
    previous row's plus one, which rules out a frame-shaped run of payload.
    Checked 2026-11-13 on FM27: Adrien Silva type 1, Gyokeres type 2."""
    out, q, last = {}, 0, None
    unpack = struct.unpack_from
    while True:
        q = buf.find(b"\x11", q + 1)
        if q < 0:
            return out
        if q < 12 or q + 1 >= len(buf) or not 1 <= buf[q + 1] <= 5:
            continue
        i, a, b = unpack("<III", buf, q - 12)
        if a != b or a == 0 or (last is not None and i != last + 1):
            continue
        out[a] = (q - 12, buf[q + 1])
        last = i


def _people_trailer(buf, pos, window=4000):
    """End of the record at `pos`, found by its id repeated before the DBID."""
    rid = struct.unpack_from("<I", buf, pos)[0]
    tgt = struct.pack("<I", rid)
    q = pos + 5
    while True:
        q = buf.find(tgt, q, pos + window)
        if q < 0 or q + 12 > len(buf):
            return -1, 0
        a, b = struct.unpack_from("<II", buf, q + 4)
        if a == b and a != 0:
            if q + 17 > len(buf):
                return q + 12, a
            nid = struct.unpack_from("<I", buf, q + 12)[0]
            if nid < 2_000_000 and 1 <= buf[q + 16] <= 5:
                return q + 12, a
        q += 1


def walk_people(buf):
    """dbid -> (start, end). Resyncs on a head whose own trailer is in place."""
    n = len(buf)

    def head_ok(p):
        return (p >= 12 and p + 17 <= n and 1 <= buf[p + 4] <= 5
                and struct.unpack_from("<I", buf, p)[0] < 2_000_000
                and buf[p - 8:p - 4] == buf[p - 4:p] != b"\0\0\0\0")

    start = next((s for s in range(0, 24) if _people_trailer(buf, s)[0] > 0), 4)
    out, pos = {}, start
    while pos + 17 <= n:
        end = -1
        if 1 <= buf[pos + 4] <= 5 and struct.unpack_from("<I", buf, pos)[0] < 2_000_000:
            end, dbid = _people_trailer(buf, pos)
        if end < 0:
            p = pos + 1
            while p + 17 <= n and not head_ok(p):
                p += 1
            if p + 17 > n:
                break
            pos = p
            continue
        out[dbid] = (pos, end)
        pos = end
    return out


def _name_block(buf, start, end):
    """(offset of the length word, name, doy, year, nation) for one record.

    Anchored on the three name ids, the printable name, a plausible date and a
    nation index right behind it - the tail before it is variable in length.
    """
    p = start + 16
    while p + 24 < end:
        ln = struct.unpack_from("<I", buf, p)[0]
        if ln <= 80 and p + 4 + ln + 12 <= end:
            s = buf[p + 4:p + 4 + ln]
            if all(b >= 0x20 and b != 0x7F for b in s):
                doy, year = struct.unpack_from("<HH", buf, p + 4 + ln)
                if 1 <= doy <= 366 and 1850 <= year <= 2050:
                    nation = struct.unpack_from("<I", buf, p + 4 + ln + 8)[0]
                    fna, sna, cna = struct.unpack_from("<III", buf, p - 12)
                    if (nation < 250
                            and (fna == NIL or fna < 215000)
                            and (sna == NIL or sna < 445000)
                            and (cna == NIL or cna < 70000)):
                        return p, s, doy, year, nation
        p += 1
    return None


class PeopleDB:
    """A release database directory, looked up by person DBID."""

    def __init__(self, dbdir, cache=None):
        self.basic = load(os.path.join(dbdir, "basic_people_db.dat"))
        self.people = load(os.path.join(dbdir, "people_db.dat"))
        key = (len(self.basic), len(self.people))
        if cache and os.path.exists(cache):
            saved = pickle.load(open(cache, "rb"))
            if saved.get("key") == key:
                self.brows, self.prows = saved["brows"], saved["prows"]
                return
        self.brows = walk_basic(self.basic)
        self.prows = walk_people(self.people)
        if cache:
            pickle.dump({"key": key, "brows": self.brows, "prows": self.prows},
                        open(cache, "wb"))

    def __contains__(self, dbid):
        return dbid in self.prows or dbid in self.brows

    def __len__(self):
        return len(set(self.brows) | set(self.prows))

    def get(self, dbid):
        rec = {"dbid": dbid}
        row = self.brows.get(dbid)
        if row:
            pos, kind = row
            rec["basic_person_type"] = kind
            rec["person_type"] = kind
            if kind in (1, 2, 3):
                nat, team, _, nat2 = struct.unpack_from("<IIII", self.basic, pos + 14)
                # raw ids that nothing has checked: no changeset carries an
                # odvl for either. `team` indexes the club+country table of
                # server_db.dat and is not the city of birth.
                rec["basic_team"] = None if team == NIL else team
                rec["second_nationality"] = None if nat2 == NIL else nat2
                rec["basic_nationality"] = None if nat == NIL else nat
        span = self.prows.get(dbid)
        if not span:
            return rec if row else None
        start, end = span
        # the two files disagree on the type for a few percent of people; the
        # attribute block is only present when people_db says 2, so that one wins
        rec["person_type"] = self.people[start + 4]
        nb = _name_block(self.people, start, end)
        if nb:
            p, name, doy, year, nation = nb
            fna, sna, cna = struct.unpack_from("<III", self.people, p - 12)
            base = p + 4 + len(name)
            rec.update(
                first_name_id=None if fna == NIL else fna,
                second_name_id=None if sna == NIL else sna,
                common_name_id=None if cna == NIL else cna,
                full_name=name.decode("utf-8", "replace") or None,
                date_of_birth=to_date(doy, year),
                nationality=nation,
                personality={n: self.people[base + 12 + i]
                             for i, n in enumerate(PERSONALITY)},
                city_of_birth=(struct.unpack_from("<I", self.people, base + 20)[0]
                               if base + 24 <= end else None),
            )
        if rec.get("person_type") == 2:
            rec["attributes"] = {n: self.people[start + o]
                                 for o, n in sorted(PLAYER_ATTRS.items())}
        return rec

    def __getitem__(self, dbid):
        r = self.get(dbid)
        if r is None:
            raise KeyError(dbid)
        return r


if __name__ == "__main__":
    db = PeopleDB(sys.argv[1], cache=os.environ.get("FM_PEOPLE_CACHE"))
    print("%d people" % len(db))
    for arg in sys.argv[2:]:
        r = db.get(int(arg))
        if r is None:
            print(arg, "not in this database")
            continue
        print("%(dbid)s type %(person_type)s %(full_name)r born %(date_of_birth)s"
              " nation %(nationality)s city %(city_of_birth)s" % {
                  **{"full_name": None, "date_of_birth": None,
                     "nationality": None, "city_of_birth": None}, **r})
        if "personality" in r:
            print("   ", r["personality"])
