"""zerozero.pt, read from the page the user's own Chrome loaded.

Cloudflare challenges every script and every automated browser, so the page
is read through the Claude extension in the user's Chrome with
`zerozero_extract.js`, and its output cached as `cache/zerozero_<id>.txt`
("key: value" lines, then "season;club;team_path;apps;goals;country" per
career row, newest first; country is the ISO code of the row's flag). The career table carries no division and no club country:
divisions come from FM26's league history, and an unmarked club is
looked for in the country of the legend's target club first.
"""
import os
import re

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")
YOUTH = re.compile(r"\s*\[(?:Jun|Juv|Jun\.|Ini|Inf|S1\d|Sub|U1\d)[^\]]*\]\s*$", re.I)
NATIONS = {"Moçambique": "Mozambique", "Angola": "Angola", "Cabo Verde": "Cape Verde",
           "Brasil": "Brazil", "Espanha": "Spain", "França": "France", "Itália": "Italy",
           "Inglaterra": "England", "Alemanha": "Germany", "Holanda": "The Netherlands",
           "Países Baixos": "The Netherlands", "Bélgica": "Belgium", "Suíça": "Switzerland",
           "Guiné-Bissau": "Guinea-Bissau", "São Tomé e Príncipe": "São Tomé e Príncipe",
           "Argentina": "Argentina", "Uruguai": "Uruguay", "Portugal": "Portugal",
           "Turquia": "Türkiye", "Mali": "Mali", "Senegal": "Senegal", "Guiné": "Guinea",
           "Nigéria": "Nigeria", "Gana": "Ghana", "Camarões": "Cameroon", "Marrocos": "Morocco",
           "Argélia": "Algeria", "Costa do Marfim": "Côte d'Ivoire", "Congo": "Congo",
           "RD Congo": "DR Congo", "Rússia": "Russia", "Ucrânia": "Ukraine", "Polónia": "Poland",
           "Suécia": "Sweden", "Noruega": "Norway", "Dinamarca": "Denmark", "Grécia": "Greece",
           "Croácia": "Croatia", "Sérvia": "Serbia", "Roménia": "Romania", "Bulgária": "Bulgaria",
           "Escócia": "Scotland", "Irlanda": "Republic of Ireland", "País de Gales": "Wales",
           "Estados Unidos": "United States", "Canadá": "Canada", "México": "Mexico",
           "Colômbia": "Colombia", "Venezuela": "Venezuela", "Peru": "Peru", "Chile": "Chile",
           "Paraguai": "Paraguay", "Equador": "Ecuador", "Bolívia": "Bolivia", "Japão": "Japan", "El Salvador": "El Salvador",
           "Venezuela": "Venezuela"}
# the row's flag (span.flag:PT) as ISO 3166 alpha-2, to FM26's nation name;
# zerozero also flags the UK nations as GB-ENG/GB-SCT/GB-WLS/GB-NIR
ISO_NATION = {"PT": "Portugal", "ES": "Spain", "FR": "France", "IT": "Italy", "DE": "Germany",
              "GB-ENG": "England", "GB-SCT": "Scotland", "GB-WLS": "Wales", "GB-NIR": "Northern Ireland",
              "EN": "England", "NL": "The Netherlands", "BE": "Belgium", "CH": "Switzerland",
              "AT": "Austria", "GR": "Greece", "TR": "Türkiye", "BR": "Brazil", "AR": "Argentina",
              "UY": "Uruguay", "PY": "Paraguay", "CL": "Chile", "CO": "Colombia", "PE": "Peru",
              "EC": "Ecuador", "VE": "Venezuela", "BO": "Bolivia", "MX": "Mexico", "US": "United States",
              "CA": "Canada", "MZ": "Mozambique", "AO": "Angola", "CV": "Cape Verde",
              "GW": "Guinea-Bissau", "ST": "São Tomé e Príncipe", "RU": "Russia", "UA": "Ukraine",
              "PL": "Poland", "CZ": "Czech Republic", "SK": "Slovakia", "HU": "Hungary", "RO": "Romania",
              "BG": "Bulgaria", "RS": "Serbia", "HR": "Croatia", "SI": "Slovenia",
              "BA": "Bosnia and Herzegovina", "CY": "Cyprus", "IL": "Israel", "DK": "Denmark",
              "SE": "Sweden", "NO": "Norway", "FI": "Finland", "IS": "Iceland", "IE": "Republic of Ireland",
              "JP": "Japan", "KR": "Korea Republic", "CN": "China PR", "QA": "Qatar",
              "SA": "Saudi Arabia", "AE": "United Arab Emirates", "KW": "Kuwait", "AU": "Australia",
              "ZA": "South Africa", "NG": "Nigeria", "GH": "Ghana", "MA": "Morocco", "TN": "Tunisia",
              "DZ": "Algeria", "EG": "Egypt", "CM": "Cameroon", "CI": "Côte d'Ivoire", "SN": "Senegal",
              "SV": "El Salvador", "HN": "Honduras", "GT": "Guatemala", "CR": "Costa Rica",
              "LU": "Luxembourg", "MT": "Malta", "AD": "Andorra", "MO": "Macau", "HK": "Hong Kong"}
