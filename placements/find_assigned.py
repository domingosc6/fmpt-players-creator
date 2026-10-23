"""Every cell of every squad file that names one of the sheet's players."""
import glob, json, re, unicodedata, os
HERE = os.path.dirname(os.path.abspath(__file__))
import xlsx_read as X

def norm(t):
    t = unicodedata.normalize("NFKD", t or "")
    return re.sub(r"[^a-z ]", "", "".join(c for c in t if not unicodedata.combining(c)).lower()).strip()

players = [r for r in X.rows(X.read(os.path.join(HERE, "xlsx/Players for script.xlsx"))["Avulsos"])[1:] if r[1]]
want = {norm(r[1]): r[1] for r in players}
last = {}
for k, v in want.items():
    last.setdefault(k.split()[-1], []).append(v)

def club_of(cells, r, c):
    """The block header above the hit: nearest cell above, in this column or
    the one or two to its left, that names the block (not a position/header)."""
    skip = {"posição", "nome", "nacio.", "jogador", "name", "camadas jovens", "t", "pres."}
    youth = False
    for rr in range(r - 1, 0, -1):
        for cc in (c - 1, c, c - 2):
            v = cells.get((rr, cc), "")
            if v.lower() in ("camadas jovens",):
                youth = True
            if v and (rr + 1, c) in cells and cells.get((rr + 1, c)) in ("Nome", "Jogador", "Name"):
                return v, youth
    return None, youth

hits = []
for f in sorted(glob.glob(os.path.join(HERE, "xlsx/*.xlsx"))):
    if "Players for" in f:
        continue
    for sheet, cells in X.read(f).items():
        for (r, c), v in cells.items():
            n = norm(v)
            if not n:
                continue
            exact = want.get(n)
            # table rows: Jogador | Posição | País | Equipa | Camadas Jovens?
            if exact or (n.split() and n.split()[-1] in last and len(n.split()) <= 4):
                row = [cells.get((r, k), "") for k in range(c, c + 5)]
                club, youth = club_of(cells, r, c)
                hits.append({"player": exact, "cell_text": v, "file": os.path.basename(f)[:-5], "sheet": sheet,
                             "cell": [r, c], "row": row, "club_block": club, "youth_block": youth,
                             "exact": bool(exact)})
json.dump(hits, open(os.path.join(HERE, "assigned_hits.json"), "w"), ensure_ascii=False, indent=1)
print(len(hits), "hits,", sum(h["exact"] for h in hits), "exact")
for h in hits:
    if h["exact"]:
        print("EXACT", h["player"], "|", h["file"], "/", h["sheet"], "|", h["club_block"], "| youth" if h["youth_block"] else "", "|", h["row"][1:5])
