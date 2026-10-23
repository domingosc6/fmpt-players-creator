"""Names out of an FM database's people_db.dat.

The file is a 12-byte header and then one compressed stream - zlib in FM18,
Zstandard in FM26. Inside, a name row is

    id:u32  05 00 00 00  00  len:u32  name[len]  pad  id:u32  t1:u32  t2:u32

with the id written either side of the name, which is both the signature the
rows can be found by and the check that a row was read correctly. The pad
between the name and the repeated id differs by edition, so it is measured
rather than assumed.
"""
import os, struct, sys

MARK = b"\x05\x00\x00\x00\x00"


def load(path):
    raw = open(path, "rb").read()
    z = raw.find(b"\x78\x9c")              # zlib, FM18 and older
    if 0 <= z <= 16:
        import zlib
        return zlib.decompressobj().decompress(raw[z:])
    from compression import zstd           # FM26
    return zstd.decompress(raw[12:])


def names(buf, max_pad=16):
    out, i = {}, 0
    while True:
        i = buf.find(MARK, i)
        if i < 0:
            return out
        head = i - 4
        if head < 0:
            i += 1
            continue
        pid = struct.unpack_from("<I", buf, head)[0]
        ln = struct.unpack_from("<I", buf, i + 5)[0]
        end = i + 9 + ln
        if not (0 < ln <= 120) or end + max_pad + 4 > len(buf):
            i += 1
            continue
        for pad in range(0, max_pad + 1, 4):
            if struct.unpack_from("<I", buf, end + pad)[0] == pid:
                try:
                    out[pid] = buf[i + 9:end].decode("utf-8")
                except UnicodeDecodeError:
                    pass
                i = end + pad + 12
                break
        else:
            i += 1


if __name__ == "__main__":
    buf = load(sys.argv[1])
    n = names(buf)
    print("decompressed %d bytes, %d names" % (len(buf), len(n)))
    for k in sys.argv[2:]:
        print("  %-10s %s" % (k, n.get(int(k))))
