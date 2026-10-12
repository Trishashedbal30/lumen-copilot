"""
Deterministic natural-language time parser (relative to the tenant's "today").

Handles: today/yesterday, last/past N days|weeks|months|quarters|years, this/last week|month|quarter|year,
MTD/QTD/YTD, month names (with or without year), quarters (Q3, Q3 2025, third quarter), halves (H1),
Indian financial years (FY26, FY 2025-26), explicit dates (1 Aug 2026, 2026-08-01, 01/08/2026),
ranges (from June to August, between 1 and 15 Aug, Jun-Aug), "since March", and comparisons
(vs last year, MoM, YoY, "compare August with July").
"""
import calendar
import os
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional

from backend import catalog as C

TODAY = date.fromisoformat(os.environ.get("LUMEN_TODAY", C.DATA_END.isoformat()))

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4,
    "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9,
    "sept": 9, "sep": 9, "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
MON_RE = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)"
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
             "ten": 10, "eleven": 11, "twelve": 12, "a": 1, "an": 1, "couple of": 2, "few": 3}
ORD = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "last": None}


@dataclass
class Range:
    start: date
    end: date
    label: str
    preset: Optional[str] = None
    span: tuple = (0, 0)

    def to_dict(self):
        d = {"start": self.start.isoformat(), "end": self.end.isoformat(), "label": self.label}
        if self.preset:
            d["preset"] = self.preset
        return d


@dataclass
class TimeParse:
    main: Optional[Range] = None
    comparison: Optional[Range] = None
    compare_mode: Optional[str] = None  # previous_period | previous_year | custom | none
    grain: Optional[str] = None
    spans: List[tuple] = field(default_factory=list)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def month_end(y, m):
    return date(y, m, calendar.monthrange(y, m)[1])


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def quarter_of(d):
    return (d.month - 1) // 3 + 1


def quarter_range(y, q):
    s = date(y, 3 * (q - 1) + 1, 1)
    return s, month_end(y, 3 * q)


def fy_range(fy_end_year):
    return date(fy_end_year - 1, 4, 1), date(fy_end_year, 3, 31)


def full_year(y):
    y = int(y)
    return y + 2000 if y < 100 else y


def latest_month(m, today=None):
    today = today or TODAY
    y = today.year if m <= today.month else today.year - 1
    return y


def fmt_range_label(s, e):
    if s == e:
        return s.strftime("%d %b %Y")
    if s.day == 1 and e == month_end(e.year, e.month):
        if s.year == e.year and s.month == e.month:
            return s.strftime("%b %Y")
        return f"{s.strftime('%b %Y')} – {e.strftime('%b %Y')}"
    return f"{s.strftime('%d %b %Y')} – {e.strftime('%d %b %Y')}"


def resolve_preset(preset, today=None):
    t = today or TODAY
    if preset.startswith("last_") and preset.endswith("_days"):
        n = int(preset.split("_")[1])
        return Range(t - timedelta(days=n - 1), t, f"Last {n} days", preset)
    if preset == "today":
        return Range(t, t, "Today", preset)
    if preset == "yesterday":
        y = t - timedelta(days=1)
        return Range(y, y, "Yesterday", preset)
    if preset == "this_week":
        s = t - timedelta(days=t.weekday())
        return Range(s, t, "This week", preset)
    if preset == "last_week":
        s = t - timedelta(days=t.weekday() + 7)
        return Range(s, s + timedelta(days=6), "Last week", preset)
    if preset in ("month_to_date", "this_month"):
        return Range(t.replace(day=1), t, f"{t.strftime('%b %Y')} (MTD)", "month_to_date")
    if preset == "last_month":
        s = add_months(t.replace(day=1), -1)
        return Range(s, month_end(s.year, s.month), s.strftime("%b %Y"), preset)
    if preset in ("quarter_to_date", "this_quarter"):
        q = quarter_of(t)
        s, _ = quarter_range(t.year, q)
        return Range(s, t, f"Q{q} {t.year} (QTD)", "quarter_to_date")
    if preset == "last_quarter":
        q = quarter_of(t) - 1
        y = t.year
        if q == 0:
            q, y = 4, y - 1
        s, e = quarter_range(y, q)
        return Range(s, e, f"Q{q} {y}", preset)
    if preset in ("year_to_date", "this_year"):
        return Range(date(t.year, 1, 1), t, f"{t.year} YTD", "year_to_date")
    if preset == "last_year":
        return Range(date(t.year - 1, 1, 1), date(t.year - 1, 12, 31), str(t.year - 1), preset)
    if preset == "last_12_months":
        s = add_months(t, -12) + timedelta(days=1)
        return Range(s, t, "Last 12 months", preset)
    if preset == "all_time":
        return Range(C.DATA_START, C.DATA_END, "All time", preset)
    raise ValueError(f"unknown preset {preset}")


