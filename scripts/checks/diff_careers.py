"""Career-level diff of two converted builds.

Groups by IDENTITY the way the converter does - a person is his whole member set,
not one id - and reads with the editor-faithful replay, which models Duplicate.
`clean_import.replay` does not, and a name-keyed id lookup only finds ids that
set a name, and both of those made Thomas Finney look unchanged when he had lost
half his career.
"""
import sys, os, glob, collections, xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import convert_edition as ce, clean_import as ci, probe_editor_replay as pr, fm_names, extract_squad as ex

nm = fm_names.Names(offline=True)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NEW, X = sys.argv[1], os.path.join(ROOT, "FM 26 XML Files/converted_xmls")

def index(p):
    return ex.people_index(ce, nm, ET.parse(p).getroot())

tot = worse = 0
for np_ in sorted(glob.glob(f"{NEW}/*.xml")):
    c = os.path.basename(np_)[:-4]
    base = (f"{X}/FMPT Legends - Portugal FM18 - target2025 - clean.xml" if c == "Portugal FM18"
            else f"{X}/FMPT Legends - {c} - target2025 - clean.xml")
    ixa, ixb = index(base), index(np_)
    ka = {frozenset(ixa["members"][q]): q for q in ixa["members"]}
    kb = {frozenset(ixb["members"][q]): q for q in ixb["members"]}
    changed = []
    for k in set(ka) & set(kb):
        oa = ixa["groups"].get((ka[k], "Plhs"), [])
        ob = ixb["groups"].get((kb[k], "Plhs"), [])
        if len(oa) == len(ob):
            continue
        ra, _ = pr.replay(oa)
        rb, dr = pr.replay(ob)
        n = ixb["names"].get(kb[k]) or nm.person(sorted(k)[0]) or "(existing DB record)"
        changed.append((n, len(ra), len(rb), ci.year_gaps(ra), ci.year_gaps(rb), len(dr)))
    if not changed:
        continue
    print(f"\n### {c} ({len(changed)})")
    for n, a, b, ga, gb, dr in sorted(changed, key=lambda r: -(r[2] - r[1])):
        bad = gb > ga or b < a
        worse += bad
        tot += 1
        print(f"   {n:38} rows {a:3}->{b:3}  gaps {ga}->{gb}  dropped-ops {dr}"
              f"{'   <-- WORSE' if bad else ''}")
print(f"\n{tot} careers changed, {worse} regressions")
