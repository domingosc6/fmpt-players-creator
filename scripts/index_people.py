"""One pass over the FM26 file: what the changeset says about each person."""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm_names

SRC = ROOT + "/FM 26 XML Files/extracts/FM26 Files/FMPT Legends - Portugal - Squads.xml"
PERSON, ADDR = "1", "55"

def fourcc(n):
    return n.to_bytes(4, "big").decode("latin1")

people, addr = {}, set()
for _, el in ET.iterparse(SRC, events=("end",)):
    if el.tag != "record" or el.get("id") is not None:
        continue
    tt = el.find('integer[@id="database_table_type"]')
    uid = el.find('large[@id="db_unique_id"]')
    if tt is None or uid is None:
        el.clear(); continue
    u, t = uid.get("value"), tt.get("value")
    if t == ADDR:
        addr.add(u); el.clear(); continue
    if t != PERSON:
        el.clear(); continue
    pid = el.find('unsigned[@id="property"]')
    if pid is None:
        el.clear(); continue
    name = fourcc(int(pid.get("value")))
    ver = el.find('integer[@id="version"]')
    d = people.setdefault(u, {"n": 0, "v": {}, "s": {}, "ptyp": [], "club": None})
    d["n"] += 1
    if ver is not None:
        d["v"][ver.get("value")] = d["v"].get(ver.get("value"), 0) + 1
    nv = el.find('*[@id="new_value"]')
    if nv is not None and nv.tag == "string":
        d["s"][name] = nv.get("value")
    if name == "Ptyp":
        ov = el.find('*[@id="odvl"]')
        d["ptyp"].append((ov.get("value") if ov is not None else None,
                          nv.get("value") if nv is not None else None))
    if name == "Pcti" and nv is not None:
        t2 = nv.find('*[@id="Cclu"]') if nv.tag == "record" else None
        if t2 is not None:
            d["club"] = fm_names.dbid(t2.get("value"))
    el.clear()

for u, d in people.items():
    d["addr"] = u in addr
WORK = os.path.join(ROOT, "work")
os.makedirs(WORK, exist_ok=True)
json.dump(people, open(os.path.join(WORK, "people.json"), "w"))
print("people:", len(people), "with ADDR:", sum(1 for d in people.values() if d["addr"]))
print("named in file:", sum(1 for d in people.values() if d["s"]))
from collections import Counter
print("string props:", Counter(k for d in people.values() for k in d["s"]).most_common(8))
print("versions:", Counter(v for d in people.values() for v in d["v"]).most_common())
