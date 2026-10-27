"""Fixes a person FM26 already has: his career is copied from FM26's own
playing history (`fm26_history`), cut before the prime season, shifted by the
offset, and written with the Rooney/Drogba method - Clear the grid, write it
fresh. The record is edited in place on its real DBID.

Written: Ptyp 1->2 (only for a non-player), a PErt Clear, a PPsT (past transfers) Clear, Pdob, Piap/Pigl,
Pird/Pirc (international retirement undone), Psnu cleared (a player moved to a new club),
Plhs, Pnph, Pdcn (days at club and nation), homegrown, contract. Never touched: names, nation, birthplace,
position, attributes, personality (user, 2026-10-08). CA, PA and the three
reputations only from the sheet's CA/PA/CR/HR/WR cells, when filled (user, 2026-10-13).
DOB and caps come from NFT (`urls`); without it both stay as FM26 has them.
"""
import json
import random
import xml.etree.ElementTree as ET

import build
import fm26_history
import model
import rebuild_lost_records as rlr
import repair_type_change as rtc
import convert_edition as c
import clean_import as ci

UID_SCALE = 4294967297


def person_doc(dbid):
    hits = build.search("fm_id:=%d" % dbid, by="name", q="*", n=1)
    return hits[0]["document"] if hits else {}


def _norm(t):
    import unicodedata
    t = unicodedata.normalize("NFKD", t or "")
    return "".join(ch for ch in t if ch.isalnum() and not unicodedata.combining(ch)).lower()


def find_person(name, nation, history, prime_season=None, target_club=None):
    """(DBID, note) for someone FM26 already has, staff or player, by name and
    nation. A name matches the index's name or any alias, accents ignored. More
    than one: the one whose FM26 career has the most league rows in the five
    seasons up to his prime wins (26 "Rui Costa"s, one played 1995-2000); a tie
    is refused with the candidates listed, never guessed."""
    want = _norm(name)
    nat = build.fm_nation(nation)
    found = {}
    for q in dict.fromkeys([name, name.split()[-1]]):
        for h in build.search("type_id:=person", by="name,search_terms", q=q, n=50):
            d = h["document"]
            names = [d.get("name")] + list(d.get("search_terms") or [])
            if d.get("fm_id", "").isdigit() and want in {_norm(x) for x in names}:
                found[int(d["fm_id"])] = d
    # someone FM26 already has AT the target club is the one, whatever nation
    # it files him under (Viseu's Messeguem, Kahraman and André Clóvis are all
    # "Portugal" there) - and it settles a namesake (Gustavo Costa)
    at_target = [d for d in found.values()
                 if target_club and int((d.get("team") or {}).get("fm_id") or 0) == target_club]
    if len(at_target) == 1:
        d = at_target[0]
        return int(d["fm_id"]), "matched %s at the target club (%s, FM26 id %s)" % (
            d["name"], d.get("classification_id"), d["fm_id"])
    pool = [d for d in found.values() if (d.get("nation") or {}).get("name") in (nat, None)]
    if len(pool) > 1 and prime_season:
        def era(d):
            return sum(1 for r in history.rows(int(d["fm_id"]))
                       if prime_season - 5 <= r["year"] <= prime_season and not r["ytht"])
        ranked = sorted(pool, key=era, reverse=True)
        if era(ranked[0]) > 0 and era(ranked[0]) > era(ranked[1]):
            pool = ranked[:1]
    if len(pool) > 1:
        sure = [d for d in pool if (d.get("nation") or {}).get("name") == nat]
        pool = sure if len(sure) == 1 else pool
    if not pool:
        return None, "no FM26 person named %r (%s)" % (name, nation)
    if len(pool) > 1:
        pool = pool[:6]
        return None, "%d+ FM26 people match %r, e.g. %s - add the id to the CSV" % (
            len(pool), name, ", ".join("%s %s (%s, %s)" % (d["fm_id"], d["name"], d.get("classification_id"),
                                       (d.get("team") or {}).get("name", "-")) for d in pool))
    d = pool[0]
    return int(d["fm_id"]), "matched %s (%s, FM26 id %s)" % (d["name"], d.get("classification_id"), d["fm_id"])


