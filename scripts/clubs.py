import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import xml.etree.ElementTree as ET
SRC = ROOT + "/FM 26 XML Files/extracts/FM26 Files/FMPT Legends - Portugal - Squads.xml"
PCTI = str(int.from_bytes(b"Pcti", "big"))
out = {}
for _, el in ET.iterparse(SRC, events=("end",)):
    if el.tag != "record" or el.get("id") is not None:
        continue
    p = el.find('unsigned[@id="property"]')
    if p is not None and p.get("value") == PCTI:
        u = el.find('large[@id="db_unique_id"]')
        nv = el.find('record[@id="new_value"]')
        d = nv.find('integer[@id="DBID"]') if nv is not None else None
        if u is not None and d is not None:
            out[u.get("value")] = d.get("value")     # last club wins
    el.clear()
WORK = os.path.join(ROOT, "work")
os.makedirs(WORK, exist_ok=True)
json.dump(out, open(os.path.join(WORK, "clubs.json"), "w"))
print("records with a club:", len(out))
