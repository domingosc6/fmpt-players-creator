import zipfile, re, sys
import xml.etree.ElementTree as ET
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"

class Book:
    def __init__(self, path):
        self.z = zipfile.ZipFile(path)
        wb = ET.fromstring(self.z.read("xl/workbook.xml"))
        rels = {r.get("Id"): r.get("Target") for r in
                ET.fromstring(self.z.read("xl/_rels/workbook.xml.rels"))}
        self.sheets = {s.get("name"): "xl/" + rels[s.get(RNS + "id")].lstrip("/")
                       for s in wb.iter(NS + "sheet")}
        ss = ET.fromstring(self.z.read("xl/sharedStrings.xml"))
        self.strings = ["".join(t.text or "" for t in si.iter(NS + "t")) for si in ss]
        st = ET.fromstring(self.z.read("xl/styles.xml"))
        fonts = [f.find(NS + "b") is not None for f in st.find(NS + "fonts")]
        self.bold = [fonts[int(x.get("fontId", 0))] for x in st.find(NS + "cellXfs")]

    def cells(self, name):
        """{(row, col_letters): (text, bold)}"""
        out = {}
        for row in ET.fromstring(self.z.read(self.sheets[name])).iter(NS + "row"):
            for c in row.iter(NS + "c"):
                ref = c.get("r")
                col = re.match(r"[A-Z]+", ref).group(0)
                r = int(ref[len(col):])
                if c.get("t") == "s":
                    v = c.find(NS + "v")
                    txt = self.strings[int(v.text)] if v is not None else ""
                elif c.get("t") == "inlineStr":
                    txt = "".join(t.text or "" for t in c.iter(NS + "t"))
                else:
                    v = c.find(NS + "v")
                    txt = v.text if v is not None else ""
                b = self.bold[int(c.get("s", 0))]
                if txt or b:
                    out[(r, col)] = (txt, b)
        return out
