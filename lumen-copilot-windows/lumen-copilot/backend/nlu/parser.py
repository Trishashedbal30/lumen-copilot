"""
Rule-based natural-language understanding: utterance -> ParsedRequest (intent + slots).

This is the default, offline, deterministic path. An LLM planner (backend/agent/llm.py) can be enabled
on top. Both produce the same ParsedRequest, so validation and execution are identical either way.
"""
import re
from dataclasses import dataclass, field
from rapidfuzz.distance import DamerauLevenshtein
from typing import Dict, List, Optional

from backend import catalog as C
from backend.nlu import timeparse
from backend.nlu.lexicon import Lexicon, apply_hinglish, norm, STOP as LEX_STOP, COMMON_EN
from backend.semantic.layer import VIEWS

def normalize_monthly_average_terms(text, protected=()):
    """Correct nearby analytical words only inside an average-comparison request.

    Do not fuzzy-match arbitrary user entities, dates or identifiers.
    """
    if not re.search(r"\b(above|below|more than|less than|greater than|higher than|lower than|exceed(?:ed|s)?)\b", text):
        return text, []
    protected = set(protected) | COMMON_EN | LEX_STOP
    fixes = {}
    tokens = re.findall(r"\b[a-z]+\b", text)
    average = [t for t in tokens if t in ("average", "avg") or (t not in protected and 5 <= len(t) <= 9 and DamerauLevenshtein.distance(t, "average") <= 2)]
    month = []
    for token in tokens:
        if token in ("month", "months", "monthly"):
            month.append((token, token))
        elif token not in protected and 4 <= len(token) <= 8:
            ranked = sorted((DamerauLevenshtein.distance(token, word), word) for word in ("month", "months", "monthly"))
            if ranked[0][0] <= 1:
                nearest = [word for distance, word in ranked if distance == ranked[0][0]]
                corrected = "months" if token.endswith("s") and "months" in nearest else nearest[0]
                month.append((token, corrected))
    if not average or not month:
        return text, []
    for token in average:
        if token != "average": fixes[token] = "average"
    for token, corrected in month:
        if token != corrected: fixes[token] = corrected
    normalized = re.sub(r"\b[a-z]+\b", lambda match: fixes.get(match.group(0), match.group(0)), text)
    return normalized, list(fixes.items())


OTHER_CITIES = ["surat", "kanpur", "nashik", "coimbatore", "vizag", "visakhapatnam", "mysuru", "mysore", "madurai",
                "ranchi", "guwahati", "thiruvananthapuram", "trivandrum", "vadodara", "baroda", "ludhiana", "agra",
                "varanasi", "noida", "gurgaon", "gurugram", "mangalore", "mangaluru", "hubballi", "hubli", "belagavi",
                "belgaum", "dharwad", "raipur", "dehradun", "shimla", "srinagar", "amritsar", "jodhpur", "udaipur",
                "kota", "vijayawada", "tirupati", "nellore", "trichy", "salem", "thrissur", "kozhikode", "calicut",
                "aurangabad", "rajkot", "jabalpur", "gwalior", "meerut", "faridabad", "ghaziabad", "jamshedpur",
                "dhanbad", "cuttack", "siliguri", "durgapur", "asansol", "jammu", "london", "dubai", "singapore", "new york"]

SAFE_AFTER_IN = {"total", "detail", "details", "general", "short", "brief", "india", "summary", "aggregate", "overall",
                 "terms", "case", "particular", "future", "order", "line", "time", "place", "progress", "focus", "question",
                 "units", "rupees", "crores", "lakhs", "numbers", "percent", "percentage", "value", "volume"} | COMMON_EN

STATE_CITIES = {
    "karnataka": ["Bengaluru"], "tamil nadu": ["Chennai"], "telangana": ["Hyderabad"], "kerala": ["Kochi"],
    "maharashtra": ["Mumbai", "Pune", "Nagpur"], "gujarat": ["Ahmedabad"], "west bengal": ["Kolkata"],
    "odisha": ["Bhubaneswar"], "orissa": ["Bhubaneswar"], "bihar": ["Patna"], "rajasthan": ["Jaipur"],
    "uttar pradesh": ["Lucknow"], "madhya pradesh": ["Bhopal", "Indore"], "punjab": ["Chandigarh"], "haryana": ["Chandigarh"],
    "andhra pradesh": [], "assam": [], "jharkhand": [], "chhattisgarh": [], "uttarakhand": [], "himachal pradesh": [],
    "jammu and kashmir": [],
}

