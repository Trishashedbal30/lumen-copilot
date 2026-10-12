"""
Builds the labelled natural-language request corpus (intent + slot + destination + UI-state labels).

Labels are produced from the template slots themselves: the template "show {region} revenue {time}" is
labelled with page sales.regional.<region>, filter region=<region> and the date range of <time>.
The parser never produces these labels. Expected date ranges are computed here with independent
calendar arithmetic (today = 30 Sep 2026), not with the agent's time parser.

Output: eval/corpus/template.jsonl
Run:    python -m eval.build_corpus
"""
import json
import os
import random

from backend import catalog as C
from backend.data.generate_metadata import slug

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "eval", "corpus", "template.jsonl")
rnd = random.Random(7)

# (phrase, start, end) relative to today = 2026-09-30, computed by hand
TIMES = [
    ("last month", "2026-08-01", "2026-08-31"),
    ("in august", "2026-08-01", "2026-08-31"),
    ("for july 2026", "2026-07-01", "2026-07-31"),
    ("last quarter", "2026-04-01", "2026-06-30"),
    ("in Q1 2026", "2026-01-01", "2026-03-31"),
    ("for q3 2025", "2025-07-01", "2025-09-30"),
    ("this year", "2026-01-01", "2026-09-30"),
    ("year to date", "2026-01-01", "2026-09-30"),
    ("in the last 30 days", "2026-09-01", "2026-09-30"),
    ("over the past 7 days", "2026-09-24", "2026-09-30"),
    ("yesterday", "2026-09-29", "2026-09-29"),
    ("in 2025", "2025-01-01", "2025-12-31"),
    ("for FY26", "2025-04-01", "2026-03-31"),
    ("in march 2026", "2026-03-01", "2026-03-31"),
    ("from june to august", "2026-06-01", "2026-08-31"),
    ("since may 2026", "2026-05-01", "2026-09-30"),
    ("this month", "2026-09-01", "2026-09-30"),
    ("in H1 2026", "2026-01-01", "2026-06-30"),
]
MONTHS = [("july", "2026-07-01", "2026-07-31"), ("june", "2026-06-01", "2026-06-30"), ("may 2026", "2026-05-01", "2026-05-31"),
          ("august", "2026-08-01", "2026-08-31"), ("april", "2026-04-01", "2026-04-30"), ("march 2026", "2026-03-01", "2026-03-31")]

cases = []


def add(utt, intent, pages, filters=None, time=None, compare=None, sort=None, top_n=None, tags=None, kind="act"):
    cases.append({
        "id": f"t{len(cases)+1:04d}", "split": "template", "utterance": utt,
        "expected": {"intent": intent, "pages": pages, "filters": filters or {},
                     "date_range": ({"start": time[1], "end": time[2]} if time else None),
                     "compare": compare, "sort": sort, "top_n": top_n, "kind": kind},
        "tags": tags or [],
    })


def T():
    return rnd.choice(TIMES)


# ---- regional revenue ----
for r in C.REGIONS:
    for tpl in ["show {r} revenue {t}", "{r} region sales {t}", "how much revenue did the {r} region make {t}",
                "what was {r} zone turnover {t}", "{r} sales performance {t}"]:
        t = T()
        add(tpl.format(r=r if rnd.random() < .5 else r.lower(), t=t[0]), "lookup", [f"sales.regional.{slug(r)}"],
            {"region": [r]}, t, tags=["region"])
# ---- city ----
for city in C.CITIES:
    tpl = rnd.choice(["revenue in {c} {t}", "{c} sales {t}", "how did {c} do {t}", "show me {c} city revenue {t}"])
    t = T()
    add(tpl.format(c=city, t=t[0]), "lookup", [f"sales.city.{slug(city)}"], {"city": [city]}, t, tags=["city"])
