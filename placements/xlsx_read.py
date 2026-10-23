"""Minimal .xlsx reader (no openpyxl): {sheet name: {(row, col): text}},
rows and columns from 1. Merged cells hold their value in the top-left cell only."""
import re
import zipfile
import xml.etree.ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _col(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n


def read(path):
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    rels = {r.get("Id"): r.get("Target") for r in
            ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out = {}
    for sh in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", NS):
        target = rels[sh.get(REL)].lstrip("/")
        target = target if target.startswith("xl/") else "xl/" + target
        cells = {}
        for c in ET.fromstring(z.read(target)).iter("{%s}c" % NS["m"]):
            ref = c.get("r")
            v = c.find("m:v", NS)
            if c.get("t") == "s" and v is not None:
                text = shared[int(v.text)]
            elif c.get("t") == "inlineStr":
                text = "".join(t.text or "" for t in c.iter("{%s}t" % NS["m"]))
            else:
                text = v.text if v is not None else None
            if text not in (None, ""):
                row = int(re.search(r"\d+", ref).group(0))
                cells[(row, _col(ref))] = text.strip()
        out[sh.get("name")] = cells
    return out


def rows(cells):
    """The sheet as a list of rows (lists), 1-based columns mapped to 0-based."""
    if not cells:
        return []
    nr = max(r for r, _ in cells)
    nc = max(c for _, c in cells)
    return [[cells.get((r, c), "") for c in range(1, nc + 1)] for r in range(1, nr + 1)]