AMBIGUOUS_TERMS = {
    "mobile": [("channel", "Mobile App"), ("product", "Smartphones")],
    "watches": None,
}

INTENT_RX = [
    ("write_blocked", r"\b(delete|erase|wipe|purge|drop (the )?table|truncate|insert (into|new)|update the (data|revenue|numbers|figures|records)|"
                      r"modify (the )?data|change the (revenue|numbers|figures|data) to|edit (the )?(data|records)|set revenue to|overwrite)\b"),
    ("greeting", r"^(hi|hello|hey|hii+|namaste|good (morning|afternoon|evening)|yo)[\s!.]*$"),
    ("out_of_scope", r"\b(weather|joke|poem|song|recipe|cricket|football|movie|film|news|stock price|share price|bitcoin|crypto|"
                     r"translate|write (me )?an? (email|essay|story)|who is the (pm|prime minister|president|ceo of)|horoscope)\b"),
    ("undo", r"\b(undo|revert|go back|take me back|previous view|back to (the )?previous|back to where)\b"),
    ("reset", r"\b(reset|clear (all )?(the )?filters|remove all filters|start over|default view|clear everything)\b"),
    ("save_view", r"\b(save (this|the|my)? ?(view|filters|dashboard|layout|state)|bookmark (this|it)|set (this )?as (my )?default|pin this (view|page))\b"),
    ("export", r"\b(export|download)\b.*\b(csv|excel|data|grid|table|this|it|report)\b|\b(export|download) (it|this)\b"),
    ("help", r"\b(help|what can you do|how (do|can) i use (you|this)|what are your (capabilities|features)|who are you|what do you do)\b"),
    ("explain_page", r"\b(what (does|is) (this|the current) (page|dashboard|chart|report|screen|view)( show| about| for)?|"
                     r"explain (this|the current) (page|dashboard|chart|report|screen|view)|what am i looking at|describe (this|the) (page|dashboard|screen))\b"),
    ("why", r"\b(why|reason|reasons|root cause|cause|caused|causes|causing|what happened|what drove|what is driving|whats driving|"
            r"drivers?|driven by|explain (the |this |that )?(drop|dip|fall|decline|spike|jump|increase|decrease|change|surge|growth|rise)|"
            r"what explains|attribute|attribution|due to what|behind (the|this|that) (drop|dip|spike|jump|increase|decrease|change|surge|rise|fall|decline))\b"),
    ("trend", r"\b(trend|trends|trending|over time|trajectory|pattern|seasonality|how (has|have|did) .{0,40}(changed|moved|evolved|grown|trended|performed over)|growth trend|time series)\b"),
    ("compare", r"\b(compare|comparison|vs\.?|versus|v/s|against|difference between|relative to|benchmark|how (does|did) .{0,40} compare)\b"),
    ("navigate", r"\b(go to|goto|open|take me|navigate|bring up|pull up|switch to|jump to|launch|visit|where (can|do) i (see|find)|which (page|dashboard|report) (shows|has)|show me the .{0,40}(page|dashboard|report|screen|monitor|tracker|scorecard|overview|grid))\b"),
    ("configure", r"\b(filter|set (the )?(date|filter|range|period)|change (the )?(date|filter|range|period|sort)|apply|restrict|limit (it |this )?to|exclude|excluding|except|"
                  r"sort|sorted|order by|rank by|arrange|group by|show only|only show|just show|drill (down|into)|switch (it|this)? ?to|make it|add (a )?filter)\b"),
    ("query", r"\b(what (is|was|are|were|s)|whats|how (much|many)|tell me|give me|total|sum of|count of|number of|which|who|top|bottom|highest|lowest|best|worst|"
              r"most|least|did we|do we|are we|is the|was the|biggest|largest|smallest)\b"),
]
INTENT_RX = [(name, re.compile(rx)) for name, rx in INTENT_RX]

FOLLOWUP_RX = re.compile(r"^(and|what about|how about|same (for|with|but)|now|ok|okay|then|also|instead|only|just|but|for|in)\b|"
                         r"\b(it|that|this|those|them|same)\b")
