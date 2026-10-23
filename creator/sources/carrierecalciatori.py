"""carrierecalciatori.it: plain HTTP, no Cloudflare (checked 2026-10-09).

A player page (/it/giocatori/<id>-<Name>) is one table - Anno, Squadra,
Categoria, Presenze, Goal fatti - newest first, one row per season and club.
Anno is the season's START year (Gattuso: Perugia 1995 Serie B = 1995/96,
1996 Serie A = 1996/97; Milan 1999-2011 = 1999/00-2011/12). A foreign club
and its league end in an Italian country code ("Glasgow Rangers SCO",
"Sion SVI"). No loans, no youth sides.

A panel beside the table holds the profile: nationality, role, birth date
and place of birth ("Taglio Di Po Ro": town, then its province). No height,
no full name.

Returns the shape sources/zerozero.load does, so build.gather_profile reads
it on the same path.
"""
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")
HOST = "https://www.carrierecalciatori.it"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
DELAY = 1.5

# the site's country codes (Italian abbreviations) -> FM26 nation names
COUNTRIES = {"SVI": "Switzerland", "SCO": "Scotland", "ING": "England", "GAL": "Wales",
             "IRL": "Republic of Ireland", "NIR": "Northern Ireland", "SPA": "Spain",
             "FRA": "France", "GER": "Germany", "POR": "Portugal", "OLA": "The Netherlands",
             "BEL": "Belgium", "GRE": "Greece", "TUR": "Türkiye", "RUS": "Russia",
             "UCR": "Ukraine", "POL": "Poland", "CRO": "Croatia", "SER": "Serbia",
             "ROM": "Romania", "BUL": "Bulgaria", "UNG": "Hungary", "CEC": "Czechia",
             "SLO": "Slovenia", "SLK": "Slovakia", "AUT": "Austria", "DAN": "Denmark",
             "SVE": "Sweden", "NOR": "Norway", "FIN": "Finland", "USA":
             "The United States of America", "CAN": "Canada", "MES": "Mexico",
             "ARG": "Argentina", "BRA": "Brazil", "URU": "Uruguay", "CIL": "Chile",
             "PAR": "Paraguay", "COL": "Colombia", "PER": "Peru", "ECU": "Ecuador",
             "GIA": "Japan", "CIN": "China PR", "QAT": "Qatar", "ARS": "Saudi Arabia",
             "EAU": "United Arab Emirates", "AUS": "Australia", "CIP": "Cyprus",
             "MLT": "Malta", "ISR": "Israel", "SMR": "San Marino", "ALB": "Albania",
             "BOS": "Bosnia and Herzegovina", "MAC": "North Macedonia", "MNE": "Montenegro",
             "LUS": "Luxembourg", "LUX": "Luxembourg", "KOR": "Korea Republic",
             "IND": "India", "THA": "Thailand", "EGI": "Egypt", "MAR": "Morocco",
             "TUN": "Tunisia", "SUD": "South Africa"}
ROLES = {"portiere": "Goalkeeper", "difensore": "Defender", "centrocampista": "Midfielder",
         "attaccante": "Forward"}


def player_id(url):
    m = re.search(r"/giocatori/(\d+)-", urllib.parse.unquote(url))
    return m.group(1) if m else None


def _get(url, data=None):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data else None,
                                 headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest",
                                          "Referer": HOST + "/it/calciatori"})
    out = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    time.sleep(DELAY)
    return out


def _cached(name, fetch):
    path = os.path.join(CACHE_DIR, name)
    if not os.path.exists(path):
        open(path, "w", encoding="utf-8").write(fetch())
    return open(path, encoding="utf-8").read()


def _cells(row_html):
    return [html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
            for t in re.findall(r"<td>(.*?)</td>", row_html, re.S)]


def level(category, season):
    """The source's level of an Italian league that season (only a fallback:
    divisions come from FM26's league history). Serie C split into C1/C2 in
    1978 and became Lega Pro, then Serie C again; Serie D sat below them."""
    c = category.lower()
    if c == "serie a":
        return "I"
    if c == "serie b":
        return "II"
    if c in ("serie c", "serie c1", "lega pro", "lega pro prima divisione", "lega pro 1"):
        return "III"
    if c in ("serie c2", "lega pro seconda divisione", "lega pro 2"):
        return "IV"
    if c in ("serie d", "interregionale", "campionato nazionale dilettanti"):
        return "IV"                 # Serie D is Serie D, whatever tier it was then
    # the amateur leagues below Serie C/D (Dilettanti 1930s, Promozione):
    # their modern equivalent is Serie D, the lowest level levels.json maps
    # (user, 2026-10-09: pre-war lower seasons take the modern equivalent)
    if c in ("dilettanti", "promozione", "prima divisione", "seconda divisione",
             "prima categoria", "eccellenza"):
        return "IV"
    return None


def _split_country(name):
    """("Glasgow Rangers", "Scotland") from "Glasgow Rangers SCO"; an
    Italian club has no code."""
    m = re.match(r"^(.*\S)\s+([A-Z]{3})$", name)
    if m:
        # a code not in the table: the club is looked for anywhere
        return m.group(1), COUNTRIES.get(m.group(2))
    return name, "Italy"


def load(url):
    pid = player_id(url)
    page = _cached("carrierecalciatori_%s.html" % pid,
                   lambda: _get(HOST + "/it/giocatori/" + urllib.parse.quote(
                       urllib.parse.unquote(url.split("/giocatori/", 1)[1]))))
    rows = []
    for tr in re.findall(r"<tr[^>]*onclick=\"location.href='/it/statistiche/[^>]*>(.*?)</tr>",
                         page, re.S):
        td = _cells(tr)
        if len(td) < 5 or not re.match(r"\d{4}$", td[0]):
            continue
        y = int(td[0])
        club, nation = _split_country(td[1])
        num = lambda t: int(t) if t.isdigit() else None
        rows.append({"season": "%d/%02d" % (y, (y + 1) % 100), "club": club, "team_path": "",
                     "apps": num(td[3]), "goals": num(td[4]),
                     "level": level(td[2], y) if nation == "Italy" else None,
                     "youth": False, "loan": False, "nation": nation})
    # the profile panel beside the table: "Nazionalità ITA, Ruolo Portiere,
    # Data di nascita 09/07/1939, Luogo di nascita Taglio Di Po Ro" - the
    # town ends in its province (Ro = Rovigo), or a country code abroad
    name = re.sub(r"\s+", " ", urllib.parse.unquote(url).split("/giocatori/", 1)[1].split("-", 1)[1])
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    field = lambda label: (re.search(label + r" (.+?) (?=Nazionalit|Ruolo|Presenze|Gol fatti|"
                                     r"Data di nascita|Luogo di nascita|Campionato|$)", text)
                           or [None, None])[1]
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", field("Data di nascita") or "")
    dob = (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
    role = ROLES.get((field("Ruolo") or "").lower())
    place, born_in = (field("Luogo di nascita") or "").strip(), None
    pm = re.match(r"^(.*\S)\s+([A-Za-z]{2,3})$", place)
    if pm and len(pm.group(2)) == 2:
        place, born_in = pm.group(1), "Italy"           # an Italian province
    elif pm and pm.group(2).upper() in COUNTRIES:
        place, born_in = pm.group(1), COUNTRIES[pm.group(2).upper()]
    return {"name": name, "full": None, "dob": dob, "birthplace": place or None,
            "birth_country": born_in,
            "position": role, "height": None, "rows": rows}