def previous_period(r: Range) -> Range:
    """Same-length window immediately before r (calendar-aware for whole months/quarters/years)."""
    s, e = r.start, r.end
    if r.preset == "year_to_date":
        return previous_year(r)
    if r.preset == "quarter_to_date":
        ps = add_months(s, -3)
        pe = add_months(e, -3)
        return Range(ps, pe, fmt_range_label(ps, pe))
    if s.day == 1 and e == month_end(e.year, e.month):
        months = (e.year - s.year) * 12 + e.month - s.month + 1
        ps = add_months(s, -months)
        pe = month_end(add_months(s, -1).year, add_months(s, -1).month)
        return Range(ps, pe, fmt_range_label(ps, pe))
    # month-to-date style: compare with same days of previous month
    if s.day == 1 and r.preset in ("month_to_date",):
        ps = add_months(s, -1)
        pe = min(add_months(e, -1), month_end(ps.year, ps.month))
        return Range(ps, pe, fmt_range_label(ps, pe))
    n = (e - s).days + 1
    pe = s - timedelta(days=1)
    ps = pe - timedelta(days=n - 1)
    label = f"prev. {n} days" if n > 1 else fmt_range_label(ps, pe)
    return Range(ps, pe, label)


def previous_year(r: Range) -> Range:
    ps, pe = add_months(r.start, -12), add_months(r.end, -12)
    if r.end == month_end(r.end.year, r.end.month):
        pe = month_end(pe.year, pe.month)
    return Range(ps, pe, fmt_range_label(ps, pe))


# ---------------------------------------------------------------------------
# atomic expression scanners: each returns list of (start_idx, end_idx, Range, kind)
# kind: 'point' for things that can be range endpoints (dates, months, quarters), 'range' otherwise
# ---------------------------------------------------------------------------
def _num(tok):
    tok = tok.strip()
    if tok.isdigit():
        return int(tok)
    return NUM_WORDS.get(tok)


PATTERNS = []


def pattern(rx):
    def deco(fn):
        PATTERNS.append((re.compile(rx), fn))
        return fn
    return deco


@pattern(r"\b(?:the\s+)?(?:last|past|previous|prior|trailing)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|couple of|few)\s+(day|week|month|quarter|year)s?\b")
def _last_n(m, t):
    n = _num(m.group(1)) or 1
    unit = m.group(2)
    if unit == "day":
        return Range(t - timedelta(days=n - 1), t, f"Last {n} days", f"last_{n}_days" if n in (7, 30, 90) else None)
    if unit == "week":
        return Range(t - timedelta(days=7 * n - 1), t, f"Last {n} weeks")
    if unit == "month":
        if n == 12:
            return resolve_preset("last_12_months", t)
        if t == month_end(t.year, t.month):
            s = add_months(t.replace(day=1), -(n - 1))
        else:
            s = add_months(t, -n) + timedelta(days=1)
        return Range(s, t, f"Last {n} months")
    if unit == "quarter":
        s = add_months(t, -3 * n) + timedelta(days=1)
        return Range(s, t, f"Last {n} quarters")
    s = add_months(t, -12 * n) + timedelta(days=1)
    return Range(s, t, f"Last {n} years")


@pattern(r"\b(today|yesterday)\b")
def _today(m, t):
    return resolve_preset(m.group(1), t)


@pattern(r"\b(this|current|last|previous|prev|prior)\s+(week|month|quarter|qtr|year|fy|financial year|fiscal year)\b")
def _this_last(m, t):
    which, unit = m.group(1), m.group(2)
    last = which in ("last", "previous", "prev", "prior")
    if unit in ("fy", "financial year", "fiscal year"):
        cur_fy_end = t.year + 1 if t.month >= 4 else t.year
        s, e = fy_range(cur_fy_end - (1 if last else 0))
        if not last:
            e = t
        return Range(s, e, f"FY{str(cur_fy_end - (1 if last else 0))[2:]}" + ("" if last else " (to date)"))
    unit = "quarter" if unit == "qtr" else unit
    key = {("week", False): "this_week", ("week", True): "last_week", ("month", False): "month_to_date",
           ("month", True): "last_month", ("quarter", False): "quarter_to_date", ("quarter", True): "last_quarter",
           ("year", False): "year_to_date", ("year", True): "last_year"}[(unit, last)]
    return resolve_preset(key, t)