SORT_RX = re.compile(r"\b(sort|sorted|order|ordered|rank|ranked|arrange|arranged)\b")
ASC_RX = re.compile(r"\b(asc|ascending|low to high|lowest first|smallest first|increasing order|bottom)\b")
TOPN_RX = re.compile(r"\b(top|bottom|best|worst|highest|lowest|leading|lagging|first|last)\s+(\d{1,3})\b")
TOPN_RX2 = re.compile(r"\b(\d{1,3})\s+(best|worst|highest|lowest|top|bottom|leading|lagging|biggest|smallest|largest)\b")
SUPERLATIVE_RX = re.compile(r"\b(highest|lowest|best|worst|most|least|top|bottom|biggest|largest|smallest|max|maximum|min|minimum|leading|lagging|poorest)\b")
EXCLUDE_RX = re.compile(r"\b(excluding|except|other than|apart from|without|not including|exclude|but not|leave out|ignoring)\b")
GENERIC_PAGE_WORDS = {"sales", "report", "performance", "dashboard", "overview", "page", "the"}


@dataclass
class ParsedRequest:
    text: str
    normalized: str = ""
    intent: str = "show"
    metrics: List[dict] = field(default_factory=list)
    view_hints: List[str] = field(default_factory=list)
    filters: Dict[str, List[str]] = field(default_factory=dict)
    excluded: Dict[str, List[str]] = field(default_factory=dict)
    group_by: List[str] = field(default_factory=list)
    time: Optional[timeparse.TimeParse] = None
    sort: Optional[dict] = None
    top_n: Optional[int] = None
    superlative: Optional[str] = None
    average_direction: Optional[str] = None
    page_mentions: List[tuple] = field(default_factory=list)
    ambiguities: List[dict] = field(default_factory=list)
    unknown_entities: List[str] = field(default_factory=list)
    typo_fixes: List[tuple] = field(default_factory=list)
    followup: bool = False
    has_page_word: bool = False
    clarification_question: Optional[str] = None
    clarification_options: List[dict] = field(default_factory=list)
    source: str = "rules"
    masked: str = ""

    def to_dict(self):
        d = dict(self.__dict__)
        d["time"] = timeparse.describe(self.time) if self.time else None
        return d

    @property
    def metric(self):
        return self.metrics[0] if self.metrics else None

    def entity_count(self):
        return len(self.metrics) + sum(len(v) for v in self.filters.values()) + len(self.group_by) + \
            (1 if self.time and self.time.main else 0) + len(self.page_mentions)


