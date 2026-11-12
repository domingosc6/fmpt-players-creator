#!/usr/bin/env python3
"""CLI: a CSV of players in, one changeset + report per player out.

Usage:
    create_legends.py inputs/probe.csv            (writes to out/probe/)
    create_legends.py inputs/probe.csv --out-dir somewhere/else
"""
import argparse
import collections
import csv
import os
import re
import sys

# every cache and sheet is UTF-8; Windows otherwise reads files as cp1252
# and garbles accented names (Atlético, São Tomé): rerun in UTF-8 mode and
# wait for it - os.execv on Windows starts a new process and returns to the
# prompt at once, leaving the batch running in the background
if __name__ == "__main__" and not sys.flags.utf8_mode:
    import subprocess
    sys.exit(subprocess.call([sys.executable, "-X", "utf8"] + sys.argv))

import build

HERE = os.path.dirname(os.path.abspath(__file__))


def write_report(path, result, row):
    p = result["profile"]
    lines = []
    lines.append("# %s - created (%s)" % (p.name, p.nation))
    lines.append("")
    lines.append("Prime season %s, target club %s, target season %s, offset %+d years."
                 % (row["prime_season"], row.get("team_name") or row["target_club"], row["target_season"],
                    result["offset"]))
    lines.append("")
    lines.append("Created id: `%s`" % result["uid"])
    lines.append("")
    v = result["verify"]
    lines.append("## Verification")
    lines.append("Replayed the written file: %d changes, %d playing-history rows, %d spells."
                 % (v["changes"], v["plhs_rows"], v["spells"]))
    lines.extend(["- FAIL: " + x for x in v["problems"]] or
                 ["- PASS: every Plhs, Pnph and Pdcn op lands, the replayed grids equal the model, "
                  "every change carries a db_random_id."])
    lines.append("")
    lines.append("## Profile")
    lines.append("- Name: first %s, last %s, common %s, full %s" % (p.first, p.last, p.common or "-", p.full or "-"))
    lines.append("- DOB (real): %d/%d/%d -> shifted %d/%d/%d"
                 % (p.dob[0], p.dob[1], p.dob[2], p.dob[0], p.dob[1], p.dob[2] + result["offset"]))
    lines.append("- Nation: %s (DBID %s)" % (p.nation, result["nation_dbid"]))
    lines.append("- Place of birth: %s" % (p.birthplace or "-"))
    born_in, eth, label = result["ethnicity"]
    lines.append("- Ethnicity: %s (born in %s)%s" % (label, born_in or "-",
                                                     "" if eth is None else ", Peth %d" % eth))
    lines.append("- Position (source): %s -> written 20 on the mapped FourCC" % (p.position,))
    lines.append("- Height: %s" % ("%d cm" % p.height if p.height else "- (no source)"))
    lines.append("- Caps before the prime season: Piap %d, Pigl %d" % (p.caps, p.cap_goals))
    if result.get("ratings"):
        lines.append("- Ratings (sheet): " + ", ".join(result["ratings"]))
    lines.append("")
    lines.append("## Career table")
    lines.append("| real season | shifted year | club | FM id | division | FM id | apps | goals | joined | left | flags |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    fmt = lambda el: "%s/%s/%s" % (el.get("day"), el.get("month"), el.get("year")) if el is not None else "-"
    for r, pr, div_id in zip(p.rows, result["plhs_rows"], result["row_divs"]):
        hit = result["club_ids"].get(r.club)
        tags = []
        if r.onln:
            tags.append("loan")
        if r.ytht:
            tags.append("youth")
        if r.flag:
            tags.append("DISAGREEMENT")
        season = ("%d" % r.year if hit and build.is_calendar_club(hit["id"])
                  else "%d/%s" % (r.year, str(r.year + 1)[-2:]))
        lines.append("| %s | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            season, r.year + result["offset"], r.club,
            ("%s %s%s" % (hit["id"], hit["name"], " (CHECK)" if hit.get("weak") else "")) if hit else "-",
            r.level or "-", div_id or "-",
            r.apps if r.apps is not None else "-",
            r.goals if r.goals is not None else "-", fmt(pr["join"]), fmt(pr["leaving"]),
            ", ".join(tags) or "-"))
    lines.append("")
    lines.append("## Club spells (Pnph, real dates, shifted +%d in the file)" % result["offset"])
    for s in sorted(result["spells"], key=lambda s: s["join"][::-1]):
        left = "%d/%d/%d" % s["left"] if s["left"] else "open"
        lines.append("- club %s: %d/%d/%d -> %s" % (s["club"], s["join"][0], s["join"][1],
                                                     s["join"][2], left))
    for s in result["dropped_spells"]:
        lines.append("- DROPPED (unresolved club %s): join %s" % (s["club"], s["join"]))
    lines.append("")
    lines.append("## Days at club and nation (Pdcn, cleared and rewritten)")
    lines.append("- Clubs: %s" % (", ".join("%s=%d" % kv for kv in result["club_days"].items()) or "none"))
    lines.append("- Nations: %s" % (", ".join("%s=%d" % kv for kv in result["nation_days"].items()) or "none"))
    lines.append("")
    lines.append("## Homegrown")
    lines.append("- Clubs: %s" % (result["hg_clubs"] or "none"))
    lines.append("- Nations: %s%s" % (result["hg_nations"] or "none",
                                      " (fell back to the record's own nation)"
                                      if result["hg_fell_back"] else ""))
    lines.append("")
    lines.append("## Contract")
    lines.append("- Club: %s (FM id %s)" % (row.get("team_name") or row["target_club"], result["target_hit"]["id"]))
    lines.append("- Pcjd forced to: %d/%d/%d" % result["target_join"])
    lines.append("- PCNj (arrival in the target club's country): %d/%d/%d" % result["nation_joined"])
    lines.append("- Pcsd / Pcex: drawn by `convert_edition.sync_contract_dates`, seeded from the record id")
    lines.append("")
    lines.append("## Flags")
    if result["flags"]:
        for f in result["flags"]:
            lines.append("- %s" % f)
    else:
        lines.append("- none")
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")