# synonyms for cities
for alias, city in [("bangalore", "Bengaluru"), ("bombay", "Mumbai"), ("madras", "Chennai"), ("calcutta", "Kolkata"), ("cochin", "Kochi")]:
    t = T()
    add(f"{alias} revenue {t[0]}", "lookup", [f"sales.city.{slug(city)}"], {"city": [city]}, t, tags=["city", "synonym"])
# ---- channel ----
for ch, alias in [("Online Store", "website"), ("Mobile App", "app"), ("Retail Stores", "offline stores"), ("Marketplace", "marketplace")]:
    for name in (ch, alias):
        t = T()
        add(f"{name} revenue {t[0]}", "lookup", [f"sales.channels.{slug(ch)}"], {"channel": [ch]}, t, tags=["channel"])
# ---- category ----
for cat in C.CATEGORIES:
    t = T()
    add(rnd.choice(["{c} sales {t}", "how is {c} doing {t}", "revenue from {c} {t}"]).format(c=cat.lower(), t=t[0]), "lookup",
        [f"sales.categories.{slug(cat)}"], {"category": [cat]}, t, tags=["category"])
# ---- product ----
for p in C.PRODUCTS:
    t = T()
    add(rnd.choice(["how many {p} did we sell {t}", "{p} sales {t}", "units of {p} sold {t}"]).format(p=p.lower(), t=t[0]), "lookup",
        [f"sales.products.{slug(p)}"], {"product": [p]}, t, tags=["product"])
# ---- region x category ----
for _ in range(20):
    r, cat = rnd.choice(C.REGIONS), rnd.choice(C.CATEGORIES)
    t = T()
    add(rnd.choice(["{c} revenue in {r} {t}", "{r} {c} sales {t}", "show {c} sales for the {r} region {t}"]).format(c=cat.lower(), r=r, t=t[0]),
        "lookup", [f"sales.region_category.{slug(r)}_{slug(cat)}"], {"region": [r], "category": [cat]}, t, tags=["region_category"])
# ---- segment ----
for seg in C.SEGMENTS:
    t = T()
    add(f"sales from {seg.lower()} customers {t[0]}", "lookup", [f"sales.segments.{slug(seg)}"], {"segment": [seg]}, t, tags=["segment"])
# ---- rankings ----
for n in (3, 5, 10):
    t = T()
    add(f"top {n} cities by revenue {t[0]}", "lookup", ["sales.city.leaderboard"], {}, t, sort={"field": "revenue", "dir": "desc"}, top_n=n, tags=["rank"])
    t = T()
    add(f"top {n} products by revenue {t[0]}", "lookup", ["sales.products.top", "sales.products.grid"], {}, t, sort={"field": "revenue", "dir": "desc"}, top_n=n, tags=["rank"])
for r in rnd.sample(C.REGIONS, 3):
    t = T()
    add(f"which city in {r} had the highest revenue {t[0]}", "lookup", [f"sales.regional.{slug(r)}"], {"region": [r]}, t, tags=["rank"])
t = T()
add(f"which category has the best margin {t[0]}", "lookup", ["sales.categories.performance", "sales.overview.margin", "finance.profitability.category_margin"], {}, t, tags=["rank"])
# ---- delivery ----
for r in C.REGIONS:
    t = T()
    add(rnd.choice(["on-time delivery in {r} {t}", "{r} delivery performance {t}", "how punctual were deliveries in the {r} {t}"]).format(r=r, t=t[0]),
        "lookup", [f"ops.delivery.{slug(r)}"], {"region": [r]}, t, tags=["delivery"])
for cr in C.CARRIERS:
    t = T()
    add(f"on time % for {cr} {t[0]}", "lookup", [f"ops.carriers.{slug(cr)}"], {"carrier": [cr]}, t, tags=["delivery"])
for w in rnd.sample(C.WAREHOUSES, 4):
    t = T()
    add(f"late shipments from {w} {t[0]}", "lookup", [f"ops.warehouses.{slug(w)}"], {"warehouse": [w]}, t, tags=["delivery"])