def future_move(hist, club, after):
    """True when FM26's history has him joining `club` after `after` (d, m, y),
    i.e. a transfer agreed for later in the season."""
    key = lambda d: (d[2], d[1], d[0])
    return any(r["club"] == club and r["join"] and key(r["join"]) > key(after) for r in hist)


def shift(d, offset):
    return (d[0], d[1], d[2] + offset) if d else None


def spells_from(kept, target_club, prime_season):
    """The creator's spell builder (runs, nested loans, 1/1 splits), then FM26's
    own join and leave dates laid over it wherever a row carries one - the
    database already chains them (Rangers left 1/10/1998, Salernitana joined
    1/10/1998). An open spell stays open."""
    rows = [model.Row(r["year"], r["club"], onln=r["onln"],
                      yror=r["yror"] if r["yror"] in (1, 2) else 0) for r in kept]
    spells = build.build_spells(rows, club_key=lambda r: r.club, target_club=target_club,
                                prime_season=prime_season, calendar=build.is_calendar_club)

    def season_of(d, club):
        return d[2] if build.is_calendar_club(club) or d[1] >= 7 else d[2] - 1
    for sp in spells:
        lo = season_of(sp["join"], sp["club"])
        hi = season_of(sp["left"], sp["club"]) if sp["left"] else 9999
        mine = [r for r in kept if r["club"] == sp["club"] and r["onln"] == sp["loan"]
                and lo <= r["year"] <= hi]
        if not mine:
            continue
        if mine[0]["join"]:
            sp["join"] = mine[0]["join"]
        if sp["left"] and mine[-1]["leaving"]:
            sp["left"] = mine[-1]["leaving"]
    return spells