FIFA_CODES = {
    "POR": "Portugal", "PRT": "Portugal", "MOZ": "Mozambique", "ANG": "Angola", "CPV": "Cape Verde",
    "CBV": "Cape Verde", "MAL": "Mali", "MLI": "Mali",
    "GNB": "Guinea-Bissau", "STP": "São Tomé e Príncipe", "BRA": "Brazil", "ARG": "Argentina",
    "URU": "Uruguay", "PAR": "Paraguay", "CHI": "Chile", "COL": "Colombia", "PER": "Peru",
    "ECU": "Ecuador", "VEN": "Venezuela", "BOL": "Bolivia", "MEX": "Mexico", "USA": "United States",
    "CAN": "Canada", "ESP": "Spain", "ITA": "Italy", "FRA": "France", "GER": "Germany",
    "ENG": "England", "SCO": "Scotland", "WAL": "Wales", "NIR": "Northern Ireland",
    "IRL": "Republic of Ireland", "NED": "The Netherlands", "BEL": "Belgium", "SUI": "Switzerland",
    "AUT": "Austria", "GRE": "Greece", "TUR": "Türkiye", "RUS": "Russia", "UKR": "Ukraine",
    "POL": "Poland", "CZE": "Czech Republic", "SVK": "Slovakia", "HUN": "Hungary", "ROU": "Romania",
    "ROM": "Romania", "BUL": "Bulgaria", "SRB": "Serbia", "CRO": "Croatia", "SVN": "Slovenia", "BIH": "Bosnia and Herzegovina",
    "MKD": "North Macedonia", "ALB": "Albania", "MNE": "Montenegro", "DEN": "Denmark", "SWE": "Sweden",
    "NOR": "Norway", "FIN": "Finland", "ISL": "Iceland", "CYP": "Cyprus", "ISR": "Israel",
    "NGA": "Nigeria", "GHA": "Ghana", "CMR": "Cameroon", "CIV": "Côte d'Ivoire", "SEN": "Senegal",
    "MAR": "Morocco", "ALG": "Algeria", "TUN": "Tunisia", "EGY": "Egypt", "RSA": "South Africa",
    "COD": "DR Congo", "CGO": "Congo", "ZAM": "Zambia", "ZIM": "Zimbabwe", "MLI": "Mali",
    "GUI": "Guinea", "JPN": "Japan", "KOR": "Korea Republic", "CHN": "China PR", "AUS": "Australia",
}


def sheet_dob(text):
    """(day, month, year) from a DOB cell (30/10/1975 or 30-10-1975), or None."""
    m = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$", text)
    return tuple(int(x) for x in m.groups()) if m else None