class RuleParser:
    def __init__(self, metadata):
        self.meta = metadata
        self.lex = Lexicon(metadata)
        self.page_phrases = []  # (normalized phrase, pid, weight)
        for pid, p in metadata["pages"].items():
            self.page_phrases.append((norm(p["title"]), pid, 1.0))
            for s in p.get("synonyms", []):
                self.page_phrases.append((norm(s), pid, 0.85))
        self.page_phrases.sort(key=lambda x: -len(x[0]))
        self.campaign_phrases = sorted({norm(c) for c in C.CAMPAIGN_NAMES if re.search(r"\d", c)}, key=len, reverse=True)

    # ------------------------------------------------------------------
    def parse(self, text: str, today=None) -> ParsedRequest:
        pr = ParsedRequest(text=text)
        raw = text.strip()
        s = norm(apply_hinglish(raw.lower()))
        s, analytical_fixes = normalize_monthly_average_terms(s, self.lex.vocab)
        pr.normalized = s

        # 1. time expressions (on normalized text), then mask them out
        protected = s
        for cname in self.campaign_phrases:
            if cname in protected:
                protected = protected.replace(cname, "#" * len(cname))
        tp = timeparse.parse(protected, today=today)
        pr.time = tp
        padded = " " + s + " "
        masked = list(padded)
        for a, b in tp.spans:
            for i in range(a, min(b, len(masked))):
                masked[i] = " "
        masked_s = re.sub(r"\s+", " ", "".join(masked)).strip()
        # mask comparison keywords so "last year" etc. never become entities
        masked_s = re.sub(r"\b(yoy|mom|qoq|wow)\b", " ", masked_s)
        pr.masked = masked_s

        # 2. phrase matching (with typo correction)
        hits, tokens, fixes = self.lex.match(masked_s)
        pr.typo_fixes = analytical_fixes + fixes
        corrected = " ".join(tokens)

        # 3. intent
        intent_text = s
        for name, rx in INTENT_RX:
            if rx.search(intent_text):
                pr.intent = name
                break
        else:
            pr.intent = "show"
        if pr.intent in ("query", "show", "navigate") and tp.comparison is not None:
            pr.intent = "compare"

        # 4. resolve entities
        metric_hits, value_hits, dim_hits = [], [], []
        strong_metric_present = any(any(e["type"] == "metric" for e in h["entries"])
                                    and not any(e["type"] == "value" for e in h["entries"]) for h in hits)
        for h in hits:
            entries = h["entries"]
            types = {e["type"] for e in entries}
            if "value" in types and "metric" in types:
                # e.g. "new customers" (segment vs metric), "delivery delay" (issue type vs metric)
                choose = "value" if strong_metric_present else "metric"
                entries = [e for e in entries if e["type"] == choose]
            for e in entries:
                if e["type"] == "metric":
                    metric_hits.append((h, e))
                elif e["type"] == "value":
                    value_hits.append((h, e))
                elif e["type"] == "dim":
                    dim_hits.append((h, e))
                elif e["type"] == "view":
                    if e["view"] not in pr.view_hints:
                        pr.view_hints.append(e["view"])

        # metrics: strong beat weak
        strong = [(h, e) for h, e in metric_hits if not e.get("weak")]
        chosen = strong if strong else metric_hits
        seen = set()
        for h, e in chosen:
            k = (e["view"], e["metric"])
            if k not in seen:
                seen.add(k)
                pr.metrics.append({"view": e["view"], "metric": e["metric"], "weak": bool(e.get("weak")), "phrase": h["phrase"]})
        if pr.metrics:
            # keep metrics consistent with the first metric's view where possible
            v0 = pr.metrics[0]["view"]
            same = [m for m in pr.metrics if m["view"] == v0]
            pr.metrics = same

        # exclusions
        excl_positions = [i for i, t in enumerate(tokens) if EXCLUDE_RX.match(t) or t in ("excluding", "except", "without", "exclude")]
        for i, t in enumerate(tokens):
            if t in ("other", "apart", "not", "but", "leave") and i + 1 < len(tokens) and tokens[i + 1] in ("than", "from", "including", "not", "out"):
                excl_positions.append(i + 1)

        for h, e in value_hits:
            fld, val = e["field"], e["value"]
            is_excl = any(0 <= h["start"] - p <= 3 for p in excl_positions)
            target = pr.excluded if is_excl else pr.filters
            target.setdefault(fld, [])
            if val not in target[fld]:
                target[fld].append(val)

        # group-by dims (ignore a dim word that just qualifies a value of the same field: "south region")
        value_ends = {(h["end"], e["field"]) for h, e in value_hits}
        for h, e in dim_hits:
            if (h["start"], e["field"]) in value_ends:
                continue
            if e["field"] not in pr.group_by:
                pr.group_by.append(e["field"])

        # 5. sort / top-n / superlatives
        sort_pos = next((i for i, t in enumerate(tokens) if SORT_RX.match(t)), None)
        if sort_pos is not None:
            after = [(h, e) for h, e in metric_hits + dim_hits if h["start"] > sort_pos]
            after.sort(key=lambda x: x[0]["start"])
            if after:
                h, e = after[0]
                fld = e["metric"] if e["type"] == "metric" else e["field"]
                pr.sort = {"field": fld, "dir": "asc" if ASC_RX.search(s) else "desc"}
                if e["type"] == "metric" and not any(m["metric"] == fld for m in pr.metrics):
                    pr.metrics.append({"view": e["view"], "metric": fld, "weak": False, "phrase": h["phrase"]})
                if e["type"] == "dim" and fld in pr.group_by and len(pr.group_by) > 0:
                    pass
            else:
                pr.sort = {"field": None, "dir": "asc" if ASC_RX.search(s) else "desc"}
        m = TOPN_RX.search(masked_s)
        m_b = TOPN_RX2.search(masked_s)
        if m:
            pr.top_n = int(m.group(2))
            pr.superlative = m.group(1)
        elif m_b:
            pr.top_n = int(m_b.group(1))
            pr.superlative = m_b.group(2)
        else:
            m2 = SUPERLATIVE_RX.search(masked_s)
            if m2:
                pr.superlative = m2.group(1)
                plural_dim = any(h["phrase"].endswith("s") or h["phrase"].endswith("ies") for h, e in dim_hits)
                if re.search(r"\b(top|bottom)\b", masked_s):
                    pr.top_n = 5 if plural_dim or not dim_hits else 5
                elif dim_hits and not plural_dim:
                    pr.top_n = 1

        # 6. page mentions (explicit names of pages)
        pc, ps = f" {corrected} ", f" {s} "
        for phrase, pid, w in self.page_phrases:
            if len(phrase) < 4:
                continue
            pp = f" {phrase} "
            if pp in pc or pp in ps:
                if any(pid == x[0] for x in pr.page_mentions):
                    continue
                score = w * min(1.0, 0.4 + 0.15 * len(phrase.split()))
                if set(phrase.split()) <= GENERIC_PAGE_WORDS:
                    continue
                pr.page_mentions.append((pid, round(score, 3), phrase))
        pr.page_mentions.sort(key=lambda x: -x[1])
        nav_rx = dict(INTENT_RX)["navigate"]
        if pr.page_mentions and pr.page_mentions[0][1] >= 0.7 and nav_rx.search(s) and pr.intent in ("trend", "compare", "show", "query"):
            pr.intent = "navigate"
        pr.has_page_word = bool(re.search(r"\b(page|dashboard|report|screen|monitor|tracker|scorecard|overview|grid|view)\b", s))

        # 7. ambiguity + unknown entities
        toks = s.split()
        for i, t in enumerate(toks):
            if t in AMBIGUOUS_TERMS and AMBIGUOUS_TERMS[t]:
                nxt = toks[i + 1] if i + 1 < len(toks) else ""
                if nxt not in ("app", "apps", "phones", "phone", "application"):
                    pr.ambiguities.append({"term": t, "options": [{"field": f, "value": v} for f, v in AMBIGUOUS_TERMS[t]]})
        for st_name, cities in STATE_CITIES.items():
            if re.search(r"\b" + st_name + r"\b", s):
                if cities:
                    pr.filters.setdefault("city", [])
                    for cty in cities:
                        if cty not in pr.filters["city"]:
                            pr.filters["city"].append(cty)
                    pr.state_mapped = (st_name.title(), cities)
                else:
                    pr.unknown_entities.append(st_name.title())
        # an unrecognised place after a location preposition ("sales in X") -> ask instead of guessing
        consumed = set()
        for h in hits:
            consumed.update(range(h["start"], h["end"]))
        for i, t in enumerate(tokens[:-1]):
            nxt = tokens[i + 1]
            if t in ("in", "at") and (i + 1) not in consumed and nxt.isalpha() and len(nxt) >= 4 \
                    and nxt not in LEX_STOP and nxt not in SAFE_AFTER_IN and not pr.unknown_entities and pr.metrics \
                    and (i + 2 >= len(tokens) or tokens[i + 2] in ("for", "last", "this", "during", "in", "and", "vs", "?")):
                pr.unknown_entities.append(nxt.title())
        for c in OTHER_CITIES:
            if re.search(r"\b" + re.escape(c) + r"\b", s):
                pr.unknown_entities.append(c.title())

        # 8. follow-up detection
        bare = not pr.metrics and not pr.page_mentions and not pr.view_hints and not pr.filters and not pr.excluded
        pr.explicit_followup = bool(FOLLOWUP_RX.search(masked_s))
        pr.followup = pr.explicit_followup or bare
        # A time-bucket extreme is a trend peak/trough, not a dimension ranking.
        bucket = re.search(r"\bwhich (?:calendar )?(month|week|quarter|year)\b", s)
        if bucket and pr.superlative and pr.intent in ("show", "query"):
            if bucket.group(1) == "year":
                pr.clarification_question = "Yearly chart buckets are not supported by the current UI. Choose monthly or quarterly revenue, or ask for a total in a specific year."
            else:
                pr.time.grain = bucket.group(1)
                pr.intent = "trend"
                pr.superlative = None
        if re.search(r"\b(yearly|annually)\b", s):
            pr.clarification_question = "Yearly chart buckets are not supported by the current UI. Choose monthly or quarterly revenue, or ask for a total in a specific year."
        # Do not silently substitute SUM for an unavailable statistical calculation.
        if re.search(r"\b(median|percentile|standard deviation|variance|correlation|forecast|predict|prediction)\b", s):
            pr.clarification_question = "This app supports recorded metric totals, trends, rankings, period comparisons and monthly-average comparisons. This statistical or predictive calculation is not supported."
        # Explicit time grain requests a series, even without the word 'trend'.
        if pr.intent in ('show', 'query') and pr.time.grain == 'month' and not pr.group_by and not pr.superlative and not pr.top_n and not any(phrase == norm(self.meta['pages'][pid]['title']) for pid, score, phrase in pr.page_mentions):
            pr.intent = 'trend'
        # Compare monthly totals with their arithmetic mean, rather than reading a KPI.
        if pr.intent in ("show", "query", "trend") and re.search(r"\b(month|months|monthly)\b", s) and re.search(r"\baverage\b", s):
            above = re.search(r"\b(above|more than|greater than|higher than|exceed(?:ed|s)?)\b", s)
            below = re.search(r"\b(below|less than|lower than)\b", s)
            if above or below:
                pr.average_direction = "above" if above else "below"
                pr.intent = "trend"
                pr.time.grain = "month"
                pr.group_by = []
        return pr
