"""
Lexicon built from the application metadata and the semantic layer.

Every phrase the agent can recognise maps to an object that already exists in the app, such as a
filter value, a metric, a dimension or a page. Recognition is therefore grounded by construction.
"""
import re
from collections import defaultdict

from rapidfuzz import fuzz, process

from backend import catalog as C
from backend.semantic.layer import VIEWS

HINGLISH = [
    (r"\bpi?chh?le\s+mahi?ne\b", "last month"), (r"\bis\s+mahi?ne\b", "this month"),
    (r"\bpi?chh?le\s+saal\b", "last year"), (r"\bis\s+saal\b", "this year"),
    (r"\bpi?chh?le\s+hafte\b", "last week"), (r"\bpi?chh?la\s+quarter\b", "last quarter"),
    (r"\baaj\b", "today"), (r"\bkal\b", "yesterday"),
    (r"\b(dikhao|dikha do|dikhaiye|dikhana|dikha)\b", "show"), (r"\b(batao|bata do|bataiye|batana)\b", "tell me"),
    (r"\b(kitna|kitni|kitne)\b", "how much"), (r"\b(kyun|kyon|kyu|kiyu)\b", "why"),
    (r"\b(kaun sa|kaunsa|kon sa|konsa|kaun si|kaunsi)\b", "which"),
    (r"\b(sabse zyada|sabse jyada|sabse jada)\b", "highest"), (r"\bsabse kam\b", "lowest"),
    (r"\b(girawat|gir gaya|gir gayi|ghat gaya|ghat gayi|kam hua|kam hui|gira)\b", "drop"),
    (r"\b(badh gaya|badh gayi|badha|badhi|badhe)\b", "increase"),
    (r"\b(ke liye|keliye)\b", "for"), (r"\b(aur)\b", "and"), (r"\b(tulna|compare karo)\b", "compare"),
    (r"\b(kya|ka|ki|ke|mein|hai|tha|thi|ko|wala|wali|karo|kijiye)\b", " "),
]

# common words that must never be "typo-corrected" into vocabulary terms
STOP = set("""a an the and or of in on at to for from by with without vs versus is are was were be been being do does did
show me tell give what which who whom how why when where much many total all any each per this that these those it its
last past previous next this current month months year years week weeks day days quarter quarters today yesterday
than then also only just please can could would should will shall may might must let us our my your their i we you
top bottom best worst highest lowest high low more less most least over under up down into out about between since
until till before after during compare compared comparison trend trends change changed drop dropped dip fall fell
rise rose spike increase decrease increased decreased grow grew growth decline declined explain reason cause caused
open go take navigate page pages dashboard dashboards report reports view views screen chart charts table grid
filter filters set sort sorted order ordered rank ranked by asc desc ascending descending number numbers count
same now again instead still okay ok yes no not except excluding exclude other overall whole entire full
data value values look see find get pull bring switch jump launch visit clear reset remove undo back save export
download""".split())

COMMON_EN = set("""about other there their would could should these those which where while with from have been were what
when into than them then they this that show shown give make need want like look know year good well much many some such
only also just over most more less very even back same down high help here each made time next both case part work plan
goes went come came tell said says call fine sure okay kind sort type thing things drop dropped rise rising fell fall
falling jump jumped spike spiked explain happen happened going doing done please thanks thank great worse better total
overall numbers number figure figures value values breakdown split across among against compare compared versus between
including excluding except pages report reports screen table chart graph trend trends current previous latest recent
recently today tomorrow weekly monthly daily quarterly annual yearly period periods growth grown declined decline decrease
increase change changes changed impact affected affect driving driver drivers reason reasons cause causes caused because
higher lower biggest smallest largest highest lowest worst best since until before after during dashboard dashboards open
navigate filter filters sorted order ordered ranking rank ranked reset clear remove undo save export download view views
page hello namaste weather joke poem cricket score movie song write email delete update insert modify edit truncate drop
table database password admin login user users account accounts going gone getting lots really actually exactly maybe
something anything everything nothing someone happen whats thats dont doesnt didnt cant wont isnt arent wasnt werent
first second third fourth half full start started starting end ended ending around near nearly about approx roughly""".split())

VIEW_HINTS = {
    "sales": ["sales", "selling", "revenue", "commerce", "merchandise"],
    "delivery": ["delivery", "deliveries", "logistics", "shipping", "shipment", "fulfilment", "fulfillment", "last mile", "dispatch", "courier"],
    "inventory": ["inventory", "stock", "warehouse", "warehouses", "replenishment", "supply"],
    "marketing": ["marketing", "campaign", "campaigns", "ads", "advertising", "media", "promotion budget"],
    "support": ["support", "helpdesk", "help desk", "customer service", "service desk", "cx", "tickets", "complaints"],
    "customers": ["customer", "customers", "crm", "churn", "retention", "loyalty", "acquisition"],
}