def sheet_row(raw, target_season):
    """The user's sheet (Position, Name, Nation, Team[, Team Id], Season,
    Website, Exists[, Id]) or the older probe columns, as the dict the builders take.
    Season is the prime season's first year (1995 = 1995/96). Exists Y/Yes
    means FM26 already has him: fixed in place, found by name unless an id is
    given, in an Id column or in Exists itself. Every column whose header holds Website/Link/URL (alternate_website too) is a source."""
    r = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
    if "prime_season" in r:                       # probe format
        r.setdefault("nation", "Italy")
        r["urls"] = r.get("urls", "").split()
        r["mode"] = "fix" if r.get("dbid") else "create"
        r["target_season"] = r.get("target_season") or str(target_season)
        return r
    urls = []
    for k, v in r.items():
        # Website, alternate_website, Link 2, URL...
        if re.search(r"website|link|url", k) and v:
            urls.extend(v.split())
    exists = r.get("exists", "").lower() in ("y", "yes", "s", "sim", "true")
    # an FM26 id in the Exists cell (4200972) both says he exists and names him
    dbid = r.get("id") or r.get("dbid") or (r.get("exists") if r.get("exists", "").isdigit() else "")
    nation = r.get("nation", "")
    nation = FIFA_CODES.get(nation.upper(), nation)       # "MOZ" or "Mozambique"
    # 'António "Flávio" Almeida': the quoted part is the name he played under
    raw_name = r.get("name", "")
    nick = re.match(r'^\s*(.*?)\s*"([^"]+)"\s*(.*?)\s*$', raw_name)
    name = nick.group(2) if nick else raw_name
    first_last = (nick.group(1), nick.group(3)) if nick else None
    # "Mdef/MC": the first code is the position written
    position = re.split(r"[/,]", r.get("position", ""))[0].strip()
    # the target club by name (found once per sheet, target_ids) or by FM26
    # id, in its own column or in the Team cell itself
    team_id = next((v for k, v in r.items() if k.replace("_", " ") in
                    ("team id", "teamid", "club id", "clubid", "team dbid") and v.isdigit()), "")
    return {"name": name, "first_last": first_last, "nation": nation, "position": position,
            "target_club": team_id or r.get("team", ""), "team_name": r.get("team", ""), "prime_season": r.get("season", ""),
            "target_season": str(target_season), "urls": urls,
            "dbid": dbid,
            "dob": sheet_dob(r.get("dob", "")),
            # Team RET: retire the person FM26 has (user, 2026-10-22)
            "mode": "retire" if r.get("team", "").upper() == "RET" else
                    "fix" if exists or dbid else "create",
            "ratings": {k: r.get(k, "") for k in ("ca", "pa", "cr", "hr", "wr")}}


def target_ids(rows):
    """Each Team name resolved once for the whole sheet, with the nation most
    of its players share (a Salamanca sheet is Spanish): looked up with each
    player's own nation, an Argentinian's "Salamanca" landed on another club
    than a Spaniard's. The id goes back into the rows; an id (Team Id column
    or the Team cell) is kept, and names its team for the rows without one."""
    import collections
    # a Team Id given on any row names that team for the rows that left it out
    known = {r["team_name"]: r["target_club"] for r in rows
             if r["target_club"].strip().isdigit() and r["team_name"] != r["target_club"]}
    for r in rows:
        if not r["target_club"].strip().isdigit() and r["team_name"] in known:
            r["target_club"] = known[r["team_name"]]
    cache = build._club_cache()
    for team in {r["target_club"].strip() for r in rows if not r["target_club"].strip().isdigit()}:
        mine = [r for r in rows if r["target_club"].strip() == team]
        home = collections.Counter(r["nation"] for r in mine).most_common(1)[0][0]
        hit = build.club_for(team, None, home, cache)
        if hit is None:
            print("target club %r did not resolve: put its FM26 id in the Team column" % team)
            continue
        print("target club %r -> %s %s%s" % (team, hit["id"], hit["name"],
                                             " (CHECK: loose match)" if hit.get("weak") else ""))
        for r in mine:
            r["target_club"] = str(hit["id"])
    build._club_cache_save(cache)


