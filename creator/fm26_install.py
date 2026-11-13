"""Where the FM26 Editor's release database is, and how to unpack it - on
macOS or Windows, under Python 3.9 or 3.14.

The database folder is `<Steam library>/steamapps/common/Football Manager 26
Editor/shared/data/database/db/2620/2620_fm`. The Steam libraries are the
default install (per OS) plus every one listed in `libraryfolders.vdf`, so an
editor installed on another drive is found too. FM26_EDITOR_DIR, the editor's
own folder, overrides the search.

Its files are zstd streams. Python 3.14 has zstd built in (`compression.zstd`);
3.9 does not, so `decompress` falls back to the `zstd` command and
`zstd_python` names an interpreter that can run a module's `--build`.
"""
import os
import re
import shutil
import subprocess
import sys

EDITOR = "Football Manager 26 Editor"
DB = os.path.join("shared", "data", "database", "db", "2620", "2620_fm")
# Every edition's release database sits in the same place under its own editor
# and folder; FM27's files have the same names and framing as FM26's.
EDITIONS = {26: ("Football Manager 26 Editor", "2620"),
            27: ("Football Manager 27 Editor", "2700"),
            # FM24's editor ships no database: it reads the game's, which sits
            # under data/ instead of shared/data/ (final update 24.3 = 2430)
            24: ("Football Manager 2024", "2430")}


def _steam_roots():
    if sys.platform == "win32":
        return [os.path.join(os.environ.get(v, d), "Steam")
                for v, d in (("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                             ("ProgramFiles", r"C:\Program Files"))]
    if sys.platform == "darwin":
        return [os.path.expanduser("~/Library/Application Support/Steam")]
    return [os.path.expanduser("~/.steam/steam"), os.path.expanduser("~/.local/share/Steam")]


def _libraries():
    libs = []
    for root in _steam_roots():
        libs.append(root)
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf):
            text = open(vdf, encoding="utf-8", errors="ignore").read()
            libs += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', text)]
    return list(dict.fromkeys(libs))


def db_dir(edition=26):
    """The edition's database folder (2620_fm for FM26, 2700_fm for FM27,
    2430_fm for FM24).
    When no install has it, the default path, so a missing file names where it
    was looked for. FM26_EDITOR_DIR / FM27_EDITOR_DIR override the search."""
    editor, ver = EDITIONS[edition]
    db = os.path.join("data" if edition < 26 else os.path.join("shared", "data"),
                      "database", "db", ver, ver + "_fm")
    env = "FM%d_EDITOR_DIR" % edition
    if os.environ.get(env):
        return os.path.join(os.environ[env], db)
    found = [os.path.join(lib, "steamapps", "common", editor, db) for lib in _libraries()]
    return next((d for d in found if os.path.isdir(d)), found[0])


def has_zstd():
    try:
        from compression import zstd  # noqa: F401
        return True
    except ImportError:
        return False


def decompress(raw):
    """A zstd stream (one or more frames) unpacked. Frame by frame through a
    memoryview: `zstd.decompress` copies the rest of the input after every
    frame, and pl_hist_dt has 88k of them (hours instead of a second)."""
    if has_zstd():
        from compression import zstd
        mv, pos, out = memoryview(raw), 0, []
        while pos < len(mv):
            size = zstd.get_frame_size(mv[pos:])
            out.append(zstd.ZstdDecompressor().decompress(mv[pos:pos + size]))
            pos += size
        return b"".join(out)
    if not shutil.which("zstd"):
        raise RuntimeError("unpacking FM26's database needs Python 3.14 or the zstd command")
    return subprocess.run(["zstd", "-d", "-q", "-c"], input=raw,
                          stdout=subprocess.PIPE, check=True).stdout


def zstd_python():
    """The command of a Python with built-in zstd: this one when it has it,
    else the first candidate that actually imports it (an asdf shim with no
    version set is on the PATH but does not run)."""
    if has_zstd():
        return [sys.executable]
    cands = [["py", "-3.14"]] if sys.platform == "win32" else []
    cands += [["python3.14"], ["/opt/homebrew/bin/python3.14"], ["/opt/homebrew/bin/python3"]]
    for cmd in cands:
        try:
            ok = subprocess.run(cmd + ["-c", "import compression.zstd"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        except OSError:
            continue
        if ok:
            return cmd
    raise RuntimeError("rebuilding the FM26 cache needs Python 3.14 (python.org)")
