"""national-football-teams.com parser.

Primary source for anyone with international caps: per-season club, apps,
goals, division level (roman numerals), plus the position and the match list
used for caps. Fetched with a browser User-Agent and cached to disk.
"""
import os
import re
import time
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")
DELAY = 2.5


def fetch(url, cache_name):
    """GET url, cached under creator/cache/. A hit skips the delay."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, cache_name)
    if os.path.exists(path):
        return open(path, encoding="utf-8", errors="replace").read()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    open(path, "w", encoding="utf-8").write(data)
    time.sleep(DELAY)
    return data


def position(html):
    """"Centre Back (CB)" -> ("Centre Back", "CB")."""
    m = re.search(r'itemprop="positionName">([^<]+)</span>.*?itemprop="positionAbbreviation">'
                  r'([^<]+)</span>', html, re.S)
    return (m.group(1).strip(), m.group(2).strip()) if m else (None, None)


def dob(html):
    """(day, month, year) from the profile header, or None."""
    m = re.search(r'itemprop="birthDate">(\d{4})-(\d{2})-(\d{2})<', html)
    if m:
        return int(m.group(3)), int(m.group(2)), int(m.group(1))
    return None


def birthplace(html):
    """The town of birth as the page writes it, or None."""
    m = re.search(r'itemprop="birthPlace">([^<]+)<', html)
    return m.group(1).strip() if m else None


def clubs(html):
    """Season rows, newest first (the page's own order) - the primary evidence for
    the career table. Two clubs in one season are listed later-club-first, as the
    page shows them; the caller reverses to chronological order.

    Each row: dict(season="2004/05", club="AC Fiorentina", apps=int, goals=int,
    level="I"|"II"|... or None, nation=the club's country as the site names it)."""
    start = html.find('<table class="table clubs')
    if start < 0:
        return []
    end = html.index("</table>", start)
    block = html[start:end]
    rows = re.findall(r"<tr>(.*?)</tr>", block, re.S)
    out = []
    for r in rows:
        season_m = re.search(r'class="season" data-order="\d+">([^<]+)<', r)
        if not season_m:
            continue
        club_m = re.search(r'<a href="/club/\d+/[^/]+/[^"]+\.html"\s*>\s*\n?\s*([^\n<]+)', r)
        # "-" (no figures known) is data-order="-1": blank, never 0 - a real
        # 0 is data-order="0" (Diallo: Mali 1981-87 are "-", Sporting 1987/88 is 0)
        m_m = re.search(r'class="stats matches" data-order="(-?\d+)"', r)
        g_m = re.search(r'class="stats goals" data-order="(-?\d+)"', r)
        num = lambda m: int(m.group(1)) if m and int(m.group(1)) >= 0 else None
        lvl_m = re.search(r'title="[^"]+">([IV]+)</abbr>', r)
        nat_m = re.search(r'href="/country/\d+/[^/]+/([^"/]+)\.html"', r)
        out.append({
            "season": season_m.group(1),
            "club": club_m.group(1).strip() if club_m else None,
            "apps": num(m_m),
            "goals": num(g_m),
            "level": lvl_m.group(1) if lvl_m else None,
            "nation": nat_m.group(1).replace("_", " ") if nat_m else None,
        })
    return out


def matches(html):
    """International caps: list of (date "YYYY-MM-DD", goals)."""
    start = html.find('<table class="table countries matches')
    if start < 0:
        return []
    end = html.index("</table>", start)
    block = html[start:end]
    rows = re.findall(r"<tr[^>]*itemtype=\"http://schema.org/SportsMatch\">(.*?)</tr>", block, re.S)
    out = []
    for r in rows:
        d_m = re.search(r'itemprop="startDate"[^>]*>\s*<a[^>]*>([\d-]+)</a>', r)
        goals = re.findall(r'class="stats" data-order="(\d+)">', r)
        if d_m:
            out.append((d_m.group(1), int(goals[0]) if goals else 0))
    return out


def height(html):
    """Height in cm from the profile ("1.77m"), or None."""
    m = re.search(r'itemprop="height">\s*(\d)[.,](\d{2})\s*m', html)
    return int(m.group(1)) * 100 + int(m.group(2)) if m else None
