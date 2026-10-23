#!/usr/bin/env python3
"""Builds the two bookmarklets (zerozero, bdfutbol) from the extractor
scripts in ../sources, so a bookmark reads a page exactly the way the tested
parsers expect. No Claude needed: open a player's page in any browser, click
the bookmark, and it saves the page's career as zerozero_<id>.txt or
bdfutbol_<id>.txt (in Downloads). `create_legends.py --import-downloads`
then moves them into cache/.

Usage:  python3 bookmarklets/make.py    ->  bookmarklets/bookmarklets.html
"""
import html
import os
import re
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = os.path.join(os.path.dirname(HERE), "sources")

# what each bookmark appends to its extractor: name the file by the page's
# player id and hand it to the browser as a download
SAVE = {
    "zerozero": ("__zz", r"/(?:jogador|joueur|player|jugador|giocatore)/[^/]+/(\d+)", "zerozero_%s.txt",
                 "www.zerozero.pt/jogador/"),
    "bdfutbol": ("__bdf", r"/j/(j\d+)\.html", "bdfutbol_%s.txt", "www.bdfutbol.com/es/j/"),
}
# the extractors read one language's labels and values (Portuguese zerozero,
# Spanish bdfutbol); another language's page gives an empty profile, so the
# bookmark refuses it. bdfutbol's languages differ only in the path prefix
# (/en/j/, /ca/j/), so it opens the Spanish page for a second click.
LANGUAGE = {
    "zerozero": "if(location.hostname!=='www.zerozero.pt'){alert('Use the Portuguese site, www.zerozero.pt');return;}",
    "bdfutbol": "if(!location.pathname.startsWith('/es/')){alert('This bookmark reads the Spanish page. "
                "Opening it now: click the bookmark again there.');"
                "location.pathname=location.pathname.replace(/^\\/[a-z]{2}\\//,'/es/');return;}",
}


def body(name):
    """The extractor without its comments and its trailing console line."""
    src = open(os.path.join(SOURCES, "%s_extract.js" % name), encoding="utf-8").read()
    src = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("//"))
    var = SAVE[name][0]
    src = re.sub(r"\n\s*window\.%s\.[^\n]*\s*$" % var, "\n", src.rstrip() + "\n")
    return src.strip()


def bookmarklet(name):
    var, id_re, pattern, host = SAVE[name]
    save = (
        "(()=>{const m=location.pathname.match(/%s/);"
        "if(!m){alert('Not a %s player page');return;}"
        "%s"
        "const txt=window.%s;"
        "if(txt.split('\\n').filter(l=>/^\\d{4}/.test(l)).length===0)"
        "{if(!confirm('No career rows found on this page. Save anyway?'))return;}"
        "const a=document.createElement('a');"
        "a.href=URL.createObjectURL(new Blob([txt+'\\n'],{type:'text/plain;charset=utf-8'}));"
        "a.download='%s'.replace('%%s',m[1]);document.body.appendChild(a);a.click();a.remove();})();"
    ) % (id_re.replace("/", "\\/"), name, LANGUAGE[name], var, pattern)
    code = body(name) + "\n" + save
    # one line, then percent-encoded the way browsers expect a javascript: URL
    one_line = " ".join(l.strip() for l in code.splitlines() if l.strip())
    return "javascript:" + urllib.parse.quote(one_line, safe="()=,;:'!*/?&+@$[]{}<>|^~.-_")


def main():
    links = {n: bookmarklet(n) for n in SAVE}
    for n, js in links.items():
        open(os.path.join(HERE, "%s.bookmarklet.txt" % n), "w", encoding="utf-8").write(js + "\n")
    page = """<!doctype html><html><head><meta charset="utf-8"><title>FMPT bookmarklets</title>
<style>body{font:15px/1.5 -apple-system,sans-serif;max-width:720px;margin:40px auto;padding:0 16px}
a.bm{display:inline-block;padding:8px 14px;margin:6px 8px 6px 0;border-radius:6px;background:#2b6cb0;
color:#fff;text-decoration:none;font-weight:600}code{background:#eee;padding:1px 4px;border-radius:3px}</style>
</head><body><h1>FMPT Legends bookmarklets</h1>
<p>Drag each button to your bookmarks bar.</p>
%s
<h2>Use</h2><ol>
<li>Open a player's page: <code>%s...</code> or <code>%s...</code></li>
<li>Click the matching bookmark. It saves <code>zerozero_&lt;id&gt;.txt</code> or
<code>bdfutbol_&lt;id&gt;.txt</code> to your Downloads.</li>
<li>Run <code>/usr/bin/python3 creator/create_legends.py sheet.csv --import-downloads</code>:
the files move into <code>creator/cache/</code> and the batch reads them.</li></ol>
<p>A page with several career tables (veterans, futsal, coaching) is read as the batch expects;
those rows are dropped by the parser, not the bookmark.</p></body></html>""" % (
        "\n".join('<a class="bm" href="%s">FMPT %s</a>' % (html.escape(js, quote=True), n)
                  for n, js in links.items()),
        SAVE["zerozero"][3], SAVE["bdfutbol"][3])
    out = os.path.join(HERE, "bookmarklets.html")
    open(out, "w", encoding="utf-8").write(page)
    for n, js in links.items():
        print("%-9s %5d chars" % (n, len(js)))
    print("wrote", out)


if __name__ == "__main__":
    main()
