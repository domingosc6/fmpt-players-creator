"""work/<country>_sheet_clubs.json from a squad sheet dump: {name: [[club, youth]]},
and work/<country>_sheet_squads.json: {club: [[position, name, nation, youth]]}.

    py scripts/fm27_sheet_clubs.py Portugal work/portugal_squad_sheet_raw.json

The dump is the Sheets API spreadsheets.get with grid data (formattedValue) of
the country's Drive squad sheet. Each tab is laid out in blocks: a club name, the
row below it "Posicao | Nome | Pais", then one player per row until a blank
row. "Camadas Jovens" is the youth tab. The "Divisoes" tabs carry no squads.
"""
import json
import os
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def plain(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().strip().lower()


def main(country, dump):
    raw = json.load(open(dump, encoding="utf-8"))
    sheets = raw.get("content", raw)["sheets"]
    out, counts, squads = {}, {}, {}
    for sh in sheets:
        title = sh["properties"]["title"]
        youth = plain(title).startswith("camadas")
        grid = [[(c.get("formattedValue") or "").strip() for c in (r.get("values") or [])]
                for r in (sh.get("data") or [{}])[0].get("rowData", [])]
        n = 0
        if grid and grid[0] and plain(grid[0][0]) == "jogador":
            # a list tab (Camadas Jovens, Avulsos): Jogador | Posicao | Pais | Equipa | ...
            for line in grid[1:]:
                line = line + [""] * 5
                name, pos, nat, club, flag = line[:5]
                if not (name and club):
                    continue
                y = youth or bool(flag.strip()) and plain(title).startswith("avulsos")
                squads.setdefault(club, []).append([pos, name, nat, y])
                ent = [club, y]
                if ent not in out.setdefault(name, []):
                    out[name].append(ent)
                    n += 1
            counts[title] = n
            continue
        for r, row in enumerate(grid):
            for c, cell in enumerate(row):
                if plain(cell) not in ("posicao", "posição") or r == 0:
                    continue
                nxt = row[c + 1] if c + 1 < len(row) else ""
                if plain(nxt) != "nome":
                    continue
                club = grid[r - 1][c] if c < len(grid[r - 1]) else ""
                if not club:
                    club = next((grid[r - 1][k] for k in range(c, min(c + 3, len(grid[r - 1]))) if grid[r - 1][k]), "")
                for rr in range(r + 1, len(grid)):
                    line = grid[rr]
                    name = line[c + 1] if c + 1 < len(line) else ""
                    pos = line[c] if c < len(line) else ""
                    if plain(pos) in ("posicao",) or (not name and not pos):
                        break
                    if name and club:
                        nat = line[c + 2] if c + 2 < len(line) else ""
                        squads.setdefault(club, []).append([pos, name, nat, youth])
                        ent = [club, youth]
                        if ent not in out.setdefault(name, []):
                            out[name].append(ent)
                            n += 1
        counts[title] = n
    out["_source"] = ("Drive squad sheet '%s', every squad tab, read through the Sheets API; "
                      "name -> [[club as the sheet names it, youth]]" % country)
    path = os.path.join(ROOT, "work", "%s_sheet_clubs.json" % country.lower())
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(len(out) - 1, "names ->", path)
    # the squads themselves, for the membership check (fm27_fix: a legend at a
    # club the sheet lists must be in that club's squad)
    squads = {k: [list(x) for x in dict.fromkeys(tuple(e) for e in v)] for k, v in squads.items()}
    spath = os.path.join(ROOT, "work", "%s_sheet_squads.json" % country.lower())
    json.dump(squads, open(spath, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(len(squads), "squads ->", spath)
    for t, n in counts.items():
        print("  %4d  %s" % (n, t))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