@pattern(r"\b(mtd|qtd|ytd|month[- ]to[- ]date|quarter[- ]to[- ]date|year[- ]to[- ]date)\b")
def _todate(m, t):
    k = m.group(1)
    if k.startswith("m"):
        return resolve_preset("month_to_date", t)
    if k.startswith("q"):
        return resolve_preset("quarter_to_date", t)
    return resolve_preset("year_to_date", t)


@pattern(r"\b(all time|all-time|entire history|full history|since (?:the )?(?:beginning|inception|launch))\b")
def _all(m, t):
    return resolve_preset("all_time", t)


@pattern(r"\bfy\s?'?(\d{2,4})(?:\s?[-/]\s?(\d{2,4}))?\b")
def _fy(m, t):
    a, b = m.group(1), m.group(2)
    end_year = full_year(b) if b else full_year(a)
    if b is None and len(a) == 4 and False:
        pass
    s, e = fy_range(end_year)
    return Range(s, e, f"FY{str(end_year)[2:]}")


@pattern(r"\b(?:q([1-4])|(first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter)(?:\s+(?:of\s+)?'?(\d{4}|\d{2})\b)?")
def _quarter(m, t):
    q = int(m.group(1)) if m.group(1) else ORD[m.group(2)]
    if m.group(3):
        y = full_year(m.group(3))
    else:
        y = t.year if quarter_range(t.year, q)[0] <= t else t.year - 1
    s, e = quarter_range(y, q)
    return Range(s, e, f"Q{q} {y}")


@pattern(r"\b(?:h([12])|(first|second)\s+half)(?:\s+(?:of\s+)?'?(\d{4}|\d{2})\b)?")
def _half(m, t):
    h = int(m.group(1)) if m.group(1) else (1 if m.group(2) == "first" else 2)
    if m.group(3):
        y = full_year(m.group(3))
    else:
        y = t.year if date(t.year, 1 if h == 1 else 7, 1) <= t else t.year - 1
    s = date(y, 1 if h == 1 else 7, 1)
    e = month_end(y, 6 if h == 1 else 12)
    return Range(s, e, f"H{h} {y}")


@pattern(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
def _iso(m, t):
    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return Range(d, d, d.strftime("%d %b %Y"))


@pattern(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})\b")
def _dmy(m, t):
    d = date(full_year(m.group(3)), int(m.group(2)), int(m.group(1)))  # Indian DD/MM/YYYY
    return Range(d, d, d.strftime("%d %b %Y"))


@pattern(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + MON_RE + r"\b(?:,?\s*'?(\d{4}|\d{2})\b)?")
def _day_mon(m, t):
    mon = MONTHS[m.group(2)]
    y = full_year(m.group(3)) if m.group(3) else latest_month(mon, t)
    d = date(y, mon, int(m.group(1)))
    return Range(d, d, d.strftime("%d %b %Y"))


@pattern(r"\b" + MON_RE + r"\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s*(\d{4})\b)?(?!\s*(?:days|weeks|months))")
def _mon_day(m, t):
    mon = MONTHS[m.group(1)]
    day = int(m.group(2))
    # "aug 26" could be Aug 2026: treat 2-digit >= 20 with no further year as a year when > 31 or followed by nothing? keep day
    if day > 31:
        return None
    y = int(m.group(3)) if m.group(3) else latest_month(mon, t)
    try:
        d = date(y, mon, day)
    except ValueError:
        return None
    return Range(d, d, d.strftime("%d %b %Y"))


@pattern(r"\b" + MON_RE + r"\b(?:\s*[,']?\s*'?(\d{4}|\d{2})\b)?")
def _month(m, t):
    name = m.group(1)
    if name == "may" and not m.group(2):
        # "may" is usually a verb; only accept when preceded by a time preposition
        pre = m.string[max(0, m.start() - 9):m.start()]
        if not re.search(r"(in|of|for|during|since|from|to|till|until|vs|and|than|with)\s+$", pre):
            return None
    if name == "mar" and not m.group(2):
        pre = m.string[max(0, m.start() - 9):m.start()]
        if not re.search(r"(in|of|for|during|since|from|to|till|until|vs|and)\s+$", pre):
            return None
    mon = MONTHS[name]
    y = full_year(m.group(2)) if m.group(2) else latest_month(mon, t)
    s = date(y, mon, 1)
    return Range(s, month_end(y, mon), s.strftime("%b %Y"))


