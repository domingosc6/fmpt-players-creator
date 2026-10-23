"""Wikipedia (it/en) infobox parser: youth clubs, loan markers, half-season
stays, and a missing full name. Read via the MediaWiki API `action=parse`,
`prop=wikitext`.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")
DELAY = 2.5


def _open(req):
    """The API's JSON; a 429 (too many requests) waits as the server asks,
    or 10 s more each time, and tries again, five times at most."""
    import urllib.error
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(req, timeout=30))
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 4:
                raise
            time.sleep(int(e.headers.get("Retry-After") or 0) or 10 * (attempt + 1))


def fetch_wikitext(lang, page, cache_name):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, cache_name)
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    url = ("https://%s.wikipedia.org/w/api.php?action=parse&page=%s&prop=wikitext"
           "&format=json&formatversion=2&redirects=1" % (lang, urllib.parse.quote(page)))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = _open(req)
    json.dump(data, open(path, "w", encoding="utf-8"))
    time.sleep(DELAY)
    return data


def _split_top_level(line):
    """Split a wikitext row on "|", ignoring pipes nested inside {{...}} or
    [[...]] (a {{Bandiera|NC}} flag template, or a [[link|text]])."""
    parts, cur, depth = [], "", 0
    i = 0
    while i < len(line):
        two = line[i:i + 2]
        if two in ("{{", "[["):
            depth += 1
            cur += two
            i += 2
            continue
        if two in ("}}", "]]"):
            depth -= 1
            cur += two
            i += 2
            continue
        if line[i] == "|" and depth == 0:
            parts.append(cur)
            cur = ""
            i += 1
            continue
        cur += line[i]
        i += 1
    parts.append(cur)
    return parts


def _clean_wikitext(s):
    s = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"\{\{Bandiera\|[^}]*\}\}", "", s)
    # it.wikipedia's club template: "{{Calcio Pisa|G}}" is Pisa
    s = re.sub(r"\{\{\s*Calcio\s+([^|}]+)(?:\|[^}]*)?\}\}", r"\1", s)
    s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\{\{[^}]*\}\}", "", s)  # any remaining template (NazU, Naz...)
    return s.strip()


def _carriera_rows(block):
    """One {{Carriera sportivo}} template body -> [(years, club, loan, stats)].
    `years` is the raw wikitext range ("1996-1998", "1999"); `loan` is True when
    the row starts with the arrow marker "→"."""
    out = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        body = line[1:]
        if not re.match(r"\d{4}", body):
            continue          # a parameter line ("sport = calcio"), not a row
        parts = _split_top_level(body)
        if len(parts) < 2:
            continue
        years = parts[0].strip()
        # it.wikipedia's club template: "{{Calcio Pisa|G}}" is Pisa
        club_raw = re.sub(r"\{\{\s*Calcio\s+([^|}]+)(?:\|[^}]*)?\}\}", r"\1", parts[1]).strip()
        stats = _clean_wikitext(parts[2]) if len(parts) > 2 else ""
        loan = club_raw.lstrip().startswith("→")
        club = _clean_wikitext(club_raw.lstrip("→").strip())
        if not years or not club:
            continue
        out.append((years, club, loan, stats))
    return out


def _template(wikitext, name):
    """The whole `{{name ... }}` template, by brace counting; '' if absent."""
    m = re.search(r"\{\{\s*" + re.escape(name) + r"\s*\n?\|", wikitext)
    if not m:
        return ""
    depth, i = 0, m.start()
    while i < len(wikitext):
        if wikitext[i:i + 2] == "{{":
            depth += 1
            i += 2
        elif wikitext[i:i + 2] == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return wikitext[m.start():i]
        else:
            i += 1
    return wikitext[m.start():]


def _template_block(wikitext, field):
    """The wikitext of a `|field = {{Carriera sportivo ... }}` value inside the
    outer {{Sportivo infobox, by brace counting (fields can nest templates)."""
    # any spacing: "|Squadre = {{Carriera..." or "|Squadre=" + newline (Merlo)
    m = re.search(r"\|\s*" + re.escape(field) + r"\s*=\s*\{\{\s*Carriera sportivo", wikitext)
    if not m:
        return None
    start = wikitext.index("{{", m.start())
    depth = 0
    i = start
    while i < len(wikitext):
        if wikitext[i:i + 2] == "{{":
            depth += 1
            i += 2
            continue
        if wikitext[i:i + 2] == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return wikitext[start:i]
            continue
        i += 1
    return None


def infobox(wikitext):
    """Sportivo infobox fields the build needs: dob (day,month,year), full name
    parts, youth clubs, senior clubs (with loan flags), caps rows."""
    out = {"dob": None, "nome": None, "cognome": None, "youth": [], "senior": [], "caps": []}
    m = re.search(r"\|GiornoMeseNascita\s*=\s*([^\n|]+)", wikitext)
    y = re.search(r"\|AnnoNascita\s*=\s*(\d+)", wikitext)
    if m and y:
        mm = m.group(1).strip()
        day_m = re.match(r"(\d+)\s+(\w+)", mm)
        MONTHS = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5,
                  "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10,
                  "novembre": 11, "dicembre": 12}
        if day_m and day_m.group(2).lower() in MONTHS:
            out["dob"] = (int(day_m.group(1)), MONTHS[day_m.group(2).lower()], int(y.group(1)))
    # names come from {{Bio}}: the {{Sportivo}} box has a |Nome too, holding
    # the display name ("Dario Dainelli"), and it comes first
    bio = _template(wikitext, "Bio")
    nm = re.search(r"\|Nome\s*=\s*([^\n|]+)", bio)
    cm = re.search(r"\|Cognome\s*=\s*([^\n|]+)", bio)
    lm = re.search(r"\|LuogoNascita\s*=\s*([^\n|]+)", bio)
    out["birthplace"] = lm.group(1).strip().strip("[]") if lm and lm.group(1).strip() else None
    if nm:
        out["nome"] = nm.group(1).strip()
    if cm:
        out["cognome"] = cm.group(1).strip()
    youth_block = _template_block(wikitext, "SquadreGiovanili")
    if youth_block:
        out["youth"] = _carriera_rows(youth_block)
    senior_block = _template_block(wikitext, "Squadre")
    if senior_block:
        out["senior"] = _carriera_rows(senior_block)
    caps_block = _template_block(wikitext, "SquadreNazionali")
    if caps_block:
        out["caps"] = _carriera_rows(caps_block)
    return out


def season_years(years_field):
    """"1996-1998" -> [1996, 1997]; "1999" -> [1999]; "1994-1995" -> [1994].
    An en dash counts as the hyphen (en/pt pages write "1984–1987")."""
    years_field = years_field.replace("\u2013", "-").replace("\u2014", "-")
    m = re.match(r"(\d{4})\s*(?:-\s*(\d{4}))?", years_field)
    if not m:
        return []
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else start + 1
    return list(range(start, end))


# ------------------------------------------------- any language, by URL -----

FLAG_NATION = {"PRT": "Portugal", "ESP": "Spain", "FRA": "France", "ITA": "Italy",
               "ENG": "England", "SCO": "Scotland", "WAL": "Wales", "GER": "Germany",
               "DEU": "Germany", "NED": "The Netherlands", "BEL": "Belgium", "SUI": "Switzerland",
               "AUT": "Austria", "GRE": "Greece", "TUR": "Türkiye", "BRA": "Brazil",
               "ARG": "Argentina", "JPN": "Japan", "USA": "United States", "MEX": "Mexico",
               "RUS": "Russia", "UKR": "Ukraine", "CYP": "Cyprus", "QAT": "Qatar",
               "KSA": "Saudi Arabia", "UAE": "United Arab Emirates", "CHN": "China PR",
               "ROU": "Romania", "POL": "Poland", "SWE": "Sweden", "NOR": "Norway",
               "DEN": "Denmark", "SCG": "Serbia", "SRB": "Serbia", "CRO": "Croatia",
               "BUL": "Bulgaria", "HUN": "Hungary", "CZE": "Czech Republic", "ANG": "Angola",
               "MOZ": "Mozambique", "CPV": "Cape Verde", "IRL": "Republic of Ireland",
               "ISR": "Israel", "KOR": "Korea Republic", "CAN": "Canada"}


ALT_NAMES = {}      # display name -> link target, filled by _club_cell


def from_url(url):
    """(language, page title) of a Wikipedia article link."""
    m = re.match(r"https?://(\w+)(?:\.m)?\.wikipedia\.org/wiki/([^?#]+)", url.strip())
    if not m:
        return None, None
    return m.group(1), urllib.parse.unquote(m.group(2))


def fetch_url(url):
    lang, title = from_url(url)
    slug = re.sub(r"\W+", "_", title.lower()).strip("_")
    data = fetch_wikitext(lang, title, "wiki_%s_%s.json" % (lang, slug))
    return lang, data["parse"]["wikitext"]


INFOBOX_LANGS = ("en", "pt", "it")      # the languages infobox_any reads


def langlink(lang, title, to):
    """The title of the same article in language `to`, or None."""
    return langlinks(lang, title).get(to)


def langlinks(lang, title):
    """{language: title} of the same article in every other language; {}
    when there is no such article."""
    slug = re.sub(r"\W+", "_", title.lower()).strip("_")
    path = os.path.join(CACHE_DIR, "wiki_links_%s_%s.json" % (lang, slug))
    if os.path.exists(path):
        links = json.load(open(path, encoding="utf-8"))
    else:
        url = ("https://%s.wikipedia.org/w/api.php?action=parse&page=%s&prop=langlinks"
               "&format=json&formatversion=2&redirects=1" % (lang, urllib.parse.quote(title)))
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        data = _open(req)
        links = {l["lang"]: l["title"] for l in (data.get("parse") or {}).get("langlinks", [])}
        json.dump(links, open(path, "w", encoding="utf-8"))
        time.sleep(DELAY)
    return links


def read_url(url):
    """(box, note) for an article link. An article in a language with no
    infobox reader (eu: the infobox is drawn from Wikidata, not the
    wikitext) takes its profile and stays from the English article; its own
    season table, when it has one, still gives the rows."""
    lang, wt = fetch_url(url)
    if lang in INFOBOX_LANGS:
        return infobox_any(wt, lang), None
    title = langlink(lang, from_url(url)[1], "en")
    if not title:
        box = infobox_any(wt, lang)
        return box, "Wikipedia (%s) has no English article to read the profile from." % lang
    box = infobox_any(fetch_url("https://en.wikipedia.org/wiki/" + title)[1], "en")
    own = career_table(wt)
    if own:
        box["table"] = own
    return box, ("Wikipedia (%s): profile and stays from the English article%s."
                 % (lang, ", seasons from the %s season table" % lang if own else ""))


def _field(wt, name):
    m = re.search(r"\|\s*" + re.escape(name) + r"\s*=\s*(.*?)(?=\n\s*\||\|\s*\w+\s*=|\n\}\})", wt, re.S)
    return m.group(1).strip() if m else ""


def _club_cell(raw):
    """(club name, loan, nation) from one infobox club cell. "→" and "(loan)" /
    "(emp.)" mark a loan; a pt flag template ({{ESPb}}) names the country."""
    flag = (re.search(r"\{\{([A-Z]{3})b?\}\}", raw)
            or re.search(r"\{\{Bandiera\|([A-Z]{3})\}\}", raw))      # it: {{Bandiera|QAT}}
    # a second line under the name holds its flag (eu: "'''[[Real Union]]'''<br /><small>...")
    raw = re.split(r"<br\s*/?>", raw)[0]
    loan = "→" in raw or bool(re.search(r"\((?:loan|emp\.?|empr[ée]stimo)\)", raw, re.I))
    name = _clean_wikitext(raw.replace("→", ""))
    link = re.search(r"\[\[([^\]|#]+)", raw)
    if link:
        # the link target names the club in full ("Clube Desportivo Montijo"
        # behind "Montijo"): kept as the fallback when the short name finds
        # nothing; a "(...)" disambiguation is not part of the name
        ALT_NAMES[re.sub(r"\((?:loan|emp\.?|empr[ée]stimo)\)", "", name, flags=re.I).strip(" '")] = \
            re.sub(r"\s*\([^)]*\)\s*$", "", link.group(1))
    name = re.sub(r"\((?:loan|emp\.?|empr[ée]stimo)\)", "", name, flags=re.I).strip(" '")
    return name, loan, FLAG_NATION.get(flag.group(1)) if flag else None


def _dob(wt):
    m = re.search(r"\{\{\s*(?:Birth date(?: and age)?|birth date(?: and age)?|dni|dnibr|"
                  r"Data de nascimento e idade|nascimento e idade)"
                  # named options before the numbers ("|df=yes|1981|5|21")
                  r"(?:\s*\|\s*[a-z]+\s*=\s*[^|}]*)*"
                  r"\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)", wt)
    if not m:
        return None
    a, b, c = (int(x) for x in m.groups())
    return (c, b, a) if a > 31 else (a, b, c)        # en is y|m|d, pt dni is d|m|y


def infobox_generic(wikitext, lang):
    """en {{Infobox football biography}} and pt {{Info/Futebolista}} into the
    shape `infobox` returns for it: youth/senior rows (years, club, loan,
    stats) - here with the club's NATION as a fifth item when a flag says so -
    plus dob, full name and birthplace."""
    out = {"dob": _dob(wikitext), "nome": None, "cognome": None, "youth": [], "senior": [],
           "caps": [], "full": None, "birthplace": None}
    # a <ref> inside a field carries its own "|url=..." and would end it early
    wikitext = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", wikitext, flags=re.S)
    if lang == "pt":
        box = _template(wikitext, "Info/Futebolista")
        out["full"] = _clean_wikitext(_field(box, "nomecompleto")) or None
        out["birthplace"] = (_clean_wikitext(_field(box, "cidadenatal")).split(",")[0].strip() or None)
        out["birth_country"] = _clean_wikitext(_field(box, "paisnatal")) or None
        pairs = (("jovemanos", "jovemclubes", None, "youth"), ("ano", "clubes", "jogos(golos)", "senior"))
        for yk, ck, sk, key in pairs:
            ys = re.split(r"<br\s*/?>", _field(box, yk))
            cs = re.split(r"<br\s*/?>", _field(box, ck))
            ss = re.split(r"<br\s*/?>", _field(box, sk)) if sk else []
            for i, (y, cl) in enumerate(zip(ys, cs)):
                y = _clean_wikitext(y)
                if not re.match(r"\d{4}", y):
                    continue
                name, loan, nat = _club_cell(cl)
                stats = _clean_wikitext(ss[i]) if i < len(ss) else ""
                out[key].append((y, name, loan, stats, nat))
    else:
        box = _template(wikitext, "Infobox football biography")
        out["full"] = (_clean_wikitext(_field(box, "full_name")) or
                       _clean_wikitext(_field(box, "fullname")) or None)
        place = _clean_wikitext(_field(box, "birth_place"))
        out["birthplace"] = place.split(",")[0].strip() or None
        # "Barra Mansa, Rio de Janeiro, Brazil": the country is the last part
        out["birth_country"] = place.split(",")[-1].strip() if "," in place else None
        for prefix, key in (("youth", "youth"), ("", "senior")):
            for i in range(1, 40):
                y = _clean_wikitext(_field(box, "%syears%d" % (prefix, i)))
                cl = _field(box, "%sclubs%d" % (prefix, i))
                if not y or not cl:
                    continue
                name, loan, nat = _club_cell(cl)
                stats = ""
                if not prefix:
                    stats = "%s (%s)" % (_clean_wikitext(_field(box, "caps%d" % i)),
                                         _clean_wikitext(_field(box, "goals%d" % i)))
                out[key].append((y, name, loan, stats, nat))
    return out


def infobox_any(wikitext, lang):
    if lang == "it":
        box = infobox(wikitext)
        box["senior"] = [r + (None,) for r in box["senior"]]
        box["youth"] = [r + (None,) for r in box["youth"]]
        box.setdefault("full", None)
    else:
        box = infobox_generic(wikitext, lang)
    box["table"] = career_table(wikitext)
    box["height"] = height_cm(wikitext)
    return box


# ------------------------------------------------- career statistics table --

STATS_HEADING = re.compile(r"^=+\s*(?:Career statistics|Club statistics|Estatísticas|"
                           r"Estatísticas na carreira|Statistiche|Statistics|Ibilbidea)\s*=+\s*$",
                           re.I | re.M)
SPAN = re.compile(r"^\s*((?:\s*(?:rowspan|colspan|style|class|v?align|width|bgcolor)\s*=\s*"
                  r"\"?[^\"|]*\"?)+)\s*\|(?!\|)(.*)$", re.I | re.S)


def _cells(line):
    """One wikitable line ("|a||b" or "!a!!b") into its cells, the "||"/"!!"
    separators only counted outside [[...]] and {{...}}."""
    body, out, cur, depth, i = line[1:], [], "", 0, 0
    if line[:2] in ("||", "!!"):
        body = line[2:]                    # "|| 2004 || ..." (it.wikipedia)
    while i < len(body):
        two = body[i:i + 2]
        if two in ("[[", "{{"):
            depth += 1; cur += two; i += 2; continue
        if two in ("]]", "}}"):
            depth -= 1; cur += two; i += 2; continue
        if depth == 0 and two in ("||", "!!"):
            out.append(cur); cur = ""; i += 2; continue
        cur += body[i]; i += 1
    out.append(cur)
    return out


def wikitable(block):
    """Rows of a wikitable as lists of (is_header, text), rowspan and colspan
    expanded the way a browser lays them out."""
    rows, carry = [], {}                          # column -> [rows left, cell]
    for chunk in re.split(r"\n\|-[^\n]*", block):
        raw = []
        for line in chunk.split("\n"):
            st = line.strip()
            if not st or st.startswith(("{|", "|}", "|+")):
                continue
            if st[0] in "|!":
                raw.extend((st[0] == "!", c) for c in _cells(st))
            elif raw:
                raw[-1] = (raw[-1][0], raw[-1][1] + " " + st)
        if not raw:
            continue
        row, col = [], 0
        cells = list(raw)
        while cells or col in carry:
            if col in carry:
                left, cell = carry[col]
                row.append(cell)
                carry[col][0] -= 1
                if carry[col][0] == 0:
                    del carry[col]
                col += 1
                continue
            hdr, text = cells.pop(0)
            m = SPAN.match(text)
            attrs, text = (m.group(1), m.group(2)) if m else ("", text)
            rs = re.search(r"rowspan\s*=\s*\"?(\d+)", attrs)
            cs = re.search(r"colspan\s*=\s*\"?(\d+)", attrs)
            for k in range(int(cs.group(1)) if cs else 1):
                row.append((hdr, text.strip()))
                if rs and int(rs.group(1)) > 1:
                    carry[col] = [int(rs.group(1)) - 1, (hdr, text.strip())]
                col += 1
        rows.append(row)
    return rows


SEASON_HEAD = re.compile(r"^(season|stagione|temporada|época|epoca|saison|denboraldia|anno)$")
CLUB_HEAD = re.compile(r"^(club|squadra|team|clube|equipo|equipa|taldea|verein)$")
LEAGUE_HEAD = re.compile(r"^(league|campionato|liga|campeonato|championnat|national league)$")
APPS_HEAD = re.compile(r"^(apps|app|pres|presenze|jogos|j|pj|jp|matches|partite|games)$")
GOALS_HEAD = re.compile(r"^(goals|gls|reti|gol|gols|golos|g|goles)$")
DIV_HEAD = re.compile(r"^(division|divisione|divisão|comp|competition|maila|categoria|league)$")


def _columns(rows):
    """(season, club, division, apps, goals) column positions from the
    table's header rows, the league group's own Apps/Goals only (user,
    2026-10-09: only the Campionato columns) - or None when the header does
    not say."""
    heads = []                                # the header rows at the top only
    for r in rows:                            # (a "!Totale Sorrento" row is not one)
        if not (r and all(h for h, _ in r)):
            break
        heads.append(r)
    if not heads:
        return None
    width = max(len(r) for r in heads)
    label = lambda r, i: _clean_wikitext(r[i][1]).lower().strip() if i < len(r) else ""
    cols = {}
    for i in range(width):
        parts = [label(r, i) for r in heads]
        if "season" not in cols and any(SEASON_HEAD.match(x) for x in parts):
            cols["season"] = i
        elif "club" not in cols and any(CLUB_HEAD.match(x) for x in parts):
            cols["club"] = i
        elif any(LEAGUE_HEAD.match(x) for x in parts[:-1]) or (
                len(parts) == 1 and LEAGUE_HEAD.match(parts[0])):
            sub = parts[-1]
            if APPS_HEAD.match(sub) and "apps" not in cols:
                cols["apps"] = i
            elif GOALS_HEAD.match(sub) and "goals" not in cols:
                cols["goals"] = i
            elif DIV_HEAD.match(sub) and "division" not in cols:
                cols["division"] = i
        elif "division" not in cols and any(DIV_HEAD.match(x) for x in parts):
            cols["division"] = i              # eu "Maila", a column of its own
    if {"season", "club", "apps"} <= set(cols):
        return cols
    return None


def career_table(wikitext):
    """Season rows of the article's club career statistics table: dicts of
    season (start year), club, loan, nation, division, apps, goals - the
    LEAGUE's apps and goals only, cups and totals left out. [] when the
    article has none. Columns are found by the header (en: Club, Season;
    it: Stagione, Squadra; eu: Taldea, Maila, Denboraldia), else by the en
    layout. The table gives one row per season and club, so it replaces the
    infobox's per-stay totals wherever it reaches."""
    m = STATS_HEADING.search(wikitext)
    if not m:
        return []
    start = wikitext.find("{|", m.end())
    end = wikitext.find("\n|}", start)
    if start < 0 or end < 0:
        return []
    rows = wikitable(wikitext[start:end])
    cols = _columns(rows)
    if cols is None:
        head = [" ".join(_clean_wikitext(t).lower() for h, t in r) for r in rows if all(h for h, _ in r)]
        has_div = any(re.search(r"\b(division|divisão|divisione|league|liga|campeonato)\b.*\bapps\b|"
                                r"\bdivision\b", h) for h in head[1:2] or head)
        cols = {"club": 0, "season": 1, "apps": 3 if has_div else 2, "goals": 4 if has_div else 3}
        if has_div:
            cols["division"] = 2
    num = lambda t: int(re.match(r"\d+", _clean_wikitext(t)).group(0)) \
        if re.match(r"\d+", _clean_wikitext(t)) else None
    out = []
    for r in rows:
        if len(r) <= max(cols.values()) or any(r[i][0] for i in (cols["season"], cols["club"])):
            continue                                  # header or a total row
        sm = re.match(r"(\d{4})", _clean_wikitext(r[cols["season"]][1]).replace("\u2013", "-"))
        if not sm:
            continue
        name, loan, nat = _club_cell(r[cols["club"]][1])
        if not name:
            continue
        out.append({"season": int(sm.group(1)), "club": name, "loan": loan, "nation": nat,
                    "division": _clean_wikitext(r[cols["division"]][1]) if "division" in cols else None,
                    "apps": num(r[cols["apps"]][1]),
                    "goals": num(r[cols["goals"]][1]) if "goals" in cols else None})
    return out


NATION_LANG = {"Portugal": "pt", "Brazil": "pt", "Angola": "pt", "Mozambique": "pt",
               "Cape Verde": "pt", "Italy": "it", "Spain": "es", "France": "fr",
               "Germany": "de", "The Netherlands": "nl", "Netherlands": "nl"}


def find(name, nation, dob):
    """(lang, wikitext) of the player's article when the row gives no link:
    his own language's Wikipedia first, then English, by his name (redirects
    followed), with "(futebolista)"/"(footballer)" tried too. Taken only when
    its birth date equals `dob`, so a namesake is never read."""
    if not dob:
        return None, None
    langs = list(dict.fromkeys([NATION_LANG.get(nation, "en"), "en"]))
    suffix = {"pt": "futebolista", "it": "calciatore", "es": "futbolista", "fr": "football",
              "de": "Fußballspieler", "nl": "voetballer", "en": "footballer"}
    for lang in langs:
        if lang not in ("pt", "it", "en"):
            continue                      # no parser for that infobox yet
        for title in (name, "%s (%s)" % (name, suffix[lang])):
            slug = re.sub(r"\W+", "_", title.lower()).strip("_")
            try:
                data = fetch_wikitext(lang, title, "wiki_%s_%s.json" % (lang, slug))
            except Exception:
                continue
            wt = (data.get("parse") or {}).get("wikitext")
            if not wt:
                continue
            box = infobox_any(wt, lang)
            if box.get("dob") == tuple(dob):
                return lang, wt
    return None, None


def height_cm(wikitext):
    """Height in cm from an en/pt/it infobox ("1.81 m", "1,75 m",
    {{height|m=1.81}}, "181 cm"), or None."""
    wt = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", wikitext, flags=re.S)
    m = re.search(r"\|\s*(?:height|altura|Altezza)\s*=\s*([^\n|]*(?:\{\{[^}]*\}\})?[^\n|]*)", wt, re.I)
    if not m:
        return None
    v = m.group(1)
    a = re.search(r"(\d)[.,](\d{2})\s*m", v) or re.search(r"m\s*=\s*(\d)[.,](\d{2})", v)
    if a:
        return int(a.group(1)) * 100 + int(a.group(2))
    b = (re.search(r"(1\d{2})\s*cm", v) or re.search(r"cm\s*=\s*(1\d{2})", v)
         or re.match(r"\s*(1[5-9]\d|20\d)\s*$", v))      # it: "|Altezza = 184"
    return int(b.group(1)) if b else None
