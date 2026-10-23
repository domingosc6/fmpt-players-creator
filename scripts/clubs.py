import json, os
import xml.etree.ElementTree as ET
SRC = "FM 26 XML Files/extracts/FM26 Files/FMPT Legends - Portugal - Squads.xml"
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
json.dump(out, open(os.environ["CLAUDE_JOB_DIR"] + "/tmp/clubs.json", "w"))
print("records with a club:", len(out))
