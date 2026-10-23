"""bdfutbol.com, read from the page the user's own Chrome loaded (Cloudflare
refuses scripts), through `bdfutbol_extract.js`, cached as
`cache/bdfutbol_<id>.txt`: "key: value" lines, then
"season;team;team_path;country;division;age;games;goals" per row, oldest
first. bdfutbol lists the leagues in its own database (Spain); the country
cell is empty for a Spanish club. A two-club season is two rows, in order.
"-" in the goals column means no goals (a 0 when he played); games are
always a number.
"""
import os
import re

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")
LEVELS = {"1ª": "I", "2ª": "II", "2ªB": "III", "3ª": "IV", "1ª RFEF": "III", "2ª RFEF": "IV",
          "3ª RFEF": "V"}
POSITIONS = {"portero": "Goalkeeper", "defensa": "Defender", "centrocampista": "Midfielder",
             "medio": "Midfielder", "delantero": "Forward"}
COUNTRIES = {"España": "Spain", "Portugal": "Portugal", "Francia": "France", "Italia": "Italy",
             "Inglaterra": "England", "Alemania": "Germany", "Argentina": "Argentina",
             "Brasil": "Brazil", "Uruguay": "Uruguay", "México": "Mexico", "Holanda": "The Netherlands",
             "Países Bajos": "The Netherlands", "Bélgica": "Belgium", "Escocia": "Scotland",
             "Suiza": "Switzerland", "Grecia": "Greece", "Turquía": "Türkiye", "Estados Unidos":
             "United States", "Chile": "Chile", "Paraguay": "Paraguay", "Colombia": "Colombia",
             "Perú": "Peru", "Venezuela": "Venezuela", "Marruecos": "Morocco", "Camerún": "Cameroon",
             "Nigeria": "Nigeria", "Japón": "Japan", "China": "China PR", "Catar": "Qatar"}


def player_id(url):
    m = re.search(r"/j/(j\d+)\.html", url)
    return m.group(1) if m else None


def cache_path(url):
    return os.path.join(CACHE_DIR, "bdfutbol_%s.txt" % player_id(url))


def load(url):
    """The cached page, parsed into the shape sources/zerozero.load returns;
    None when it was not fetched yet."""
    path = cache_path(url)
    if not os.path.exists(path):
        return None
    info, rows = {}, []
    for line in open(path, encoding="utf-8").read().splitlines():
        if re.match(r"^\d{4}", line):
            season, team, team_path, country, div, age, games, goals = (line.split(";") + [""] * 8)[:8]
            apps = int(games) if games.strip().isdigit() else None
            gls = int(goals) if goals.strip().isdigit() else (0 if apps is not None else None)
            rows.append({"season": season.replace("-", "/"), "club": team.strip(),
                         "team_path": team_path, "apps": apps, "goals": gls,
                         "level": LEVELS.get(div.strip()), "youth": False, "loan": False,
                         "nation": COUNTRIES.get(country.strip(), country.strip()) or "Spain"})
        elif ":" in line:
            k, v = line.split(":", 1)
            info[k] = v.strip()
    # the labels and values read are Spanish; another language's page has none
    if not info.get("url", "/es/").startswith("/es/"):
        raise ValueError("%s was saved from %s, not the Spanish page: open /es/%s and save it again"
                         % (os.path.basename(path), info["url"], info["url"].split("/", 2)[-1]))
    dob = None
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", info.get("dob", ""))
    if m:
        dob = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    h = re.search(r"(1\d{2})\s*cm", info.get("height", ""))
    return {"name": info.get("name"), "full": info.get("full") or None, "dob": dob,
            "birthplace": re.sub(r"\s*\([^)]*\)\s*$", "", info.get("birthplace", "")) or None,
            "birth_country": COUNTRIES.get(info.get("birth_country"), info.get("birth_country")) or None,
            "position": POSITIONS.get((info.get("position") or "").lower()),
            "height": int(h.group(1)) if h else None, "rows": rows}
