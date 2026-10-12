"""
Hand-written evaluation sets, written separately from the templates.

  dev    : used while building the agent (bugs found here were fixed, so its numbers are optimistic)
  blind  : written before any evaluation run and NEVER used for tuning: the honest generalisation number
  dialog : multi-turn conversations; a dialogue succeeds only if every turn lands correctly

Label conventions: "pages" lists every acceptable destination (first = preferred). "filters" lists
required filter values; any extra filter on the target state must be a preset of the chosen page.
Dates are computed by hand with today = 30 Sep 2026.
Run: python -m eval.handwritten   (writes eval/corpus/{dev,blind,dialogues}.jsonl)
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUG = ("2026-08-01", "2026-08-31")
JUL = ("2026-07-01", "2026-07-31")
SEP = ("2026-09-01", "2026-09-30")
Q2 = ("2026-04-01", "2026-06-30")
YTD = ("2026-01-01", "2026-09-30")
QTD = ("2026-07-01", "2026-09-30")
L30 = ("2026-09-01", "2026-09-30")


def c(utt, intent, pages=(), filters=None, date=None, compare=None, sort=None, top_n=None, kind="act", tags=()):
    return {"utterance": utt, "expected": {"intent": intent, "pages": list(pages), "filters": filters or {},
            "date_range": {"start": date[0], "end": date[1]} if date else None, "compare": compare,
            "sort": sort, "top_n": top_n, "kind": kind}, "tags": list(tags)}


GEN = ["sales.overview.overview", "sales.overview.revenue_trend", "exec.dashboards.summary"]

DEV = [
    c("how's the business doing?", ["lookup"], ["exec.dashboards.summary", "sales.overview.overview", "exec.dashboards.scorecard"]),
    c("bengaluru numbers for last month", ["lookup"], ["sales.city.bengaluru"], {"city": ["Bengaluru"]}, AUG),
    c("app sales in the west this quarter", ["lookup"], ["sales.channels.mobile-app", "sales.regional.west"], {"channel": ["Mobile App"], "region": ["West"]}, QTD),
    c("Show me electronics in the south for august", ["lookup"], ["sales.region_category.south_electronics"], {"region": ["South"], "category": ["Electronics"]}, AUG),
    c("which warehouse had the most stockouts last quarter", ["lookup"], ["inventory.health.overview", "inventory.health.stockouts", "inventory.health.levels"], {}, Q2),
    c("delhivery late deliveries in july", ["lookup"], ["ops.carriers.delhivery"], {"carrier": ["Delhivery"]}, JUL),
    c("complaints about refunds in the south", ["lookup"], ["support.issues.refund"], {"issue_type": ["Refund"], "region": ["South"]}),
    c("what's our roas on instagram", ["lookup"], ["marketing.channels.social-media"], {"mkt_channel": ["Social Media"]}),
    c("diwali campaign results", ["lookup"], ["marketing.campaigns.diwali-dhamaka"], {"campaign": ["Diwali Dhamaka"]}),
    c("premium customer churn over the last 12 months", ["lookup", "trend"], ["customers.segments.premium"], {"segment": ["Premium"]}, ("2025-10-01", "2026-09-30")),
    c("kolkata sales yesterday", ["lookup"], ["sales.city.kolkata"], {"city": ["Kolkata"]}, ("2026-09-29", "2026-09-29")),
    c("open the p&l", ["lookup"], ["finance.profitability.pnl"]),
    c("take me to the carrier scorecard", ["lookup"], ["ops.carriers.scorecard"]),
    c("monthly business review", ["lookup"], ["exec.dashboards.mbr"]),
    c("revenue by channel last month", ["lookup"], ["sales.channels.mix", "sales.overview.overview", "sales.overview.orders_aov", "sales.overview.discounts"], {}, AUG),
    c("margin % for fashion this year", ["lookup"], ["sales.categories.fashion"], {"category": ["Fashion"]}, YTD),
    c("how many orders did pune get in june", ["lookup"], ["sales.city.pune"], {"city": ["Pune"]}, ("2026-06-01", "2026-06-30")),
    c("show grocery revenue in the east excluding retail stores", ["lookup"], ["sales.region_category.east_grocery"],
      {"region": ["East"], "category": ["Grocery"], "channel": ["Marketplace", "Mobile App", "Online Store"]}),
    c("top 10 skus by revenue this month", ["lookup"], ["sales.products.top", "sales.products.grid"], {}, SEP, top_n=10),
    c("avg delay for mumbai dc deliveries last month", ["lookup"], ["ops.warehouses.mumbai-dc"], {"warehouse": ["Mumbai DC"]}, AUG),
    c("chennai warehouse stock", ["lookup"], ["inventory.warehouses.chennai-dc"], {"warehouse": ["Chennai DC"]}),
    c("cpa for email campaigns", ["lookup"], ["marketing.channels.email"], {"mkt_channel": ["Email"]}),
    c("how many new customers in the north last quarter", ["lookup"], ["customers.regions.north"], {"region": ["North"]}, Q2),
    c("critical tickets this week", ["lookup"], ["support.service.priority_queue"], {"priority": ["Critical"]}, ("2026-09-28", "2026-09-30")),
    c("csat for damaged item complaints", ["lookup"], ["support.issues.damaged-item"], {"issue_type": ["Damaged Item"]}),
    c("compare july and august revenue for hyderabad", ["compare"], ["sales.city.hyderabad"], {"city": ["Hyderabad"]}, AUG, compare="custom"),
    c("why did revenue fall in the south last month", ["why"], [], {}, None, tags=["why"]),
    c("revenue trend for laptops in 2026", ["trend"], ["sales.products.laptops"], {"product": ["Laptops"]}, YTD),
    c("show women's apparel sales for q2", ["lookup"], ["sales.products.womens-apparel"], {"product": ["Women's Apparel"]}, Q2),
    c("sales for corporate clients this year", ["lookup"], ["sales.segments.corporate"], {"segment": ["Corporate"]}, YTD),
    c("can you delete last month's orders", ["refuse"], kind="refuse"),
    c("what is the weather in bengaluru", ["refuse", "clarify"], kind="refuse"),
    c("hi", ["greeting"], kind="greet"),
    c("revenue in tamil nadu", ["lookup"], ["sales.city.chennai"], {"city": ["Chennai"]}),
    c("gmv for marketplace last 30 days", ["lookup"], ["sales.channels.marketplace"], {"channel": ["Marketplace"]}, L30),
    c("best performing region on on-time delivery this year", ["lookup"], ["ops.delivery.overview"], {}, YTD),
    c("stock outs of smartphones", ["lookup"], ["inventory.health.stockouts", "inventory.categories.electronics", "inventory.health.overview", "inventory.health.levels"], {"product": ["Smartphones"]}),
    c("on time delivery for in-house fleet in august", ["lookup"], ["ops.carriers.in-house-fleet"], {"carrier": ["In-house Fleet"]}, AUG),
    c("how did the summer sale 2026 perform", ["lookup"], ["marketing.campaigns.summer-sale-2026"], {"campaign": ["Summer Sale 2026"]}),
    c("returns rate for fashion", ["lookup"], ["sales.overview.returns", "sales.categories.fashion"], {"category": ["Fashion"]}),
    c("discounts given on the marketplace channel last quarter", ["lookup"], ["sales.channels.marketplace", "sales.overview.discounts", "finance.profitability.discount_leakage"], {"channel": ["Marketplace"]}, Q2),
    c("shipments from kolkata dc in the last 7 days", ["lookup"], ["ops.warehouses.kolkata-dc"], {"warehouse": ["Kolkata DC"]}, ("2026-09-24", "2026-09-30")),
    c("nagpur warehouse inventory health", ["lookup"], ["inventory.warehouses.nagpur-dc"], {"warehouse": ["Nagpur DC"]}),
    c("lucknow aov last month", ["lookup"], ["sales.city.lucknow"], {"city": ["Lucknow"]}, AUG),
    c("how much did we spend on tv ads in 2025", ["lookup"], ["marketing.channels.tv"], {"mkt_channel": ["TV"]}, ("2025-01-01", "2025-12-31")),
    c("retention for regular customers", ["lookup"], ["customers.segments.regular"], {"segment": ["Regular"]}),
    c("payment issue tickets last month", ["lookup"], ["support.issues.payment-issue"], {"issue_type": ["Payment Issue"]}, AUG),
    c("pichle mahine mumbai ka revenue kitna tha", ["lookup"], ["sales.city.mumbai"], {"city": ["Mumbai"]}, AUG),
    c("electronics stock health", ["lookup"], ["inventory.categories.electronics"], {"category": ["Electronics"]}),
]

BLIND = [
    c("what did chennai bring in last month", ["lookup"], ["sales.city.chennai"], {"city": ["Chennai"]}, AUG),
    c("jaipur turnover for q1", ["lookup"], ["sales.city.jaipur"], {"city": ["Jaipur"]}, ("2026-01-01", "2026-03-31")),
    c("I need the west region numbers for september", ["lookup"], ["sales.regional.west"], {"region": ["West"]}, SEP),
    c("pull up the stock levels grid", ["lookup"], ["inventory.health.levels"]),
    c("where can I see campaign roi", ["lookup"], ["marketing.performance.roas", "marketing.performance.campaigns"]),
    c("average basket size on the app this year", ["lookup"], ["sales.channels.mobile-app"], {"channel": ["Mobile App"]}, YTD),
    c("how are sports products selling in central india", ["lookup"], ["sales.region_category.central_sports"], {"region": ["Central"], "category": ["Sports"]}),
    c("footwear units sold last 30 days", ["lookup"], ["sales.products.footwear"], {"product": ["Footwear"]}, L30),
    c("who delivers fastest, carrier wise", ["lookup"], ["ops.carriers.scorecard", "ops.delivery.overview", "ops.delivery.on_time", "ops.delivery.delays"]),
    c("late deliveries from ahmedabad dc in july", ["lookup"], ["ops.warehouses.ahmedabad-dc"], {"warehouse": ["Ahmedabad DC"]}, JUL),
    c("out-of-stock situation at bengaluru dc in august", ["lookup"], ["inventory.warehouses.bengaluru-dc"], {"warehouse": ["Bengaluru DC"]}, AUG),
    c("search ads cost per conversion last quarter", ["lookup"], ["marketing.channels.search-ads"], {"mkt_channel": ["Search Ads"]}, Q2),
    c("how did back to school do", ["lookup"], ["marketing.campaigns.back-to-school"], {"campaign": ["Back to School"]}),
    c("attrition among corporate customers", ["lookup"], ["customers.segments.corporate"], {"segment": ["Corporate"]}),
    c("customer acquisition in the east", ["lookup"], ["customers.regions.east", "customers.health.acquisition"], {"region": ["East"]}),
    c("tickets about late delivery in the west during july", ["lookup"], ["support.issues.delivery-delay"], {"issue_type": ["Delivery Delay"], "region": ["West"]}, JUL),
    c("resolution time for high priority tickets", ["lookup"], ["support.service.resolution", "support.service.overview", "support.service.volume"], {"priority": ["High"]}),
    c("zone-wise revenue for last month", ["lookup"], ["sales.regional.comparison", "sales.overview.overview", "exec.dashboards.regional_overview"], {}, AUG),
    c("list the 5 worst cities for on-time delivery this year", ["lookup"], ["ops.delivery.city_grid", "ops.delivery.delays"], {}, YTD, top_n=5),
    c("goa sales from 1st to 15th september", ["lookup"], ["sales.city.goa"], {"city": ["Goa"]}, ("2026-09-01", "2026-09-15")),
    c("revenue for the electronics category in hyderabad last month", ["lookup"], ["sales.city.hyderabad", "sales.region_category.south_electronics"], {"city": ["Hyderabad"], "category": ["Electronics"]}, AUG),
    c("sales of mens apparel in delhi", ["lookup"], ["sales.products.mens-apparel", "sales.city.delhi"], {"product": ["Men's Apparel"], "city": ["Delhi"]}),
    c("Show me how the mobile app did vs the website in august", ["compare"], ["sales.channels.mix", "sales.overview.overview", "sales.overview.orders_aov"], {"channel": ["Mobile App", "Online Store"]}, AUG),
    c("compare this year with last year for revenue", ["compare"], GEN + ["finance.reports.annual"], {}, YTD, compare="previous_year"),
    c("what happened to south revenue in august", ["why"], tags=["why"]),
    c("explain the drop in premium sales", ["why"], tags=["why"]),
    c("kochi ka revenue batao is mahine", ["lookup"], ["sales.city.kochi"], {"city": ["Kochi"]}, SEP),
    c("bhubaneswar orders last week", ["lookup"], ["sales.city.bhubaneswar"], {"city": ["Bhubaneswar"]}, ("2026-09-21", "2026-09-27")),
    c("how's delhi dc doing on dispatch", ["lookup"], ["ops.warehouses.delhi-dc"], {"warehouse": ["Delhi DC"]}),
    c("show the beauty stock health page", ["lookup"], ["inventory.categories.beauty"], {"category": ["Beauty"]}),
    c("facebook spend in the north", ["lookup"], ["marketing.channels.social-media", "marketing.regions.north"], {"mkt_channel": ["Social Media"], "region": ["North"]}),
    c("republic day sale 2026 campaign report", ["lookup"], ["marketing.campaigns.republic-day-sale-2026"], {"campaign": ["Republic Day Sale 2026"]}),
    c("churned customers in the south last quarter", ["lookup"], ["customers.regions.south"], {"region": ["South"]}, Q2),
    c("csat in the east for payment problems", ["lookup"], ["support.issues.payment-issue", "support.regions.east"], {"issue_type": ["Payment Issue"], "region": ["East"]}),
    c("revenue from b2b clients in 2025", ["lookup"], ["sales.segments.corporate"], {"segment": ["Corporate"]}, ("2025-01-01", "2025-12-31")),
    c("please erase the september numbers", ["refuse"], kind="refuse"),
    c("tell me a joke", ["refuse", "clarify"], kind="refuse"),
    c("sales in pondicherry", ["clarify"], kind="clarify"),
    c("show revnue for kolkatta", ["lookup"], ["sales.city.kolkata"], {"city": ["Kolkata"]}),
    c("inventry levels at mumbai warehouse", ["lookup"], ["inventory.warehouses.mumbai-dc"], {"warehouse": ["Mumbai DC"]}),
    c("what's the margin like for home and kitchen", ["lookup"], ["sales.categories.home-and-kitchen"], {"category": ["Home & Kitchen"]}),
    c("headphones revenue by channel", ["lookup"], ["sales.products.headphones"], {"product": ["Headphones"]}),
    c("which product sold the most units in the north last month", ["lookup"], ["sales.products.top", "sales.products.grid", "sales.regional.north"], {"region": ["North"]}, AUG),
    c("orders and aov for retail stores", ["lookup"], ["sales.channels.retail-stores"], {"channel": ["Retail Stores"]}),
    c("how did h1 2026 compare to h1 2025 for revenue", ["compare"], GEN + ["finance.reports.annual", "finance.reports.monthly"], {}, ("2026-01-01", "2026-06-30"), compare="custom"),
    c("south electronics", ["lookup"], ["sales.region_category.south_electronics"], {"region": ["South"], "category": ["Electronics"]}),
    c("bring up the regional profitability report", ["lookup"], ["finance.profitability.regional_profit"]),
    c("show me daily revenue for the past two weeks", ["lookup"], GEN + ["exec.dashboards.daily_pulse"], {}, ("2026-09-17", "2026-09-30")),
    c("average delay minutes for blue dart", ["lookup"], ["ops.carriers.bluedart"], {"carrier": ["BlueDart"]}),
]

DIALOGUES = [
    {"id": "d1", "turns": [
        c("show south revenue for august", ["lookup"], ["sales.regional.south"], {"region": ["South"]}, AUG),
        c("what about the north?", ["lookup"], ["sales.regional.north"], {"region": ["North"]}, AUG),
        c("compare it with july", ["compare"], ["sales.regional.north"], {"region": ["North"]}, AUG, compare="custom"),
        c("why did it change?", ["why"])]},
    {"id": "d2", "turns": [
        c("open the stockout monitor", ["lookup"], ["inventory.health.stockouts"]),
        c("only chennai dc", ["lookup"], ["inventory.health.stockouts", "inventory.warehouses.chennai-dc"], {"warehouse": ["Chennai DC"]}),
        c("last month", ["lookup"], ["inventory.health.stockouts", "inventory.warehouses.chennai-dc"], {"warehouse": ["Chennai DC"]}, AUG),
        c("sort by stockout days", ["lookup"], ["inventory.health.stockouts", "inventory.warehouses.chennai-dc"], {"warehouse": ["Chennai DC"]}, AUG, sort={"field": "stockout_days", "dir": "desc"})]},
    {"id": "d3", "turns": [
        c("on-time delivery in the west last quarter", ["lookup"], ["ops.delivery.west"], {"region": ["West"]}, Q2),
        c("and in july?", ["lookup"], ["ops.delivery.west"], {"region": ["West"]}, JUL),
        c("why did it drop", ["why"])]},
    {"id": "d4", "turns": [
        c("top 5 cities by revenue this year", ["lookup"], ["sales.city.leaderboard"], {}, YTD, top_n=5),
        c("only the app channel", ["lookup"], ["sales.city.leaderboard"], {"channel": ["Mobile App"]}, YTD),
        c("compare with last year", ["compare"], ["sales.city.leaderboard"], {"channel": ["Mobile App"]}, YTD, compare="previous_year")]},
    {"id": "d5", "turns": [
        c("churn rate for premium customers this year", ["lookup"], ["customers.segments.premium"], {"segment": ["Premium"]}, YTD),
        c("how about regular?", ["lookup"], ["customers.segments.regular"], {"segment": ["Regular"]}, YTD),
        c("compare with last year", ["compare"], ["customers.segments.regular"], {"segment": ["Regular"]}, YTD, compare="previous_year")]},
    {"id": "d6", "turns": [
        c("revenue for laptops last month", ["lookup"], ["sales.products.laptops"], {"product": ["Laptops"]}, AUG),
        c("in the south", ["lookup"], ["sales.products.laptops", "sales.region_category.south_electronics"], {"product": ["Laptops"], "region": ["South"]}, AUG),
        c("vs same month last year", ["compare"], ["sales.products.laptops", "sales.region_category.south_electronics"], {"product": ["Laptops"], "region": ["South"]}, AUG, compare="previous_year")]},
]


def write():
    d = os.path.join(ROOT, "eval", "corpus")
    os.makedirs(d, exist_ok=True)
    for name, rows in (("dev", DEV), ("blind", BLIND)):
        with open(os.path.join(d, f"{name}.jsonl"), "w", encoding="utf-8") as f:
            for i, r in enumerate(rows, 1):
                r = dict(r, id=f"{name[0]}{i:03d}", split=name)
                f.write(json.dumps(r) + "\n")
    with open(os.path.join(d, "dialogues.jsonl"), "w", encoding="utf-8") as f:
        for dl in DIALOGUES:
            f.write(json.dumps(dl) + "\n")
    print(f"dev={len(DEV)} blind={len(BLIND)} dialogues={len(DIALOGUES)}")


if __name__ == "__main__":
    write()