# ---- inventory ----
for w in C.WAREHOUSES:
    t = T()
    add(rnd.choice(["stockouts at {w} {t}", "out of stock items in {w} {t}", "{w} inventory {t}"]).format(w=w, t=t[0]), "lookup",
        [f"inventory.warehouses.{slug(w)}"], {"warehouse": [w]}, t, tags=["inventory"])
for cat in rnd.sample(C.CATEGORIES, 4):
    t = T()
    add(f"{cat.lower()} stock availability {t[0]}", "lookup", [f"inventory.categories.{slug(cat)}"], {"category": [cat]}, t, tags=["inventory"])
# ---- marketing ----
for m in C.MKT_CHANNELS:
    t = T()
    add(rnd.choice(["{m} spend {t}", "how much did we spend on {m} {t}", "{m} roas {t}"]).format(m=m.lower(), t=t[0]), "lookup",
        [f"marketing.channels.{slug(m)}"], {"mkt_channel": [m]}, t, tags=["marketing"])
for name, s, e in rnd.sample(C.CAMPAIGNS, 5):
    add(f"show results of the {name} campaign", "lookup", [f"marketing.campaigns.{slug(name)}"], {"campaign": [name]}, None, tags=["marketing"])
for r in rnd.sample(C.REGIONS, 3):
    t = T()
    add(f"marketing spend in {r} {t[0]}", "lookup", [f"marketing.regions.{slug(r)}"], {"region": [r]}, t, tags=["marketing"])
# ---- customers ----
for seg in C.SEGMENTS:
    t = T()
    add(f"churn rate for {seg.lower()} customers {t[0]}", "lookup", [f"customers.segments.{slug(seg)}"], {"segment": [seg]}, t, tags=["customers"])
for r in rnd.sample(C.REGIONS, 3):
    t = T()
    add(f"{r} customer base {t[0]}", "lookup", [f"customers.regions.{slug(r)}"], {"region": [r]}, t, tags=["customers"])
t = T()
add(f"new customer acquisition {t[0]}", "lookup", ["customers.health.acquisition"], {}, t, tags=["customers"])
# ---- support ----
for it in C.ISSUE_TYPES:
    r = rnd.choice(C.REGIONS)
    t = T()
    add(f"{it.lower()} tickets in {r} {t[0]}", "lookup", [f"support.issues.{slug(it)}"], {"issue_type": [it], "region": [r]}, t, tags=["support"])
for r in rnd.sample(C.REGIONS, 3):
    t = T()
    add(f"csat in the {r} region {t[0]}", "lookup", [f"support.regions.{slug(r)}"], {"region": [r]}, t, tags=["support"])
# ---- navigation by page name ----
meta = json.load(open(os.path.join(ROOT, "data", "app_metadata.json"), encoding="utf-8"))
named = [pid for pid in meta["pages"] if not meta["pages"][pid].get("presets")]
for pid in rnd.sample(named, min(30, len(named))):
    p = meta["pages"][pid]
    tpl = rnd.choice(["open {t}", "take me to the {t}", "go to {t} page", "show me the {t} dashboard", "navigate to {t}"])
    add(tpl.format(t=p["title"].lower()), "lookup", [pid], {}, None, tags=["navigate"])
# ---- period comparisons ----
for r in rnd.sample(C.REGIONS, 4):
    a, b = rnd.sample(MONTHS, 2)
    if a[1] < b[1]:
        a, b = b, a
    add(f"compare {r} revenue in {a[0]} with {b[0]}", "compare", [f"sales.regional.{slug(r)}"], {"region": [r]}, a, compare="custom", tags=["compare"])
for r in rnd.sample(C.REGIONS, 3):
    m = rnd.choice(MONTHS)
    add(f"{r} revenue in {m[0]} vs last year", "compare", [f"sales.regional.{slug(r)}"], {"region": [r]}, m, compare="previous_year", tags=["compare"])