@pattern(r"\b(?:in|for|during|of|year)\s+(20\d{2})\b|\b(20\d{2})\b")
def _year(m, t):
    y = int(m.group(1) or m.group(2))
    return Range(date(y, 1, 1), date(y, 12, 31), str(y))


GRAIN_RX = [
    (re.compile(r"\b(daily|day[- ]wise|day by day|per day|by day|each day|everyday)\b"), "day"),
    (re.compile(r"\b(weekly|week[- ]wise|per week|by week|each week|week on week|wow)\b"), "week"),
    (re.compile(r"\b(monthly|month[- ]wise|per month|by month|each month|month on month|mom|month over month)\b"), "month"),
    (re.compile(r"\b(quarterly|quarter[- ]wise|per quarter|by quarter|qoq|quarter over quarter)\b"), "quarter"),
]

CMP_PREV_YEAR = re.compile(r"\b(yoy|year[- ]over[- ]year|year on year|same (?:period|time|month|quarter) last year|"
                           r"(?:vs\.?|versus|compared? (?:to|with)|against|over|than) (?:the )?(?:previous|prior|last|same period last) year|"
                           r"last year's|previous year)\b")
CMP_PREV_PERIOD = re.compile(r"\b(mom|qoq|wow|month[- ]over[- ]month|month on month|quarter[- ]over[- ]quarter|week[- ]over[- ]week|"
                             r"(?:vs\.?|versus|compared? (?:to|with)|against|over|than) (?:the )?(?:previous|prior|preceding|last) (?:period|month|quarter|week)|"
                             r"previous period|prior period|preceding period|period over period)\b")
CMP_NONE = re.compile(r"\b(no comparison|without comparison|remove (?:the )?comparison|turn off comparison|hide comparison)\b")
RANGE_JOIN = re.compile(r"^\s*(?:to|till|until|through|thru|-|–|and)\s*$")
RANGE_LEAD = re.compile(r"(?:from|between)\s*$")
SINCE_LEAD = re.compile(r"(?:since|starting|starting from|after|from)\s*$")
UPTO_LEAD = re.compile(r"(?:till|until|up to|upto|before)\s*$")
CMP_JOIN = re.compile(r"(?:vs\.?|versus|v/s|compared (?:to|with)|compare(?:d)?|against|with|and|to|over|than)\s*(?:the\s+)?$")


def _scan(text, t):
    found = []
    taken = [False] * len(text)
    for rx, fn in PATTERNS:
        for m in rx.finditer(text):
            if any(taken[m.start():m.end()]):
                continue
            try:
                r = fn(m, t)
            except (ValueError, KeyError):
                r = None
            if r is None:
                continue
            r.span = (m.start(), m.end())
            found.append(r)
            for i in range(m.start(), m.end()):
                taken[i] = True
    found.sort(key=lambda r: r.span[0])
    return found


