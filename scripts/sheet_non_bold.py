import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xlsx import Book

# The club tables hold staff in the same rows as the squad. A role is the staff
# member's, not a player's position, written loosely: "T. Adj", "T.Adj", "Adj.".
STAFF = {"t", "tadj", "adj", "pres", "vicepres", "dirdesp", "directord"}


def is_staff(role):
    return "".join(ch for ch in role.lower() if ch.isalnum()) in STAFF

def num(s):
    n = 0
    for ch in s:
        n = n * 26 + ord(ch) - 64
    return n

def letters(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s

b = Book(sys.argv[2] if len(sys.argv) > 2 else 'sheet.xlsx')
tab = sys.argv[1]
c = b.cells(tab)
get = lambda r, col: c.get((r, col), ("", False))

heads = sorted([(r, col) for (r, col), (t, _) in c.items() if t.strip() == "Posição"],
               key=lambda k: (k[0], num(k[1])))
blocks = []
for hr, pc in heads:
    pos, nam, pais = pc, letters(num(pc) + 1), letters(num(pc) + 2)
    club = get(hr - 1, pos)[0] or get(hr - 1, nam)[0]
    # the youth section starts at CAMADAS JOVENS; the main team is everything above it
    stop = min([r for (r, col), (t, _) in c.items()
                if col == pos and r > hr and "CAMADAS JOVENS" == t.strip().upper()] or [10 ** 6])
    rows = []
    for r in range(hr + 1, stop):
        name, bold = get(r, nam)
        role = get(r, pos)[0].strip()
        if name.strip() and not bold and not is_staff(role):
            rows.append((role, name.strip(), get(r, pais)[0]))
    blocks.append((club, hr, stop, rows))

total = sum(len(r[3]) for r in blocks)
print("# %s - main-team players not in bold\n" % tab)
print("_Staff rows (%s) are left out._\n" % ", ".join(sorted(STAFF)))
print("%d clubs, %d players\n" % (len(blocks), total))
for club, hr, stop, rows in blocks:
    print("## %s  _(rows %d-%d)_" % (club, hr + 1, stop - 1))
    if not rows:
        print("\n_none_\n")
        continue
    print("\n| Posição | Nome | País |\n|---|---|---|")
    for p, n, q in rows:
        print("| %s | %s | %s |" % (p, n, q))
    print()