def build_fix(row, out_xml):
    flags = []
    prime_season = int(row["prime_season"])
    hist_db = fm26_history.History()
    # --- target club, first: it also tells a namesake apart -----------------------
    tc = row["target_club"].strip()
    if tc.isdigit():
        target_id = int(tc)
    else:
        cache = build._club_cache()
        hit = build.club_for(tc, None, row.get("nation"), cache)
        build._club_cache_save(cache)
        if hit is None:
            raise SystemExit("target club %r did not resolve" % tc)
        target_id = hit["id"]
    if (row.get("dbid") or "").strip():
        dbid = int(row["dbid"])
    else:
        dbid, note = find_person(row["name"], row.get("nation"), hist_db, prime_season, target_id)
        if dbid is None:
            raise SystemExit(note)
        flags.append("Identity: " + note)
    uid = dbid * UID_SCALE
    target_season = int(row["target_season"])
    offset = target_season - prime_season
    rng = random.Random(uid)

    doc = person_doc(dbid)
    nation_dbid = (doc.get("nation") or {}).get("fm_id")
    hist = hist_db.rows(dbid)
    if not hist:
        raise SystemExit("%s: FM26 holds no playing history - use the creator instead" % row["name"])
    kept = [r for r in hist if r["year"] < prime_season]
    dropped = [r for r in hist if r["year"] >= prime_season]
    if not kept:
        # the season is his first in FM26: he starts at the target club with no
        # history before it (a youth player placed at his first club)
        flags.append("No FM26 season before %d/%02d: playing history written empty, one "
                     "open spell at the target club from that season." % (prime_season, (prime_season + 1) % 100))
    if any(r["trib"] for r in kept):
        flags.append("A kept row carries the tribunal tick, which is not written - set it by hand.")

    # --- sources: DOB and caps ----------------------------------------------
    nft_html, box, notes, zz_data = build.fetch_sources(row.get("urls") or [], row["name"])
    flags.extend(notes)
    dob, caps = None, None
    if nft_html:
        import sources.nft as nft
        dob = nft.dob(nft_html)
        caps = [0, 0]
        for date_str, g in nft.matches(nft_html):
            if tuple(int(x) for x in date_str.split("-")) < (prime_season, 7, 1):
                caps[0] += 1
                caps[1] += g
    if not dob and box:
        dob = box.get("dob")
    if not dob and zz_data:
        dob = zz_data.get("dob")
    if not dob and row.get("dob"):
        # the sheet's DOB column, for people no link or FM26 decode dates
        dob = row["dob"]
    if not dob:
        # no link gives one (a player listed by id alone): FM26's own date
        # (user, 2026-10-10), shifted like the rest
        import fm26_people
        dob = fm26_people.dob(dbid)
        if dob:
            flags.append("No DOB in the linked sources: FM26's own date of birth (%d/%d/%d) "
                         "used and shifted." % dob)
    if not dob:
        flags.append("No DOB in any source or in FM26: DOB left as FM26 has it, NOT shifted.")
    if caps is None:
        flags.append("No NFT page: caps before the prime unknown, Piap/Pigl left as FM26 has them.")
    if dob and kept:
        first_age = rtc.age_on_1_july(dob, kept[0]["year"])
        if first_age > 18:
            flags.append("FM26's history starts in %d/%02d, when he was %d - earlier seasons "
                         "are missing from the database." % (kept[0]["year"], (kept[0]["year"] + 1) % 100,
                                                            first_age))
    years = sorted({r["year"] for r in kept})
    for y in range(years[0], years[-1]) if years else ():
        if y not in years:
            flags.append("Hole in FM26's history: no row for %d/%02d." % (y, (y + 1) % 100))

    spells = (spells_from(kept, target_id, prime_season) if kept else
              [{"club": target_id, "join": (1, 7, prime_season), "left": None, "loan": False}])

    # --- ops, in the order the editor accepts -------------------------------
    ops = []
    is_non_player = doc.get("classification_id") != "player"
    # the index's team is the club he is contracted to, and that includes a
    # move already agreed for later in the season (user, 2026-10-22: Eduardo
    # Fereira, at La Guaira until 15/12/2025 with Caracas from 20/12/2025 -
    # the index says Caracas, the game starts him at La Guaira, so nothing
    # was moved). A move into the target club dated after the summer window
    # has not happened yet: he is not there.
    already_there = (int((doc.get("team") or {}).get("fm_id") or 0) == target_id
                     and not future_move(hist, target_id, (1, 10, target_season)))
    if is_non_player:
        # moved to the target club BEFORE the type change: the editor applies
        # ops in order, and a man on a women's team's staff cannot become a
        # player there (user, 2026-10-09: Vellisca at Logroño's women's side)
        if not already_there:
            ops.append(build.ref_op(uid, "Pcti", build.team_ref(target_id), "Ttea", rng))
        ops.append(rlr.type_change(uid, rng))
    # every fixed player's retirements are cleared, not only a converted
    # non-player's (user, 2026-10-22)
    ops.extend(build.retirement_ops(uid, rng))
    ops.extend(build.intl_retirement_ops(uid, rng))
    # and his past transfers (user, 2026-10-22)
    ops.append(build.past_transfers_clear(uid, rng))
    height = None
    if is_non_player:
        # a staff member made a player has no position and no height: the
        # sheet's position (user, 2026-10-08: Jorge Rosário) and the sources' height
        code = (row.get("position") or "").strip().upper()
        fourcc = build.CSV_POSITIONS.get(code)
        if fourcc:
            ops.append(build.int_op(uid, fourcc, 20, rng, odvl=0))
        else:
            flags.append("Converted from a non-player and the sheet gives no position code - set it by hand.")
        import sources.nft as nft_mod
        height = ((nft_mod.height(nft_html) if nft_html else None) or (box or {}).get("height")
                  or (zz_data or {}).get("height"))
        if height:
            ops.append(build.int_op(uid, "Phes", height, rng, odvl=0))
    if dob:
        ops.append(build.date_op(uid, "Pdob", shift(dob, offset), rng))
    if caps is not None:
        ops.append(build.int_op(uid, "Piap", caps[0], rng))
        ops.append(build.int_op(uid, "Pigl", caps[1], rng))
    r_ops, ratings_written = build.rating_ops(uid, row.get("ratings"), rng, flags)
    ops.extend(r_ops)

    plhs_rows = []
    for r in kept:
        pr = ci.new_row()
        pr["year"] = r["year"] + offset
        pr["yror"] = r["yror"]
        pr["club"] = build.team_ref(r["club"]) if r["club"] else None
        pr["divi"] = build.comp_ref(r["divi"]) if r["divi"] else None
        pr["apps"], pr["gols"] = r["apps"], r["gols"]
        pr["ytht"], pr["onln"] = r["ytht"], r["onln"]
        # FM26's own negative fee codes (-2) are refused by the editor, and the
        # row's later cells - join, leaving, club, division - then fail with it
        # (user, 2026-10-23: Pedro Ferreira's Varzim 2019/20). Only real fees go.
        pr["cash"] = (ET.Element("integer", value=str(r["cash"]))
                      if r["cash"] is not None and r["cash"] >= 0 else None)
        pr["join"] = build.date_el(shift(r["join"], offset)) if r["join"] else None
        pr["leaving"] = build.date_el(shift(r["leaving"], offset)) if r["leaving"] else None
        plhs_rows.append(pr)
    ops.extend(ci.emit_rows(uid, plhs_rows, build.BUILD))

    shifted_spells = [{"club": s["club"], "join": shift(s["join"], offset),
                       "left": shift(s["left"], offset), "loan": s["loan"]} for s in spells]
    ops.extend(build.emit_pnph(uid, shifted_spells, rng))

    nation_of = build.nation_resolver({r["club"]: r["divi"] for r in kept if r["club"] and r["divi"]})
    club_days, nation_days, unknown = build.days_at(shifted_spells, (1, 7, target_season), nation_of)
    for cl in unknown:
        flags.append("Club %s has no nation in the index: its days count for the club only." % cl)
    days_entries = list(club_days.items()) + list(nation_days.items())
    ops.extend(build.emit_pdcn(uid, days_entries, rng))

    hg_clubs, hg_nations, hg_fell_back = [], [], False
    if dob:
        hg_rows = [{"club": r["club"], "year": r["year"]} for r in kept]
        hg_clubs, hg_nations, hg_fell_back = rtc.home_grown(
            # the sheet's nation: the index's "nation" is his current club's
            # country (Emmanuel Boateng, at Hapoel Tel-Aviv, came out Israeli)
            hg_rows, dob, build._Namer({}), build.fm_nation(row.get("nation")))
        if hg_clubs:
            ops.extend(rtc.hg_ops(str(uid), "Phgc", rtc.HG_CLUB_COL, "Cclu", hg_clubs, build.BUILD, rng))
        nat_ids = rtc.nation_ids(hg_nations)
        hg_nation_ids = [nat_ids[n] for n in hg_nations if nat_ids.get(n)]
        if hg_nation_ids:
            ops.extend(rtc.hg_ops(str(uid), "Phgn", rtc.HG_NATION_COL, "Nnat", hg_nation_ids,
                                  build.BUILD, rng))
    else:
        flags.append("No DOB: homegrown not recomputed, FM26's own grids stand.")

    open_spell = next(s for s in shifted_spells if s["left"] is None)
    target_join = open_spell["join"]
    if already_there:
        # FM26 already has him at the target club: his real contract stays
        # (Viseu's current squad, prime = target season), but the day he
        # joined follows the rebuilt career (user, 2026-10-27)
        flags.append("Already at the target club in FM26: contract left as FM26 has it, "
                     "date joined moved to %d/%d/%d." % target_join)
        written = [build.date_op(uid, "Pcjd", target_join, rng)]
    elif not is_non_player:
        # (a converted non-player was moved before his type change)
        ops.append(build.ref_op(uid, "Pcti", build.team_ref(target_id), "Ttea", rng))
        # his squad number belongs to the club he leaves: cleared (user,
        # 2026-10-13); the Legends files null it the same way
        ops.append(build.scalar_op(uid, "Psnu", ET.Element("null"), rng))
    written, _ = (written, None) if already_there else c.sync_contract_dates(
        str(uid), {}, ET.fromstring('<date day="%d" month="%d" year="%d" time="0"/>' % target_join),
        build.BUILD, target_season, seasons=c.Seasons(build._names()),
        club=target_id)
    ops.extend(written)
    nation_joined = build.nation_join(shifted_spells, target_id, target_join, nation_of)
    ops.append(build.date_op(uid, "PCNj", nation_joined, rng))

    # achievements from the chosen season on go, like the playing history
    # (user, 2026-10-22: season 2009 with titles in 2005, 2008, 2013 keeps
    # 2005 and 2008): the grid is cleared and the earlier ones written back
    # as FM26 has them (real years - Pacl is not a shift target)
    import fm26_achievements as fa
    ach = fa.rows(dbid)
    def ach_season(a):
        return fa.season_of(a, bool(a["team"]) and build.is_calendar_club(a["team"]))
    ach_dropped = [a for a in ach if ach_season(a) >= prime_season]
    ach_kept = [a for a in ach if ach_season(a) < prime_season]
    if ach_dropped:
        ops.extend(achievement_ops(uid, ach_kept, rng))

    build.write_changeset(out_xml, ops)
    contract = {c.rec_prop(o): c.dtup(o.find("*[@id='new_value']")) for o in written}
    import verify
    checked = build.verify_output(out_xml, uid, plhs_rows, shifted_spells)
    checked["problems"] += verify.check_days(out_xml, uid, c.prop_id("Pdcn"), days_entries)
    return {
        "verify": checked,
        "uid": uid, "doc": doc, "offset": offset, "flags": flags, "kept": kept,
        "dropped": dropped, "spells": spells, "dob": dob, "caps": caps,
        "non_player": is_non_player, "hg_clubs": hg_clubs, "hg_nations": hg_nations, "nation_joined": nation_joined,
        "target_id": target_id, "target_join": target_join, "contract": contract,
        "club_days": club_days, "nation_days": nation_days,
        "row_position": (row.get("position") or "").strip().upper(), "height": height,
        "ratings": ratings_written, "ach_dropped": ach_dropped, "ach_kept": ach_kept,
        "already_there": already_there,
    }


