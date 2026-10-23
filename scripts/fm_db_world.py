"""Nations and cities out of an FM database, by the id a person carries.

A person read by `fm_db_people` points at the world twice and neither pointer
is usable on its own: the nationality is a 0-based row number in the nation
table, not the DBID the editor writes, and the city of birth is a row number
in the city table. Both tables live outside the two people files.

    client_db.dat   the city rows - nation, latitude, longitude, DBID
    lang_db.dat     the names, one block per shipped language

Those two are not a single stream like `people_db.dat`. Each is a 12-byte
header and then one zlib stream per table, laid end to end; the last table of
the file is a directory naming the others. Every table starts with its own
9-byte header and a u32 row count.

    nation names    dbid:u32 name z short z abbr adjective z
    city names      dbid:u32 name:len+bytes 00 00
    city rows       fixed 43 bytes, first row at offset 14
                    .. lat:f32@2 lon:f32@6 nation:u8@11 .. idx:u32@31
                    dbid:u32@35 dbid:u32@39

Row order is the same in both files, so the row number a person carries is
an index into either, and the DBID written by a table row is the id the
editor uses - `Pnti` on a person is a nation DBID, `Pcbi` a city DBID.

Checked on FM18 only. The nation table comes out 249 rows with index 162 ->
Portugal 788, 143 -> France 769, 189 -> Brazil 1651, 194 -> Peru 1656. For
cities there is no changeset value to check against, so the check is the
nation: for 24,478 sampled people the city decoded from their record belongs
to the nation they are a citizen of 97.3% of the time, and the rest are
people born abroad. Beto (DBID 727969) comes out born in Lisboa.

What is *not* decoded: the field at offset 18 of a `basic_people_db` row,
which an earlier read of that file called the city of birth. It is not one -
people born in one city carry different values and one value spans many
cities. It indexes a 62,626-row table of `server_db.dat` that is the 62,377
clubs plus the 249 national sides, so it is a team, most likely the current
one.
"""
import os
import struct
import sys
import zlib

CITY_ROW = 43
CITY_ROW_START = 14

# Table positions inside each container, English first. Both are verified on
# load rather than trusted: a wrong guess fails the parse or the id match.
NATION_NAMES, CITY_NAMES = 0, 3
CITY_ROWS = 2


def sections(path):
    """The decompressed tables of a container file, in order.

    One stream per table, laid end to end: zlib in FM18, Zstandard in FM26.
    Either way the reader walks them by what the last stream left unread."""
    raw = open(path, "rb").read()
    pos = raw.find(b"\x78\x9c")
    zpos = raw.find(bytes.fromhex("28b52ffd"))
    if pos >= 0 and (zpos < 0 or pos < zpos):
        out = []
        while 0 <= pos < len(raw):
            z = zlib.decompressobj()
            out.append(z.decompress(raw[pos:]))
            pos = raw.find(b"\x78\x9c", len(raw) - len(z.unused_data))
        return out
    # FM26 wraps these containers in a further ".fmf" header, so the first frame
    # is found rather than assumed - people_db starts at 12, lang_db at 38.
    from compression import zstd
    MAGIC = bytes.fromhex("28b52ffd")
    out, pos = [], raw.find(MAGIC)
    while 0 <= pos < len(raw):
        d = zstd.ZstdDecompressor()
        chunk = d.decompress(raw[pos:])
        if chunk:
            out.append(chunk)
        rest = len(raw) - len(d.unused_data)
        pos = raw.find(MAGIC, max(rest, pos + 4))
    return out


def _string(buf, pos, pad=1):
    n = struct.unpack_from("<I", buf, pos)[0]
    return buf[pos + 4:pos + 4 + n].decode("utf-8", "replace"), pos + 4 + n + pad


def _row_count(buf):
    return struct.unpack_from("<I", buf, 9)[0]


def _nation_names(buf):
    rows, pos = [], 13
    for _ in range(_row_count(buf)):
        dbid = struct.unpack_from("<I", buf, pos)[0]
        name, pos = _string(buf, pos + 4)
        _short, pos = _string(buf, pos)
        abbr, pos = _string(buf, pos, pad=0)
        adjective, pos = _string(buf, pos)
        rows.append((dbid, name, abbr, adjective))
    if pos != len(buf):
        raise ValueError("nation table does not end where it should")
    return rows


def _city_names(buf):
    rows, pos = [], 13
    for _ in range(_row_count(buf)):
        dbid = struct.unpack_from("<I", buf, pos)[0]
        name, pos = _string(buf, pos + 4, pad=2)
        rows.append((dbid, name))
    if pos != len(buf):
        raise ValueError("city table does not end where it should")
    return rows


def _city_rows(buf, count):
    """(nation index, latitude, longitude, DBID) per city, in row order."""
    out = []
    for i in range(count):
        o = CITY_ROW_START + CITY_ROW * i
        idx, dbid, again = struct.unpack_from("<III", buf, o + 31)
        if idx != i or dbid != again:
            raise ValueError("city row %d is not framed as expected" % i)
        lat, lon = struct.unpack_from("<ff", buf, o + 2)
        out.append((buf[o + 11], lat, lon, dbid))
    return out


class WorldDB:
    """The nation and city tables of a release database, by row index."""

    def __init__(self, dbdir):
        lang = sections(os.path.join(dbdir, "lang_db.dat"))
        client = sections(os.path.join(dbdir, "client_db.dat"))
        self._nations = _nation_names(lang[NATION_NAMES])
        names = _city_names(lang[CITY_NAMES])
        rows = _city_rows(client[CITY_ROWS], len(names))
        if [r[3] for r in rows] != [n[0] for n in names]:
            raise ValueError("city rows and city names are not the same table")
        self._cities = [(n[1],) + r for n, r in zip(names, rows)]

    def nation(self, index):
        """{dbid, name, abbr, adjective} for a person's nationality index."""
        if index is None or not 0 <= index < len(self._nations):
            return None
        dbid, name, abbr, adjective = self._nations[index]
        return {"index": index, "dbid": dbid, "name": name,
                "abbr": abbr, "adjective": adjective}

    def city(self, index):
        """{dbid, name, nation, lat, lon} for a person's city of birth."""
        if index is None or not 0 <= index < len(self._cities):
            return None
        name, nation, lat, lon, dbid = self._cities[index]
        return {"index": index, "dbid": dbid, "name": name,
                "nation": nation, "latitude": lat, "longitude": lon}

    def resolve(self, person):
        """A person record from `fm_db_people`, with the two ids named."""
        out = dict(person)
        out["nation"] = self.nation(person.get("nationality"))
        out["city"] = self.city(person.get("city_of_birth"))
        return out


if __name__ == "__main__":
    world = WorldDB(sys.argv[1])
    print("%d nations, %d cities" % (len(world._nations), len(world._cities)))
    import fm_db_people
    people = fm_db_people.PeopleDB(sys.argv[1],
                                   cache=os.environ.get("FM_PEOPLE_CACHE"))
    for arg in sys.argv[2:]:
        r = people.get(int(arg))
        if r is None:
            print(arg, "not in this database")
            continue
        r = world.resolve(r)
        print("%s %r nation %s city %s" % (
            arg, r.get("full_name"),
            (r["nation"] or {}).get("name"), (r["city"] or {}).get("name")))