# ---- entity comparisons ----
comp_pages = ["sales.regional.comparison", "sales.overview.overview", "exec.dashboards.regional_overview", "sales.channels.mix",
              "sales.overview.revenue_trend", "finance.profitability.regional_profit", "finance.reports.annual", "finance.reports.monthly",
              "finance.reports.quarterly", "sales.city.leaderboard"]
for _ in range(6):
    r1, r2 = rnd.sample(C.REGIONS, 2)
    t = T()
    add(f"compare {r1} and {r2} revenue {t[0]}", "compare", comp_pages, {"region": sorted([r1, r2])}, t, tags=["entity_compare"])
for _ in range(3):
    c1, c2 = rnd.sample(C.CHANNELS, 2)
    t = T()
    add(f"{c1} vs {c2} revenue {t[0]}", "compare", comp_pages + ["sales.channels.mix"], {"channel": sorted([c1, c2])}, t, tags=["entity_compare"])
# ---- trends ----
for r in rnd.sample(C.REGIONS, 4):
    add(f"show the revenue trend in {r} over the last 6 months", "trend", [f"sales.regional.{slug(r)}", "sales.overview.revenue_trend"], {"region": [r]},
        ("", "2026-04-01", "2026-09-30"), tags=["trend"])
for r in rnd.sample(C.REGIONS, 3):
    add(f"how has on-time delivery in the {r} changed over the last 12 months", "trend", [f"ops.delivery.{slug(r)}"], {"region": [r]},
        ("", "2025-10-01", "2026-09-30"), tags=["trend"])
add("churn trend for premium customers this year", "trend", ["customers.segments.premium"], {"segment": ["Premium"]}, ("", "2026-01-01", "2026-09-30"), tags=["trend"])
# ---- sorting / configuration ----
for cat in rnd.sample(C.CATEGORIES, 3):
    t = T()
    add(f"{cat.lower()} sales {t[0]} sorted by margin", "lookup", [f"sales.categories.{slug(cat)}"], {"category": [cat]}, t,
        sort={"field": "margin_pct", "dir": "desc"}, tags=["sort"])
t = T()
add(f"top products by units {t[0]}", "lookup", ["sales.products.top", "sales.products.grid"], {}, t, sort={"field": "units", "dir": "desc"}, tags=["sort", "rank"])
# ---- exclusions ----
for cat in rnd.sample(C.CATEGORIES, 2):
    t = T()
    add(f"revenue excluding {cat.lower()} {t[0]}", "lookup", ["sales.overview.overview", "sales.overview.revenue_trend", "sales.categories.performance"],
        {"category": sorted(c for c in C.CATEGORIES if c != cat)}, t, tags=["exclude"])
# ---- why ----
for q in ["why did south revenue drop in august", "what caused the dip in south sales last month",
          "why did revenue spike in march 2026", "why did on-time delivery fall in the west in july",
          "why did churn go up in august", "what drove north beauty sales up in september"]:
    add(q, "why", [], {}, None, tags=["why"])
# ---- guardrails / special ----
for q in ["delete all the revenue data", "update the revenue figures for august to 50 crore", "drop table sales_daily"]:
    add(q, "refuse", [], {}, None, kind="refuse", tags=["guardrail"])
for q in ["show sales in surat", "revenue for nashik last month", "what about our london store"]:
    add(q, "clarify", [], {}, None, kind="clarify", tags=["unknown_entity"])
for q in ["show mobile sales last month", "how are mobile numbers looking"]:
    add(q, "clarify", [], {}, None, kind="clarify", tags=["ambiguous"])
for q in ["revenue for 2028", "orders in january 2024"]:
    add(q, "clarify", [], {}, None, kind="clarify", tags=["out_of_range"])
for q in ["what can you do", "help"]:
    add(q, "help", [], {}, None, kind="help", tags=["help"])

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    for c in cases:
        f.write(json.dumps(c) + "\n")
print(f"wrote {len(cases)} cases to {OUT}")