# metric synonyms that are too generic to override a more specific metric in the same utterance
WEAK_METRIC_PHRASES = {"customers", "sales", "business", "inventory", "stock", "rating", "traffic", "visits", "views",
                       "volume", "delay", "delays", "reach", "on time", "conversion", "margin", "profit", "returns",
                       "income", "budget", "roi", "availability", "in stock", "sla"}


def norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("&", " and ").replace("%", " percent ")
    s = s.replace("'", "")
    s = re.sub(r"[^a-z0-9.\s/-]", " ", s)
    s = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", s)  # on-time -> on time
    s = re.sub(r"\s+", " ", s).strip()
    return s


def apply_hinglish(s: str) -> str:
    for rx, rep in HINGLISH:
        s = re.sub(rx, rep, s)
    return re.sub(r"\s+", " ", s).strip()


class Lexicon:
    def __init__(self, metadata):
        self.meta = metadata
        self.phrases = defaultdict(list)   # phrase -> [entry]
        self.max_len = 1
        self._build()
        self.vocab = sorted({tok for ph in self.phrases for tok in ph.split() if len(tok) >= 4 and tok not in STOP})

    def add(self, phrase, entry):
        p = norm(phrase)
        if not p:
            return
        if entry not in self.phrases[p]:
            self.phrases[p].append(entry)
        self.max_len = max(self.max_len, len(p.split()))

    def _build(self):
        # dimension values (+ synonyms + qualified forms like "south region")
        qualifiers = {"region": ["region", "zone"], "city": ["city"], "category": ["category", "categories"],
                      "channel": ["channel"], "segment": ["segment", "customers", "customer"], "warehouse": ["warehouse"],
                      "carrier": ["carrier", "courier"], "campaign": ["campaign", "sale"], "mkt_channel": ["ads", "channel"],
                      "issue_type": ["tickets", "issues", "complaints"], "priority": ["priority", "tickets"],
                      "product": []}
        for field, values in C.DIMENSION_VALUES.items():
            if field in ("retail_product", "customer_id", "br_state", "br_city", "olist_delivery_status", "order_status"): continue  # handled exactly in the active retail adapter
            for v in values:
                e = {"type": "value", "field": field, "value": v}
                self.add(v, e)
                for q in qualifiers.get(field, []):
                    self.add(f"{v} {q}", e)
                if field == "warehouse":
                    self.add(v.replace(" DC", " dc"), e)
                    self.add(v.replace(" DC", " distribution centre"), e)
            for syn, v in C.VALUE_SYNONYMS.get(field, {}).items():
                self.add(syn, {"type": "value", "field": field, "value": v})
        # metrics
        for view, spec in VIEWS.items():
            for m, md in spec["metrics"].items():
                e = {"type": "metric", "view": view, "metric": m}
                self.add(md["label"], e)
                self.add(m.replace("_", " "), e)
                for syn in md["synonyms"]:
                    ent = dict(e)
                    if norm(syn) in WEAK_METRIC_PHRASES:
                        ent["weak"] = True
                    self.add(syn, ent)
        # dimensions (for group-by)
        for field, syns in C.DIMENSION_SYNONYMS.items():
            for s in syns:
                self.add(s, {"type": "dim", "field": field})
        # view hints
        for view, words in VIEW_HINTS.items():
            for w in words:
                self.add(w, {"type": "view", "view": view})

    # ------------------------------------------------------------------
    def correct_typos(self, tokens):
        """Replace out-of-vocabulary tokens with close vocabulary tokens (rapidfuzz)."""
        out, fixes = [], []
        if not hasattr(self, "_all_tokens"):
            self._all_tokens = {tok for ph in self.phrases for tok in ph.split()}
        for t in tokens:
            if len(t) < 4 or t in STOP or t in self._all_tokens or not t.isalpha() or t in COMMON_EN:
                out.append(t)
                continue
            best = process.extractOne(t, self.vocab, scorer=fuzz.ratio)
            thr = 86 if len(t) >= 6 else 89
            if best and best[1] >= thr:
                out.append(best[0])
                fixes.append((t, best[0]))
            else:
                out.append(t)
        return out, fixes

    def match(self, text_masked):
        """Longest-first phrase matching. Returns list of hits with token spans."""
        tokens = text_masked.split()
        tokens, fixes = self.correct_typos(tokens)
        used = [False] * len(tokens)
        hits = []
        for n in range(min(self.max_len, len(tokens)), 0, -1):
            for i in range(0, len(tokens) - n + 1):
                if any(used[i:i + n]):
                    continue
                ph = " ".join(tokens[i:i + n])
                if ph in self.phrases:
                    hits.append({"phrase": ph, "start": i, "end": i + n, "entries": self.phrases[ph]})
                    for k in range(i, i + n):
                        used[k] = True
        hits.sort(key=lambda h: h["start"])
        return hits, tokens, fixes
