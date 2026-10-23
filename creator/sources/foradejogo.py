"""foradejogo.net, through the Wayback Machine (the live site is gone): plain
HTTP, no Cloudflare (checked 2026-10-10). The link in the sheet is the
archived page itself, web.archive.org/web/<timestamp>/https://www.foradejogo
.net/player.php?player=<id>[&language=2]; the archive serves it in the
language of its capture - Portuguese (Data de Nascimento, Época) or English
(Birth Date, Season) - so both sets of labels are read.

Career table (class "careertable"), newest first, one VISIBLE row per season
and club: season ("2012/13", or a calendar year "2019" in Brazil; blank on a
follow-on row), logo, club, country flag (flags/<n>.png, the site's own
country number), competition, games, goals, ... The competition is the
league level - "I" (Portugal's 1ª), or a letter and the level in brackets,
"A (1)" Série A, "D (4)", "I E (5)" a state league. A youth side has an age
grade there instead - JUN, JUV, INI, INF, ESC - and escalao=<age> in its team
link (senior is escalao=0): read as a youth row. Games are starts and,
in brackets, sub appearances: "3(7)" is 10 games. The cup ("Taças"),
continental ("Cont") and total rows sit hidden under the league row and are
not read (user, 2026-10-09: league columns only).

Profile: name, full name, birth date (1980-11-16), nationality, birthplace
("Dracena - São Paulo": town, then its state or district), height, position.
"""
import html
import json
import os
import re
import time
import urllib.request

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")
NATIONS_CACHE = os.path.join(CACHE_DIR, "foradejogo_nations.json")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"
ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII"}
# the site's country numbers seen so far; the rest are read off the archived
# nation.php page once and cached
KNOWN = {"16": "Austria", "30": "Brazil", "44": "Cyprus", "76": "Greece", "104": "Israel",
         "154": "Portugal", "163": "Romania"}
# a youth side's age grade in the competition cell: juniores, juvenis,
# iniciados, infantis, escolas
YOUTH_GRADES = {"JUN", "JUV", "INI", "INF", "ESC"}
LABELS = {"dob": ("Birth Date", "Data de Nascimento"), "nation": ("Nation", "Nacionalidade"),
          "birthplace": ("Birthplace", "Naturalidade"), "height": ("Height", "Altura"),
          "position": ("Position", "Posição")}


def player_id(url):
    m = re.search(r"player=(\d+)", url)
    return m.group(1) if m else None


def _get(url, tries=4):
    import urllib.error
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(tries):
        try:
            raw = urllib.request.urlopen(req, timeout=60).read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404 or attempt == tries - 1:
                raise
            time.sleep(10 * (attempt + 1))
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(10 * (attempt + 1))
    time.sleep(1.5)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _text(cell):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cell)).replace("\xa0", " ")).strip()