def write_report(path, res, row):
    doc = res["doc"]
    fmt = lambda d: "%d/%d/%d" % d if d else "-"
    L = ["# %s - fix probe (FM26 DBID %s)" % (row["name"], row["dbid"]), "",
         "FM26 has him as **%s** at %s. Prime season %s, target %s at club %s, offset %+d years."
         % (doc.get("classification_id"), (doc.get("team") or {}).get("name", "-"),
            row["prime_season"], row["target_season"], res["target_id"], res["offset"]),
         "", "Record id: `%s` (DBID x 4294967297)" % res["uid"], "", "## Verification"]
    v = res["verify"]
    L.append("Replayed the written file: %d changes, %d playing-history rows, %d spells."
             % (v["changes"], v["plhs_rows"], v["spells"]))
    L += ["- FAIL: " + x for x in v["problems"]] or [
        "- PASS: every Plhs, Pnph and Pdcn op lands, the replayed grids equal the model, "
        "every change carries a db_random_id."]
    L += ["", "## Written"]
    if res["non_player"]:
        L.append("- Ptyp 1 -> 2, PErt cleared (non-player in FM26)")
    L.append("- Pdob: %s -> %s" % (fmt(res["dob"]), fmt(shift(res["dob"], res["offset"]))))
    if res["caps"] is not None:
        L.append("- Piap %d, Pigl %d (NFT, before 1/7/%s)" % (res["caps"][0], res["caps"][1],
                                                            row["prime_season"]))
    if res["ratings"]:
        L.append("- Ratings (sheet): " + ", ".join(res["ratings"]))
    if res["ach_dropped"]:
        L.append("- Achievements: %d from %s on removed (grid cleared), %d earlier ones written back"
                 % (len(res["ach_dropped"]), row["prime_season"], len(res["ach_kept"])))
    else:
        L.append("- Achievements: none from %s on, left as FM26 has them" % row["prime_season"])
    L.append("- Homegrown clubs %s, nations %s" % (res["hg_clubs"] or "none", res["hg_nations"] or "none"))
    if res.get("already_there"):
        L.append("- Contract: kept - FM26 already has him at club %s; Pcjd %s, PCNj %s"
                 % (res["target_id"], fmt(res["target_join"]), fmt(res["nation_joined"])))
    else:
      L.append("- Contract: Pcti %s, Pcjd %s, PCNj %s, %s" % (
        res["target_id"], fmt(res["target_join"]), fmt(res["nation_joined"]),
        ", ".join("%s %s" % (k, "/".join(v)) for k, v in sorted(res["contract"].items())
                  if k not in ("Pcjd", "PCNj"))))
    if not res["non_player"] and res["target_id"] != int((doc.get("team") or {}).get("fm_id") or 0):
        L.append("- Squad number (Psnu) cleared")
    L.append("- Past transfers (PPsT) cleared")
    L.append("- International retirement undone: Pird nulled, Pirc false; debut and first-goal dates (Pidd/Pigd) cleared")
    L.append("- Days (Pdcn, cleared, as of 1/7/%s): clubs %s; nations %s" % (
        row["target_season"], ", ".join("%s=%d" % kv for kv in res["club_days"].items()),
        ", ".join("%s=%d" % kv for kv in res["nation_days"].items())))
    L += ["", "## Career (FM26 rows kept, real years; the file adds %+d)" % res["offset"],
          "| year | order | club | division | apps | goals | youth | loan | fee | joined | left |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    show = lambda x: "-" if x is None else x
    for r in res["kept"]:
        L.append("| %d | %d | %d | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["year"], r["yror"], r["club"], show(r["divi"]), show(r["apps"]), show(r["gols"]),
            "x" if r["ytht"] else "", "x" if r["onln"] else "", show(r["cash"]),
            fmt(r["join"]), fmt(r["leaving"])))
    L.append("")
    L.append("Dropped (prime season and later): %d rows, %d to %d." % (
        len(res["dropped"]), res["dropped"][0]["year"], res["dropped"][-1]["year"])
        if res["dropped"] else "Dropped: none.")
    L += ["", "## Club spells (Pnph, real dates)"]
    for s in sorted(res["spells"], key=lambda s: s["join"][::-1]):
        L.append("- club %s%s: %s -> %s" % (s["club"], " (loan)" if s["loan"] else "",
                                            fmt(s["join"]), fmt(s["left"]) if s["left"] else "open"))
    flags = list(res["flags"])
    if res["non_player"]:
        flags.append("Converted from a non-player: position %s and height %s written; attributes "
                     "stay empty until set by hand." % (res["row_position"] or "-",
                                                         "%d cm" % res["height"] if res["height"] else "-"))
    L += ["", "## Flags"] + (["- " + f for f in flags] or ["- none"])
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")


