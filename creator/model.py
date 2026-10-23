"""Data model for a created legend, before FM ids are resolved.

A `Row` is one Plhs season (or a blank youth row); a `Spell` is one Pnph stay
at a club, possibly nested inside another (a loan). Both carry REAL years -
`build.py` shifts them by the offset right before emitting.
"""


class Row:
    def __init__(self, year, club, apps=None, goals=None, level=None, yror=0,
                 onln=False, ytht=False, flag=None, nation=None):
        self.year = year          # real season start year
        self.club = club          # source club name, resolved later
        self.apps = apps          # None = blank (youth), 0 = a real 0-app season
        self.goals = goals
        self.level = level        # roman numeral division, or None
        self.yror = yror          # 0, 1 or 2 (two clubs sharing a season)
        self.onln = onln          # on loan
        self.ytht = ytht          # youth tick (blank row, age <= 18)
        self.flag = flag          # a report note, e.g. a source disagreement
        self.nation = nation      # the club's country as the source names it, or None

    def __repr__(self):
        return ("Row(%s %s apps=%s goals=%s level=%s yror=%s onln=%s ytht=%s)"
                % (self.year, self.club, self.apps, self.goals, self.level,
                   self.yror, self.onln, self.ytht))


class Spell:
    def __init__(self, club, join, left, loan=False, owner=None):
        self.club = club
        self.join = join          # (day, month, year) real
        self.left = left          # (day, month, year) real, or None if open
        self.loan = loan
        self.owner = owner        # owning club name, for a loan


class Profile:
    def __init__(self, name):
        self.name = name
        self.first = None
        self.last = None
        self.common = None
        self.full = None
        self.dob = None           # (day, month, year) real
        self.birthplace = None    # town name as a source writes it
        self.birth_country = None # country of birth, when a source names it
        self.height = None        # cm, when a source gives it
        self.nation = "Italy"
        self.position = None      # (label, abbr) from the source
        self.rows = []            # Row, real years, chronological
        self.spells = []          # Spell, real years, chronological
        self.caps = 0
        self.cap_goals = 0
        self.flags = []           # report lines
        self.homegrown_clubs = []
        self.homegrown_nations = []
