"""Every country squad sheet as one table of players.

    py scripts/fm27_sheets.py            # rebuild work/all_sheet_players.json

Reads the Drive squad sheets exported to work/squad_sheets/<title>.xlsx (Drive
connector download_file_content, xlsx export). Two layouts:

- club blocks: a club name, the row below it "Posicao | Nome | Pais/Nacionalidade",
  then one player per row until a blank row (league tabs, the Avulsos - Europa
  country tabs);
- lists: a header row with "Jogador" (or "Nome") and "Equipa" columns (Avulsos,
  Camadas Jovens, free-agent lists without an Equipa column).

A youth tab is "Camadas Jovens", "CJ" or "Primavera"; a list row can also carry
its own youth flag (Portugal's Avulsos). "Divisoes" tabs carry no players.

Each player: {name, club (as the sheet writes it, "" for a free agent), pos,
nation, youth, sheet, tab}.
"""
import glob
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "placements"))
import xlsx_read  # noqa: E402

OUT = os.path.join(ROOT, "work", "all_sheet_players.json")


def plain(s):
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().strip().lower()


POS_HEAD = {"posicao", "pos", "position"}
NAME_HEAD = {"nome", "jogador", "name"}


def hcell(s):
    return plain(s).rstrip(".").strip()


def youth_tab(title):
    t = plain(title)
    return "camadas" in t or "primavera" in t or bool(re.search(r"(^|[\s-])cj($|\s)", t))


def parse(path):
    sheet = os.path.basename(path)[:-5]
    out = []
    for tab, cells in xlsx_read.read(path).items():
        if plain(tab).startswith(("estrutura", "glossario", "mexico - divis")) or "divisoes" in plain(tab) or plain(tab).endswith("divisoes"):
            continue
        youth = youth_tab(tab)
        nr = max([r for r, c in cells] or [0])
        nc = max([c for r, c in cells] or [0])
        get = lambda r, c: str(cells.get((r, c)) or "").strip()
        # a list: the first row holding "jogador"/"nome" and "equipa"
        head = None
        for r in range(1, min(nr, 6) + 1):
            labels = {plain(get(r, c)): c for c in range(1, nc + 1) if get(r, c)}
            if ("jogador" in labels or "nome" in labels) and ("equipa" in labels or "clube" in labels
                                                             or "livres" in plain(tab)):
                head = (r, labels)
                break
        if head:
            r0, labels = head
            cn = labels.get("jogador") or labels.get("nome")
            cp = labels.get("posicao") or labels.get("posição")
            cc = labels.get("equipa") or labels.get("clube")
            cx = labels.get("pais") or labels.get("nacionalidade")
            flag_col = (cc + 1) if cc else None
            for r in range(r0 + 1, nr + 1):
                name = get(r, cn)
                if not name:
                    continue
                y = youth or (bool(get(r, flag_col)) and plain(tab).startswith("avulsos") and sheet == "Portugal")
                out.append({"name": name, "club": get(r, cc) if cc else "", "pos": get(r, cp) if cp else "",
                            "nation": get(r, cx) if cx else "", "youth": bool(y), "sheet": sheet, "tab": tab})
            continue
        # club blocks
        for r in range(2, nr + 1):
            for c in range(1, nc):
                if hcell(get(r, c)) not in POS_HEAD or hcell(get(r, c + 1)) not in NAME_HEAD:
                    continue
                club = get(r - 1, c) or next((get(r - 1, k) for k in range(c, c + 3) if get(r - 1, k)), "")
                for rr in range(r + 1, nr + 1):
                    pos, name = get(rr, c), get(rr, c + 1)
                    if hcell(pos) in POS_HEAD or (not name and not pos):
                        break
                    if name and club:
                        out.append({"name": name, "club": club, "pos": pos, "nation": get(rr, c + 2),
                                    "youth": youth, "sheet": sheet, "tab": tab})
    return out


def build():
    rows = []
    for f in sorted(glob.glob(os.path.join(ROOT, "work", "squad_sheets", "*.xlsx"))):
        got = parse(f)
        seen = set()
        for x in got:
            k = (x["name"], x["club"], x["youth"])
            if k not in seen:          # the Atual and Historica tabs repeat a club
                seen.add(k)
                rows.append(x)
        print("%-28s %5d players" % (os.path.basename(f)[:-5], len(seen)))
    json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(len(rows), "->", OUT)
    return rows


def load():
    if not os.path.exists(OUT):
        return build()
    return json.load(open(OUT, encoding="utf-8"))


if __name__ == "__main__":
    build()
