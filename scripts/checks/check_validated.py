"""Re-read the records the user has personally validated.

Automated diffs miss things: `diff_careers.py` reads only `Plhs`, and the spell
diff is meaningless once spells are rebuilt on purpose. Bobby Tambling lost his
Cork City spell and had a real January transfer flattened to July while every
aggregate check reported zero problems.

So this checks a named list and FAILS on any of:
  - fewer career rows, or a new hole in the career
  - any dropped grid op
  - FEWER CLUB SPELLS  <- the one that let Tambling through
  - a spell date that was usable becoming unusable
"""
import os, sys, xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import convert_edition as ce, clean_import as ci, probe_editor_replay as pr, fm_names, extract_squad as ex

nm = fm_names.Names(offline=True)
NEW, X = sys.argv[1], "FM 26 XML Files/converted_xmls"

# every record the user has said is correct, per file
VALIDATED = {
    "England": ["Robert Victor Tambling", "Ramon Wilson", "Peter Phillip Bonetti",
                "Thomas Finney", "Dennis Frank Wise"],
    "Italy": ["Renato Zaccarelli", "Tarcisio Burgnich", "Cristiano Doni"],
    "Portugal FM18": ["Milonja Djukic", "Tulipa", "José Tavares",
                      "Ahmed Ziad Tlemçani", "Serafim Pereira Batista",
                      "Manuel Barbosa", "Joaquim António Jorge",
                      "José Carlos Gonçalves Abreu", "Pedro Benje Neto"],
    "Portugal": ["Lucho González"],
}


def usable(el):
    if el is None:
        return False
    y = el.get("year")
    if not y or not y.isdigit() or int(y) in ce.SENTINELS:
        return False
    return el.get("day") not in (None, "0") and el.get("month") not in (None, "0")


def look(ix, who):
    for p in ix["members"]:
        if (ix["names"].get(p) or nm.person(ix["members"][p][0]) or "") == who:
            return p
    return None


fails = 0
for c, names in VALIDATED.items():
    a = ex.people_index(ce, nm, ET.parse(f"{X}/FMPT Legends - {c} - target2025 - clean.xml").getroot())
    b = ex.people_index(ce, nm, ET.parse(f"{NEW}/{c}.xml").getroot())
    print(f"\n### {c}")
    for who in names:
        qa, qb = look(a, who), look(b, who)
        if qa is None or qb is None:
            print(f"   {who:30} NOT FOUND (before={qa is not None}, after={qb is not None})")
            fails += 1
            continue
        ra, _ = pr.replay(a["groups"].get((qa, "Plhs"), []))
        rb, dr = pr.replay(b["groups"].get((qb, "Plhs"), []))
        sa = ce.replay_spells_ops(a["groups"].get((qa, "Pnph"), []))
        sb = ce.replay_spells_ops(b["groups"].get((qb, "Pnph"), []))
        lost_date = sum(1 for x, y in zip(sa, sb)
                        for f in ("join", "left")
                        if usable(x[f]) and not usable(y[f]))
        why = []
        if len(rb) < len(ra):
            why.append("career rows lost")
        if ci.year_gaps(rb) > ci.year_gaps(ra):
            why.append("new hole in the career")
        if dr:
            why.append(f"{len(dr)} grid ops drop")
        if len(sb) < len(sa):
            why.append(f"SPELLS LOST ({len(sa)} -> {len(sb)})")
        if lost_date:
            why.append(f"{lost_date} spell date(s) became unusable")
        fails += bool(why)
        print(f"   {who:30} career {len(ra)}->{len(rb)} spells {len(sa)}->{len(sb)}"
              f"{'   <-- ' + '; '.join(why) if why else ''}")
print(f"\n{fails} validated record(s) FAILED")
sys.exit(1 if fails else 0)