def import_downloads(folder):
    """Move the bookmarklets' files into cache/. A browser saves a repeat as
    "zerozero_183908 (1).txt": the newest copy of each player wins."""
    import shutil
    cache = os.path.join(HERE, "cache")
    newest = {}
    for f in os.listdir(folder):
        m = re.match(r"^((?:zerozero_\d+|bdfutbol_j\d+))(?: \(\d+\))?\.txt$", f)
        if m:
            path = os.path.join(folder, f)
            if m.group(1) not in newest or os.path.getmtime(path) > os.path.getmtime(newest[m.group(1)]):
                newest[m.group(1)] = path
    for key, path in sorted(newest.items()):
        shutil.copy2(path, os.path.join(cache, key + ".txt"))
        print("imported", os.path.basename(path), "->", "cache/%s.txt" % key)
    for f in os.listdir(folder):
        if re.match(r"^(?:zerozero_\d+|bdfutbol_j\d+)(?: \(\d+\))?\.txt$", f):
            os.remove(os.path.join(folder, f))
    if not newest:
        print("no bookmarklet files in", folder)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv_path")
    ap.add_argument("--out-dir", help="default out/<sheet>, named after the CSV (out/famalicao)")
    ap.add_argument("--ids", default=os.path.join(HERE, "ids.json"))
    ap.add_argument("--only", action="append", default=[],
                    help="rebuild only this player (repeatable); the others keep the files "
                         "already in --out-dir and are merged as they are")
    ap.add_argument("--import-downloads", nargs="?", const=os.path.expanduser("~/Downloads"),
                    metavar="DIR", help="first move the bookmarklet files (zerozero_*.txt, "
                    "bdfutbol_*.txt) from DIR (default ~/Downloads) into cache/")
    ap.add_argument("--target-season", type=int, default=2025,
                    help="season the legends are moved to (2025 = 2025/26, FM26)")
    a = ap.parse_args()

    # one folder per sheet, or every sheet's files pile up together in out/
    a.out_dir = a.out_dir or os.path.join(HERE, "out", os.path.splitext(os.path.basename(a.csv_path))[0])
    os.makedirs(a.out_dir, exist_ok=True)
    if a.import_downloads:
        import_downloads(a.import_downloads)
    import fix
    done, summary = [], []
    with open(a.csv_path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        rows = [sheet_row(r, a.target_season) for r in csv.DictReader(fh, dialect=dialect)]
        rows = [r for r in rows if r["name"]]
    target_ids([r for r in rows if r["mode"] != "retire"])
    # two people with one name (Serginho the goalkeeper and Serginho the
    # winger) need their own files, or the second overwrites the first
    repeated = {n for n, c in collections.Counter(r["name"].strip() for r in rows).items() if c > 1}
    for i, row in enumerate(rows):
        name = row["name"].strip()
        mode = row["mode"]
        stem = "%s (%s)" % (name, row["dbid"] or "row %d" % (i + 2)) if name in repeated else name
        out_xml = os.path.join(a.out_dir, "FMPT Legends - %s - %s.xml" % (mode, stem))
        if a.only and name not in a.only:
            if os.path.exists(out_xml):
                done.append(out_xml)
                summary.append((name, mode, "KEPT", "not rebuilt this run", 0))
            continue
        # one player's failure is reported and the batch goes on
        try:
            # an id FM26's history or the site index still names, but whose
            # person is gone: every op would land on "Record not found"
            import fm26_people
            if mode in ("fix", "retire") and str(row["dbid"]).isdigit() and not fm26_people.exists(row["dbid"]):
                if mode == "retire":
                    raise SystemExit("FM26 id %s is not in FM26's people database: "
                                     "nothing to retire" % row["dbid"])
                # a person FM26 deleted but whose playing history it kept:
                # created, his career copied from that history (user, 2026-10-22)
                mode = row["mode"] = "create"
                row["history_id"] = row["dbid"]
                out_xml = os.path.join(a.out_dir, "FMPT Legends - %s - %s.xml" % (mode, stem))
            if mode == "retire":
                result = fix.build_retire(row, out_xml)
                fix.write_retire_report(out_xml[:-4] + ".md", result, row)
            elif mode == "fix":
                # a person FM26 already has: fixed in place on his DBID
                result = fix.build_fix(row, out_xml)
                fix.write_report(out_xml[:-4] + ".md", result, row)
            else:
                result = build.build_changeset(row, os.path.join(HERE, "cache"), a.ids,
                                               out_xml, out_xml[:-4] + ".md")
                write_report(out_xml[:-4] + ".md", result, row)
        except (Exception, SystemExit) as e:
            summary.append((name, mode, "ERROR", str(e).splitlines()[0][:200], 0))
            print("ERROR", name, e)
            continue
        problems = result["verify"]["problems"]
        summary.append((name, mode, "FAIL" if problems else "PASS",
                        "; ".join(problems)[:200], len(result["flags"])))
        if not problems:
            done.append(out_xml)
        print("wrote", out_xml)

    base = os.path.splitext(os.path.basename(a.csv_path))[0]
    if done:
        import merge_changesets as mc
        head, _, tail = mc.split(done[0])
        merged = os.path.join(a.out_dir, "FMPT Legends - %s - all.xml" % base)
        open(merged, "w", encoding="utf-8").write(
            head + "".join(mc.body(p) for p in done) + "\n\t" + tail)
        print("merged %d players -> %s" % (len(done), merged))
    lines = ["# Batch %s" % base, "",
             "%d players: %d passed, %d kept from an earlier run, %d failed verification, %d errors. "
             "Only passed and kept ones are in the merged file."
             % (len(summary), sum(s[2] == "PASS" for s in summary), sum(s[2] == "KEPT" for s in summary),
                                      sum(s[2] == "FAIL" for s in summary),
                                      sum(s[2] == "ERROR" for s in summary)), "",
             "| player | mode | result | flags | detail |", "|---|---|---|---|---|"]
    lines += ["| %s | %s | %s | %d | %s |" % (n, m, r, f, d.replace("|", "/")) for n, m, r, d, f in summary]
    open(os.path.join(a.out_dir, "FMPT Legends - %s - summary.md" % base), "w",
         encoding="utf-8").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