# --- achievements (PACL) ---------------------------------------------------
ACH_COL = {"team": "1952801133", "competition": "1668246896", "date": "1684108389",
           "year": "2036687218", "plac": "1886151011", "ajob": "1634365282",
           "prom": "1886547821", "otea": "1869899105"}
VAL_ID = "1986096245"


def _ach_olvl(st):
    """The row as it stands, the editor's `olvl` for the next cell write."""
    o = ET.Element("record", id="olvl")
    ET.SubElement(o, "unsigned", id="id", value=build.OLVL_ID)
    for key, tag, col in (("team", "Ttea", ACH_COL["team"]), ("competition", "competition", ACH_COL["competition"])):
        if st[key] is None:
            ET.SubElement(o, "null", id=key)
        else:
            r = ET.SubElement(o, "record", id=key)
            ET.SubElement(r, "unsigned", id="id", value=col)
            ET.SubElement(r, "integer", id=tag, value=str(st[key]))
    ET.SubElement(o, "integer", id="plac", value=str(st["plac"]))
    if st["date"]:
        ET.SubElement(o, "date", id="date", day=str(st["date"][0]), month=str(st["date"][1]),
                      year=str(st["date"][2]), time="0")
    else:
        ET.SubElement(o, "null", id="date")
    for key in ("year", "ajob"):
        if st[key] is None:
            ET.SubElement(o, "null", id=key)
        else:
            ET.SubElement(o, "unsigned", id=key, value=str(st[key]))
    ET.SubElement(o, "boolean", id="prom", value="true" if st["prom"] else "false")
    if st["otea"] is None:
        ET.SubElement(o, "null", id="otea")
    else:
        r = ET.SubElement(o, "record", id="otea")
        ET.SubElement(r, "unsigned", id="id", value=ACH_COL["otea"])
        ET.SubElement(r, "integer", id="Ttea", value=str(st["otea"]))
    ET.SubElement(o, "boolean", id="wgps", value="false")
    return o