def parse(text: str, today: date = None) -> TimeParse:
    t = today or TODAY
    s = " " + text.lower().replace("’", "'") + " "
    out = TimeParse()
    for rx, g in GRAIN_RX:
        if rx.search(s):
            out.grain = g
            break

    atoms = _scan(s, t)
    # mark atoms that are only comparison phrases ("last year" inside "vs last year") so they are not main range
    merged = []
    i = 0
    while i < len(atoms):
        a = atoms[i]
        if i + 1 < len(atoms):
            b = atoms[i + 1]
            between = s[a.span[1]:b.span[0]]
            lead = s[max(0, a.span[0] - 10):a.span[0]]
            is_between = bool(RANGE_LEAD.search(lead))
            if RANGE_JOIN.match(between) and (between.strip() != "and" or is_between):
                # day-only start like "between 1 and 15 aug" handled by _day_mon on second atom only
                r = Range(a.start, b.end, fmt_range_label(a.start, b.end), span=(a.span[0], b.span[1]))
                if r.start > r.end:  # e.g. "nov to feb" -> previous year start
                    r.start = date(r.start.year - 1, r.start.month, r.start.day)
                    r.label = fmt_range_label(r.start, r.end)
                merged.append(r)
                i += 2
                continue
        lead = s[max(0, a.span[0] - 16):a.span[0]]
        if SINCE_LEAD.search(lead) and not RANGE_LEAD.search(lead[-9:]) or re.search(r"since\s*$", lead):
            a = Range(a.start, t, f"Since {a.label}", span=a.span)
        elif UPTO_LEAD.search(lead):
            a = Range(C.DATA_START, a.end, f"Up to {a.label}", span=a.span)
        merged.append(a)
        i += 1

    # numbers like "between 1 and 15 aug": first atom missing; handle "(\d+) (?:and|to|-) (\d+) mon"
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:and|to|till|until|-|–)\s*(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + MON_RE + r"\b(?:\s+(\d{4}))?", s)
    if m:
        mon = MONTHS[m.group(3)]
        y = int(m.group(4)) if m.group(4) else latest_month(mon, t)
        try:
            r = Range(date(y, mon, int(m.group(1))), date(y, mon, int(m.group(2))), "", span=(m.start(), m.end()))
            r.label = fmt_range_label(r.start, r.end)
            merged = [x for x in merged if not (x.span[0] >= m.start() and x.span[1] <= m.end())] + [r]
            merged.sort(key=lambda x: x.span[0])
        except ValueError:
            pass

    # comparison keywords
    cmp_year = CMP_PREV_YEAR.search(s)
    cmp_prev = CMP_PREV_PERIOD.search(s)
    if CMP_NONE.search(s):
        out.compare_mode = "none"

    # drop atoms that are part of a comparison keyword phrase
    def inside(r, mm):
        return mm and r.span[0] >= mm.start() - 1 and r.span[1] <= mm.end() + 1

    atoms2 = [r for r in merged if not inside(r, cmp_year) and not inside(r, cmp_prev)]
    if cmp_year:
        out.compare_mode = "previous_year"
    elif cmp_prev:
        out.compare_mode = "previous_period"

    if len(atoms2) == 1:
        a = atoms2[0]
        lead = s[max(0, a.span[0] - 30):a.span[0]]
        if re.search(r"\b(compared?|comparing|vs\.?|versus|against|relative)\b(\s+(it|this|that|them|these|those))?\s*(with|to|against)?\s*(the\s+)?$", lead):
            out.comparison = a
            out.compare_mode = "custom"
            out.spans = [r.span for r in merged]
            return out
    if atoms2:
        out.main = atoms2[0]
        if len(atoms2) > 1:
            a, b = atoms2[0], atoms2[1]
            between = s[a.span[1]:b.span[0]]
            lead = s[max(0, a.span[0] - 12):a.span[0]]
            if CMP_JOIN.search(between.strip() + " ") or re.search(r"\bcompare\b", lead) or re.search(r"\b(vs|versus|against|compared)\b", between):
                out.comparison = b
                out.compare_mode = "custom"
            else:
                # two unrelated ranges -> treat the later-mentioned as comparison only if text says compare
                if re.search(r"\b(compare|vs|versus|against|difference)\b", s):
                    out.comparison = b
                    out.compare_mode = "custom"
    if out.comparison is not None and out.main is not None and out.main.preset == "year_to_date" \
            and out.comparison.preset == "last_year":
        # "this year vs last year" means the same period last year, not all of last year
        out.comparison = None
        out.compare_mode = "previous_year"
    if out.comparison is not None and out.main is not None:
        # keep the most recent period as the main one, so deltas read as change over time
        if out.comparison.start > out.main.start:
            out.main, out.comparison = out.comparison, out.main
    # "how did august compare" -> no second range: default previous period handled downstream
    out.spans = [r.span for r in merged]
    return out


def describe(tp: TimeParse) -> dict:
    return {
        "main": tp.main.to_dict() if tp.main else None,
        "comparison": tp.comparison.to_dict() if tp.comparison else None,
        "compare_mode": tp.compare_mode,
        "grain": tp.grain,
    }


if __name__ == "__main__":
    tests = ["revenue last month", "south sales in august", "compare august with july", "q3 2025 revenue",
             "from june to august", "since march", "last 90 days vs previous period", "orders yoy for july",
             "ytd revenue", "fy26 revenue", "between 1 and 15 aug", "revenue in may 2026", "you may want revenue",
             "show me monthly trend for 2025", "last quarter", "this month", "yesterday", "1st jan 2026 to 31 mar 2026",
             "aug 2025 vs aug 2026", "h1 2026", "past 6 months", "how did september compare to last year",
             "revenue in mar", "nov to feb"]
    for x in tests:
        print(f"{x!r:45} -> {describe(parse(x))}")
