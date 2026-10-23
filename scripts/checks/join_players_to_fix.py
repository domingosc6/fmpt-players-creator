"""Join every report's closing "Players to check" table into one file.

Scope matches what is actually IMPORTED (`FM 26 XML Files/final_xmls`):
  - the 32 country reports, in full;
  - the Portugal report, in full - the merged file carries all of its ops;
  - the Portugal FM18 report FILTERED to the people the merge actually carried,
    because that file edits 13,304 people and only ~1,000 of them travel.

Usage: /usr/bin/python3 scripts/checks/join_players_to_fix.py
"""
import os
import re
import sys
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
E = os.path.join(ROOT, "FM 26 XML Files/explanations")
MERGED_REPORT = os.path.join(
    ROOT, "FM 26 XML Files/merged",
    "FMPT Legends - Portugal FM24 + FM18 - target2025 - merged.md")
OUT = os.path.join(ROOT, "FM 26 XML Files/final_xmls", "PLAYERS TO FIX.md")


def table_rows(text, heading):
    """The data rows of the markdown table under `heading`, as cell lists."""
    if heading not in text:
        return []
    body = text[text.index(heading):]
    out = []
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        if line.startswith("|---") or line.startswith("| Player") \
                or line.startswith("| Person"):
            continue
        out.append([c.strip() for c in line.strip().strip("|").split("|")])
    return out


def carried_ids():
    """Record ids the merge actually took out of the FM18 file."""
    if not os.path.exists(MERGED_REPORT):
        return None
    text = open(MERGED_REPORT, encoding="utf-8").read()
    ids = {r[1].strip("`") for r in table_rows(text, "## People carried") if len(r) > 1}
    return ids or None


def main():
    keep = carried_ids()
    rows, per_file, per_reason = [], collections.Counter(), collections.Counter()
    for name in sorted(os.listdir(E)):
        if not name.endswith("clean.md"):
            continue
        country = name.replace("FMPT Legends - ", "").replace(" - target2025 - clean.md", "")
        text = open(os.path.join(E, name), encoding="utf-8").read()
        for cells in table_rows(text, "## Players to check"):
            if len(cells) < 4:
                continue
            player, uid, club, why = cells[0], cells[1], cells[2], cells[3]
            if country == "Portugal FM18":
                # only the people the merge carried reach the game
                if keep is not None and uid not in keep:
                    continue
                country_label = "Portugal (from FM18)"
            else:
                country_label = country
            rows.append((country_label, player, uid, club, why))
            per_file[country_label] += 1
            for one in why.split(";"):
                one = one.strip()
                if one:
                    per_reason[re.sub(r"\d+", "N", one)] += 1

    rows.sort(key=lambda r: (r[0], r[1].lower()))
    L = []
    L.append("# Players to fix — every report's closing table, joined\n")
    L.append(f"**{len(rows)} players** across the 33 files in "
             "`FM 26 XML Files/final_xmls`. One row per player per source report, "
             "so a player edited by two files appears twice. There are "
             f"{len(per_file)} source labels for 33 files because Portugal has two: "
             "its own file and the people carried out of FM18, which both land in "
             "the single merged Portugal file.\n")
    L.append("Nothing here has been repaired and none of it is necessarily wrong - "
             "these are the records worth an eye. The club is the one he is AT in "
             "that file, which is what you search for in the editor, and not "
             "necessarily the club the problem is about. Where the Player column "
             "shows no name, the file never named him and FM's index has no entry, "
             "so the record id IS the identifier.\n")
    L.append("`Portugal (from FM18)` rows are the people the merge carried out of "
             "the FM18 file - the rest of that file is not imported.\n")
    L.append("## By file\n")
    L.append("| File | Players to fix |")
    L.append("|---|---|")
    for k, v in sorted(per_file.items()):
        L.append(f"| {k} | {v} |")
    L.append("")
    L.append("## By reason\n")
    L.append("| Players | Reason |")
    L.append("|---|---|")
    for k, v in per_reason.most_common():
        L.append(f"| {v} | {k} |")
    L.append("")
    L.append("## Every player\n")
    L.append("| File | Player | Club | Reason to fix | Record id |")
    L.append("|---|---|---|---|---|")
    for f, player, uid, club, why in rows:
        L.append(f"| {f} | {player} | {club} | {why} | `{uid}` |")
    L.append("")
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"{len(rows)} players -> {OUT}")
    print(f"files: {len(per_file)}, reason classes: {len(per_reason)}")


if __name__ == "__main__":
    main()