def achievement_ops(uid, rows, rng):
    """Clear the PACL grid and write `rows` back, one inserted row each, cell
    by cell - the shape the Legends files carry."""
    nv = ET.Element("record", id="new_value")
    ET.SubElement(nv, "unsigned", id="id", value=build.ROW_ID)
    ET.SubElement(nv, "integer", id="lsop", value="3")
    ops = [build.grid_wrap(uid, "Pacl", nv, rng)]
    for row in rows:
        nv = ET.Element("record", id="new_value")
        ET.SubElement(nv, "unsigned", id="id", value=build.ROW_ID)
        ET.SubElement(nv, "integer", id="lsop", value="0")
        ops.append(build.grid_wrap(uid, "Pacl", nv, rng))
        st = {"team": None, "competition": None, "plac": 1, "date": None, "year": None,
              "ajob": None, "prom": False, "otea": None}
        cells = [("team", row["team"]), ("competition", row["competition"]),
                 ("date", row["date"]) if row["date"] else ("year", row["year"]),
                 ("plac", row["plac"]), ("ajob", row["ajob"]), ("prom", row["prom"]),
                 ("otea", row["other_team"])]
        for key, val in cells:
            if val is None or (key == "plac" and val == 1) or (key == "prom" and not val):
                continue
            nv = ET.Element("record", id="new_value")
            ET.SubElement(nv, "unsigned", id="id", value=ACH_COL[key])
            if key in ("team", "otea", "competition"):
                v = ET.SubElement(nv, "record", id="value")
                ET.SubElement(v, "unsigned", id="id", value=VAL_ID)
                ET.SubElement(v, "integer", id="Ttea" if key != "competition" else "competition",
                              value=str(val))
            elif key == "date":
                ET.SubElement(nv, "date", id="value", day=str(val[0]), month=str(val[1]),
                              year=str(val[2]), time="0")
            elif key == "prom":
                ET.SubElement(nv, "boolean", id="value", value="true")
            else:
                ET.SubElement(nv, "integer", id="value", value=str(val))
            ET.SubElement(nv, "integer", id="lsop", value="1")
            nv.append(_ach_olvl(st))
            ops.append(build.grid_wrap(uid, "Pacl", nv, rng))
            st[{"otea": "otea"}.get(key, key)] = val
    return ops


