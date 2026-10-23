"""Every club block in the project's squad files: senior and youth names.
Grid sheets: a club header cell, then a header row (Posição | Nome/Jogador/Name
| Nacio.), then rows; a "CAMADAS JOVENS" row starts the youth part. Table
sheets ("Avulsos", "Camadas Jovens"): Jogador | Posição | País | Equipa |
Camadas Jovens?"""
import glob, json, re
import xlsx_read as X
HEAD = ("Nome", "Jogador", "Name")
blocks = []
for f in sorted(glob.glob("xlsx/*.xlsx")):
    if "Players for" in f:
        continue
    for sheet, cells in X.read(f).items():
        heads = sorted((r, c) for (r, c), v in cells.items() if v in HEAD)
        table = [h for h in heads if cells.get((h[0], h[1] + 3)) in ("Equipa",) or cells.get((h[0], h[1] + 2)) == "Equipa"]
        maxr = max((r for r, _ in cells), default=0)
        for (r, c) in heads:
            if (r, c) in table:
                ecol = c + 3 if cells.get((r, c + 3)) == "Equipa" else c + 2
                for rr in range(r + 1, maxr + 1):
                    name = cells.get((rr, c))
                    if not name:
                        continue
                    youth = "jovens" in sheet.lower() or "cj" in sheet.lower().split() or bool(cells.get((rr, ecol + 1)))
                    blocks.append({"file": f[5:-5], "sheet": sheet, "club": cells.get((rr, ecol)) or "(free)",
                                   "kind": "table", "senior": [] if youth else [name], "youth": [name] if youth else []})
                continue
            club = cells.get((r - 1, c - 1)) or cells.get((r - 1, c)) or cells.get((r - 2, c - 1)) or "?"
            nxt = [h[0] for h in heads if h[1] == c and h[0] > r]
            end = (min(nxt) - 2) if nxt else maxr
            senior, youth, in_youth = [], [], False
            empty_slots = 0
            for rr in range(r + 1, end + 1):
                pos, name = cells.get((rr, c - 1), ""), cells.get((rr, c), "")
                if "camadas jovens" in (pos + name).lower():
                    in_youth = True
                    continue
                if pos in ("T", "Pres.") or pos.lower().startswith("trein"):
                    continue
                if name:
                    (youth if in_youth else senior).append(name)
                elif pos and not in_youth:
                    empty_slots += 1
            blocks.append({"file": f[5:-5], "sheet": sheet, "club": club, "kind": "grid",
                           "senior": senior, "youth": youth, "empty_slots": empty_slots})
json.dump(blocks, open("squads.json", "w"), ensure_ascii=False, indent=1)
g = [b for b in blocks if b["kind"] == "grid"]
print(len(g), "club blocks;", sum(len(b["senior"]) for b in g), "senior names;", sum(len(b["youth"]) for b in g), "youth;",
      sum(1 for b in blocks if b["kind"] == "table"), "table rows")
for b in g[:5]: print(b["file"], "/", b["sheet"], "/", b["club"], len(b["senior"]), "senior,", len(b["youth"]), "youth,", b["empty_slots"], "empty")