POSITIONS = {"guarda-redes": "Goalkeeper", "defesa": "Defender", "médio": "Midfielder",
             "avançado": "Forward"}


def _height(v):
    """"1,85 m" / "185 cm" -> 185."""
    m = re.search(r"(\d)[.,](\d{2})", v or "")
    if m:
        return int(m.group(1)) * 100 + int(m.group(2))
    m = re.search(r"(1\d{2})", v or "")
    return int(m.group(1)) if m else None


def player_id(url):
    m = re.search(r"/(?:jogador|joueur|player|jugador|giocatore)/[^/]+/(\d+)", url)
    return m.group(1) if m else None


def cache_path(url):
    return os.path.join(CACHE_DIR, "zerozero_%s.txt" % player_id(url))


def load(url):
    """The cached page, parsed; None when it was not fetched yet."""
    path = cache_path(url)
    if not os.path.exists(path):
        return None
    info, rows = {}, []
    for line in open(path, encoding="utf-8").read().splitlines():
        if re.match(r"^\d{4}", line):
            season, club, team_path, apps, goals, flag = (line.split(";") + [""] * 6)[:6]
            if re.search(r"\[(?:Veteranos|Futsal|Praia|Fem)", club, re.I):
                continue            # veterans, futsal, beach: not his football career
            # "CD Tondela(E) [Académica OAF]": on loan (empréstimo) at Tondela
            # from Académica, the owner in the brackets
            loan = bool(re.search(r"\(E\)", club))
            if loan:
                club = re.sub(r"\s*\(E\).*$", "", club)
            club = re.sub(r"\s*\((?:Extinto|Extinta)\)", "", club)   # "FC Felgueiras (Extinto)"
            youth = bool(YOUTH.search(club))
            # "Benfica [B]" is the club's B side, a senior team of its own
            club = re.sub(r"\s*\[B\]\s*$", " B", club)
            num = lambda v: int(v) if v.strip().isdigit() else None
            rows.append({"season": season, "club": YOUTH.sub("", club).strip(),
                         "team_path": team_path, "apps": num(apps), "goals": num(goals),
                         "youth": youth, "loan": loan,
                         "nation": ISO_NATION.get(flag.upper()) if flag else None})
        elif ":" in line:
            k, v = line.split(":", 1)
            info[k] = v.strip()
    dob = None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", info.get("dob", ""))
    if m:
        dob = (int(m.group(3)), int(m.group(2)), int(m.group(1)))
    place = re.search(r"\(([^)]+)\)", info.get("birthplace", ""))
    country = info.get("birthplace", "").split("(")[0].strip()
    # a current player's page title carries the season ("Anthony Correia :: 2026/2027")
    return {"name": re.sub(r"\s*::.*$", "", info.get("name") or "") or None, "full": info.get("full") or None, "dob": dob,
            "nation": NATIONS.get(info.get("nationality"), info.get("nationality")),
            "birthplace": place.group(1) if place else None,
            "birth_country": NATIONS.get(country, country) or None,
            "position": POSITIONS.get((info.get("position") or "").lower()),
            "height": _height(info.get("height")),
            "rows": rows}