RETIRE_DATE = (30, 6, 2024)


def build_retire(row, out_xml):
    """Team RET in the sheet (user, 2026-10-22): the person FM26 has is left
    without a club and gets one retirement, on 30/6/2024. Nothing else is
    written."""
    if not (row.get("dbid") or "").strip():
        raise SystemExit("%s: RET needs his FM26 id in the Exists column" % row["name"])
    dbid = int(row["dbid"])
    uid = dbid * UID_SCALE
    rng = random.Random(uid)
    doc = person_doc(dbid)
    team = int((doc.get("team") or {}).get("fm_id") or 0)
    ops = []
    if team:
        odvl = ET.Element("record")
        ET.SubElement(odvl, "unsigned", id="id", value="1868854892")
        ET.SubElement(odvl, "integer", id="Ttea", value=str(team))
        ops.append(build.scalar_op(uid, "Pcti", ET.Element("null"), rng, odvl))
    ops.extend(build.retirement_ops(uid, rng, RETIRE_DATE))
    build.write_changeset(out_xml, ops)
    # replay: the file parses and holds exactly the ops written
    written = ET.parse(out_xml).getroot().iter("record")
    n = sum(1 for r in written if r.find("integer[@id='database_table_type']") is not None)
    problems = [] if n == len(ops) else ["%d ops written, %d read back" % (len(ops), n)]
    flags = [] if team else ["FM26 has him at no club: only the retirement is written."]
    return {"verify": {"problems": problems, "changes": n}, "flags": flags, "uid": uid,
            "doc": doc, "team": team}


def write_retire_report(path, res, row):
    doc = res["doc"]
    L = ["# %s - retire (FM26 DBID %s)" % (row["name"], row["dbid"]), "",
         "FM26 has him as **%s** at %s." % (doc.get("classification_id"),
                                             (doc.get("team") or {}).get("name", "-")), "",
         "## Written",
         "- Pcti -> none (was %s)" % (res["team"] or "-"),
         "- PErt cleared, one retirement on %d/%d/%d" % RETIRE_DATE, "",
         "## Verification", "- " + ("FAIL: " + "; ".join(res["verify"]["problems"])
                                    if res["verify"]["problems"] else
                                    "PASS: %d changes read back" % res["verify"]["changes"]), "",
         "## Flags"] + (["- " + f for f in res["flags"]] or ["- none"])
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")