def _nation(num, url, year=None):
    """The country of the site's number `num`, from the archived nation page:
    the link the row itself uses (nation.php?year=..&nation=..), else the bare
    one. The archive may hold neither (Ávalos, 2026-10-10): then None - the
    club is looked for without a country - and the miss is cached too."""
    if num in KNOWN:
        return KNOWN[num]
    data = json.load(open(NATIONS_CACHE, encoding="utf-8")) if os.path.exists(NATIONS_CACHE) else {}
    if num not in data:
        stamp = (re.search(r"/web/(\d+)", url) or [None, "2020"])[1]
        data[num] = None
        for q in (["year=%s&nation=%s" % (year, num)] if year else []) + ["nation=%s" % num]:
            try:
                page = _get("https://web.archive.org/web/%s/https://www.foradejogo.net/nation.php?%s"
                            % (stamp, q), tries=1)
            except Exception:
                continue
            m = re.search(r"<title>[^<]*?-\s*([^<]+?)\s*</title>", page)
            if m and "Wayback" not in m.group(0):
                data[num] = m.group(1).strip()
                break
        json.dump(data, open(NATIONS_CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    name = data[num]
    from sources.zerozero import NATIONS            # Portuguese country names
    return NATIONS.get(name, name) if name else None


CODES = {"GR": "Goalkeeper", "DD": "Defender", "DE": "Defender", "DC": "Defender", "D": "Defender",
         "MD": "Midfielder", "MC": "Midfielder", "ME": "Midfielder", "MO": "Midfielder",
         "MDEF": "Midfielder", "MAC": "Midfielder", "M": "Midfielder", "ED": "Forward",
         "EE": "Forward", "PL": "Forward", "A": "Forward"}


def _position(text):
    # a code, spaced: "D D / M C" (first one counts)
    code = re.sub(r"\s+", "", text.split("/")[0]).upper()
    if code in CODES:
        return CODES[code]
    t = text.lower()
    for words, pos in ((("guarda-redes", "goalkeeper"), "Goalkeeper"),
                       (("defesa", "defender", "back", "lateral"), "Defender"),
                       (("trinco", "médio", "midfielder"), "Midfielder"),
                       (("extremo", "winger", "avançado", "ponta", "forward", "striker"), "Forward")):
        if any(w in t for w in words):
            return pos
    return None


def _is_player(page):
    return any(label + ":" in page for label in LABELS["dob"]) and "careertable" in page


def _fetch(url, pid):
    """The player page: the linked capture, or - when the archive saved it
    empty (Alonso's 2022 capture is the toolbar alone) - its other captures of
    the same page, newest first."""
    page = _get(url)
    if _is_player(page):
        return page
    cdx = _get("https://web.archive.org/cdx/search/cdx?url=foradejogo.net/player.php?player=%s*"
               "&output=json&filter=statuscode:200" % pid)
    caps = json.loads(cdx)[1:] if cdx.strip().startswith("[") else []
    for row in sorted(caps, key=lambda r: r[1], reverse=True):
        try:
            page = _get("https://web.archive.org/web/%s/%s" % (row[1], row[2]), tries=2)
        except Exception:
            continue
        if _is_player(page):
            return page
    raise ValueError("foradejogo: no capture of player %s holds his page (the archive saved them "
                     "empty) - use another source" % pid)


def load(url):
    pid = player_id(url)
    path = os.path.join(CACHE_DIR, "foradejogo_%s.html" % pid)
    if not os.path.exists(path) or not _is_player(open(path, encoding="utf-8").read()):
        open(path, "w", encoding="utf-8").write(_fetch(url, pid))
    page = open(path, encoding="utf-8").read()

    # profile: "Label:" then its value, in either language
    lines = [l for l in (_text(x) for x in re.split(r"<[^>]+>", page)) if l]
    def field(key):
        for i, l in enumerate(lines):
            if l.rstrip(":") in LABELS[key] and l.endswith(":") and i + 1 < len(lines):
                return lines[i + 1]
        return ""
    k = next((i for i, l in enumerate(lines) if l.rstrip(":") in LABELS["dob"] and l.endswith(":")),
             None)
    name, full = (lines[k - 2], lines[k - 1]) if k and k >= 2 else (None, None)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", field("dob"))
    dob = (int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None
    place = field("birthplace").split(" - ")[0].strip() or None
    h = re.search(r"(1\d{2})\s*cm", field("height"))
    nat = field("nation")
    from sources.zerozero import NATIONS
    nationality = NATIONS.get(nat, nat) or None

    # career: the visible rows of the career table
    table = page[page.find('class="careertable"'):]
    rows, season = [], None
    for attrs, tr in re.findall(r"<tr([^>]*)>(.*?)</tr>", table, re.S):
        if "display: none" in attrs or "flags/" not in tr:
            continue
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 7:
            continue
        season = _text(tds[0]) or season
        if not season or not re.match(r"\d{4}", season):
            continue
        comp = _text(tds[4])
        esc = re.search(r"escalao=(\d+)", tds[2])
        youth = bool(esc and esc.group(1) != "0") or comp.split(" ")[0].upper() in YOUTH_GRADES
        lm = re.search(r"\((\d)\)", comp) or re.match(r"(I{1,3}|IV|V|VI)\b", comp)
        level = None
        if lm and not youth:
            level = ROMAN.get(int(lm.group(1))) if lm.group(1).isdigit() else lm.group(1)
        g = re.match(r"(\d+)(?:\((\d+)\))?", _text(tds[5]))
        apps = int(g.group(1)) + int(g.group(2) or 0) if g else None
        goals = int(_text(tds[6])) if _text(tds[6]).isdigit() else None
        flag = re.search(r"flags/(\d+)\.png", tds[3])
        rows.append({"season": season, "club": _text(tds[2]), "team_path": "",
                     "apps": apps, "goals": goals if apps is not None else None,
                     "level": level, "youth": youth, "loan": False,
                     "nation": _nation(flag.group(1), url, season[:4]) if flag else None})
    # one row per club and season: a Brazilian year lists the state
    # championship beside the national league (Alonso's Cruzeiro 1998) - the
    # row with a league level wins, the other is dropped; a senior row beats
    # the same club's youth side (Rúben Micael's União 2003/04: II and JUN),
    # and of two youth grades the first is kept (JUN and JUV, 2002/03)
    kept = []
    for r in rows:
        twin = next((k for k in kept if k["season"] == r["season"] and k["club"] == r["club"]), None)
        if twin is None:
            kept.append(r)
        elif r["youth"]:
            continue
        elif twin["youth"] or (r["level"] and (not twin["level"] or twin["apps"] is None)):
            kept[kept.index(twin)] = r
    rows = kept
    return {"name": name, "full": full if full and full != name else None, "dob": dob,
            "birthplace": place, "birth_country": nationality, "nationality": nationality,
            "position": _position(field("position")), "height": int(h.group(1)) if h else None,
            "rows": rows}
