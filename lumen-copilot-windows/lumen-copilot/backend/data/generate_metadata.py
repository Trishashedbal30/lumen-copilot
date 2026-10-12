"""
Generates the no-code application metadata, i.e. what a platform like this would export:

  * navigation hierarchy (directories -> subdirectories -> pages)
  * page catalog with routes / deep links
  * widget catalog per page (KPI cards, line, bar, donut, grid) bound to semantic-layer views
  * filter / date-range / sort / top-N schemas per page
  * component type catalog and date presets

The frontend renders the entire app from this file, and the agent reasons over the same file.
There is one source of truth for both.

Run:  python -m backend.data.generate_metadata
"""
import json
import os
import re

from backend import catalog as C
from backend.semantic.layer import VIEWS

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "app_metadata.json")

DATE_PRESETS = [
    {"id": "last_7_days", "label": "Last 7 days"},
    {"id": "last_30_days", "label": "Last 30 days"},
    {"id": "last_90_days", "label": "Last 90 days"},
    {"id": "last_month", "label": "Last month"},
    {"id": "last_quarter", "label": "Last quarter"},
    {"id": "month_to_date", "label": "Month to date"},
    {"id": "quarter_to_date", "label": "Quarter to date"},
    {"id": "year_to_date", "label": "Year to date"},
    {"id": "last_12_months", "label": "Last 12 months"},
    {"id": "last_year", "label": "Last year"},
    {"id": "all_time", "label": "All time"},
]

COMPONENT_TYPES = {
    "kpi": {"label": "KPI Card", "props": ["metric", "view", "compare"], "description": "Single metric with change vs comparison period"},
    "line": {"label": "Line Chart", "props": ["metrics", "view", "time_grain"], "description": "Metric trend over time"},
    "bar": {"label": "Bar Chart", "props": ["metric", "dimension", "view", "limit"], "description": "Metric broken down by a dimension"},
    "donut": {"label": "Donut Chart", "props": ["metric", "dimension", "view"], "description": "Share / mix of a metric across a dimension"},
    "grid": {"label": "Data Grid", "props": ["metrics", "dimensions", "view", "sort", "top_n"], "description": "Sortable table of metrics by dimensions"},
}


def slug(s):
    s = s.lower().replace("&", "and").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


class Builder:
    def __init__(self):
        self.pages = {}
        self.dirs = []  # [{id,label,icon,subdirectories:[{id,label,pages:[]}]}]

    def directory(self, did, label, icon, description):
        d = {"id": did, "label": label, "icon": icon, "description": description, "subdirectories": []}
        self.dirs.append(d)
        return d

    def subdir(self, d, sid, label):
        s = {"id": f'{d["id"]}.{sid}', "label": label, "pages": []}
        d["subdirectories"].append(s)
        return s

    def page(self, d, s, key, title, view, description, kpis, breakdowns, presets=None, synonyms=None,
             date_preset="last_90_days", extra_widgets=None, grid_metrics=None, kind="dashboard",
             trend_metrics=None):
        pid = f'{s["id"]}.{key}'
        route = "/" + "/".join([slug(d["label"]), slug(s["label"]), slug(key)])
        widgets = []
        n = 0

        def wid():
            nonlocal n
            n += 1
            return f"{pid}.w{n}"

        for m in kpis:
            v, mm = (m if isinstance(m, tuple) else (view, m))
            widgets.append({"id": wid(), "type": "kpi", "view": v, "metric": mm,
                            "title": VIEWS[v]["metrics"][mm]["label"]})
        tm = trend_metrics or [kpis[0] if isinstance(kpis[0], str) else kpis[0][1]]
        tview = kpis[0][0] if isinstance(kpis[0], tuple) else view
        widgets.append({"id": wid(), "type": "line", "view": tview, "metrics": tm,
                        "title": f'{" & ".join(VIEWS[tview]["metrics"][x]["label"] for x in tm)} Trend'})
        prim = kpis[0] if isinstance(kpis[0], str) else kpis[0][1]
        if breakdowns:
            b0 = breakdowns[0]
            widgets.append({"id": wid(), "type": "bar", "view": view, "metric": prim, "dimension": b0, "limit": 12,
                            "title": f'{VIEWS[view]["metrics"][prim]["label"]} by {C.DIMENSION_LABELS[b0]}'})
        if len(breakdowns) > 1:
            b1 = breakdowns[1]
            widgets.append({"id": wid(), "type": "donut", "view": view, "metric": prim, "dimension": b1,
                            "title": f'{VIEWS[view]["metrics"][prim]["label"]} Mix by {C.DIMENSION_LABELS[b1]}'})
        for ew in extra_widgets or []:
            ew = dict(ew)
            ew["id"] = wid()
            widgets.append(ew)
        if breakdowns:
            gm = grid_metrics or [k if isinstance(k, str) else k[1] for k in kpis if (isinstance(k, str) or k[0] == view)]
            widgets.append({"id": wid(), "type": "grid", "view": view, "metrics": gm, "dimensions": [breakdowns[0]],
                            "title": f"{C.DIMENSION_LABELS[breakdowns[0]]} Details", "top_n": 25})

        # filters: dims shared by every widget's view
        views_used = {w["view"] for w in widgets}
        shared = [dm for dm in VIEWS[view]["dims"] if all(dm in VIEWS[v]["dims"] for v in views_used)]
        filters = [{"field": f, "label": C.DIMENSION_LABELS[f], "type": "multi_select",
                    "options": C.DIMENSION_VALUES[f]} for f in shared]
        grid = next((w for w in widgets if w["type"] == "grid"), None)
        sort_options = []
        if grid:
            sort_options = [{"field": m, "label": VIEWS[view]["metrics"][m]["label"]} for m in grid["metrics"]]
            sort_options += [{"field": dm, "label": C.DIMENSION_LABELS[dm]} for dm in grid["dimensions"]]
        presets = presets or {}
        default_state = {
            "filters": {k: [v] for k, v in presets.items()},
            "date_range": {"preset": date_preset},
            "compare": "previous_period",
            "sort": {"field": grid["metrics"][0], "dir": "desc"} if grid else None,
            "top_n": grid["top_n"] if grid else None,
            "grain": "auto",
        }
        page = {
            "id": pid, "title": title, "kind": kind, "route": route,
            "directory": d["id"], "subdirectory": s["id"],
            "breadcrumb": [d["label"], s["label"], title],
            "view": view, "description": description,
            "synonyms": synonyms or [], "presets": presets,
            "breakdowns": breakdowns,
            "primary_metrics": [k if isinstance(k, str) else k[1] for k in kpis],
            "filters": filters,
            "date_range": {"type": "date_range", "presets": [p["id"] for p in DATE_PRESETS], "default": date_preset},
            "compare_options": ["none", "previous_period", "previous_year"],
            "sort_options": sort_options,
            "top_n_options": [5, 10, 25, 50] if grid else [],
            "grain_options": ["auto", "day", "week", "month", "quarter"],
            "widgets": widgets,
            "default_state": default_state,
        }
        self.pages[pid] = page
        s["pages"].append(pid)
        return page


def build():
    b = Builder()
    S = "sales"
    sales_kpis = ["revenue", "orders", "aov", "margin_pct"]

    # ---------------- Executive ----------------
    d = b.directory("exec", "Executive", "briefcase", "Leadership dashboards spanning sales, operations, customers and support")
    s = b.subdir(d, "dashboards", "Leadership Dashboards")
    b.page(d, s, "summary", "Executive Summary", S,
           "Company-wide headline KPIs: revenue, orders, on-time delivery, CSAT and churn with trend and regional split.",
           ["revenue", "orders", ("delivery", "on_time_pct"), ("support", "csat"), ("customers", "churn_rate")],
           ["region"], synonyms=["home", "ceo dashboard", "leadership view", "company overview", "main dashboard", "kpi summary", "headline numbers",
                     "business overview", "how is the business doing", "hows the business doing", "how are we doing", "overall business"])
    b.page(d, s, "scorecard", "Company Scorecard", S,
           "Balanced scorecard of growth, profitability, fulfilment and customer health metrics.",
           ["revenue", "margin_pct", ("delivery", "on_time_pct"), ("customers", "retention_rate")],
           ["region"], synonyms=["balanced scorecard", "health check", "business health"])
    b.page(d, s, "mbr", "Monthly Business Review", S,
           "Monthly business review pack: last month's revenue, margin, orders and returns versus the previous month.",
           ["revenue", "gross_margin", "orders", "return_rate"], ["region", "category"], date_preset="last_month",
           synonyms=["mbr", "monthly review", "month end review", "monthly report pack"], kind="report")
    b.page(d, s, "regional_overview", "Regional Performance Overview", S,
           "Side-by-side performance of North, South, East, West and Central regions across sales and delivery.",
           ["revenue", "orders", ("delivery", "on_time_pct"), ("support", "tickets")], ["region"],
           synonyms=["region comparison", "zone performance", "all regions"])
    b.page(d, s, "daily_pulse", "Daily Pulse", S,
           "Day-by-day pulse of revenue and orders for the last 7 days.",
           ["revenue", "orders", "aov"], ["channel", "region"], date_preset="last_7_days",
           synonyms=["daily dashboard", "yesterday", "today's numbers", "daily sales", "pulse"])

    # ---------------- Sales ----------------
    d = b.directory("sales", "Sales", "trending-up", "Revenue, orders, margin and returns across regions, channels, categories and products")
    s = b.subdir(d, "overview", "Sales Overview")
    b.page(d, s, "overview", "Sales Overview", S, "Overall sales performance: revenue, orders, AOV and margin with trend and breakdowns by region and channel.",
           sales_kpis, ["region", "channel"], synonyms=["sales dashboard", "sales summary", "revenue dashboard", "sales home"])
    b.page(d, s, "revenue_trend", "Revenue Trend", S, "Revenue over time with growth versus the previous period and the previous year.",
           ["revenue", "orders"], ["region", "category"], date_preset="last_12_months",
           synonyms=["revenue over time", "sales trend", "growth trend", "revenue growth", "sales over time"])
    b.page(d, s, "orders_aov", "Orders & AOV", S, "Order volume, units and average order value (basket size) by channel and region.",
           ["orders", "aov", "units"], ["channel", "region"], trend_metrics=["orders"],
           synonyms=["order volume", "basket size", "average order value", "aov dashboard"])
    b.page(d, s, "margin", "Margin Analysis", S, "Gross margin and margin % by category and region to spot profitability issues.",
           ["gross_margin", "margin_pct", "revenue"], ["category", "region"], synonyms=["profitability", "profit analysis", "gross margin report"])
    b.page(d, s, "discounts", "Discounts & Promotions", S, "Discount spend and discount depth by channel and category, including campaign periods.",
           ["discount", "discount_pct", "revenue"], ["channel", "category"], synonyms=["promotions", "markdowns", "promo analysis", "discount report"])
    b.page(d, s, "returns", "Returns Analysis", S, "Returns volume and return rate by category, region and channel.",
           ["return_rate", "returns", "orders"], ["category", "region"], synonyms=["rto", "returns report", "return rate dashboard", "product returns"])

    s = b.subdir(d, "regional", "Regional Sales")
    b.page(d, s, "comparison", "Regional Sales Comparison", S, "Compare revenue, orders and margin across all five regions.",
           sales_kpis, ["region", "channel"], synonyms=["region vs region", "compare regions", "zone comparison", "regional sales"])
    for r in C.REGIONS:
        b.page(d, s, slug(r), f"{r} Region Sales", S,
               f"Sales performance for the {r} region ({', '.join(C.REGION_CITIES[r])}): revenue, orders, AOV and margin by city and category.",
               sales_kpis, ["city", "category"], presets={"region": r},
               synonyms=[f"{r.lower()} zone", f"{r.lower()} sales", f"{r.lower()} region", f"{r.lower()} india sales"])

    s = b.subdir(d, "city", "City Performance")
    b.page(d, s, "leaderboard", "City Leaderboard", S, "All 18 cities ranked by revenue, orders, AOV and margin.",
           sales_kpis, ["city", "region"], synonyms=["city ranking", "city wise sales", "sales by city", "top cities", "city comparison"])
    for city in C.CITIES:
        b.page(d, s, slug(city), f"{city} Sales", S,
               f"City-level sales for {city} ({C.CITY_REGION[city]} region): revenue, orders and AOV by channel and category.",
               ["revenue", "orders", "aov"], ["category", "channel"], presets={"city": city},
               synonyms=[f"{city.lower()} city", f"{city.lower()} store sales"])

    s = b.subdir(d, "channels", "Channels")
    b.page(d, s, "mix", "Channel Mix", S, "Revenue and orders split across Online Store, Mobile App, Retail Stores and Marketplace.",
           sales_kpis, ["channel", "region"], synonyms=["channel performance", "omnichannel", "online vs offline", "channel split"])
    for ch in C.CHANNELS:
        b.page(d, s, slug(ch), f"{ch} Performance", S, f"Sales through the {ch} channel by region and category.",
               sales_kpis, ["region", "category"], presets={"channel": ch}, synonyms=[f"{ch.lower()} sales", f"{ch.lower()} channel"])

    s = b.subdir(d, "categories", "Categories")
    b.page(d, s, "performance", "Category Performance", S, "Revenue, margin and returns across all product categories.",
           ["revenue", "orders", "margin_pct", "return_rate"], ["category", "region"],
           synonyms=["category sales", "category wise sales", "all categories", "merchandise performance"])
    for cat in C.CATEGORIES:
        b.page(d, s, slug(cat), f"{cat} Category Sales", S, f"{cat} category sales by product and region: revenue, orders, margin.",
               ["revenue", "orders", "margin_pct"], ["product", "region"], presets={"category": cat},
               synonyms=[f"{cat.lower()} sales", f"{cat.lower()} category", f"{cat.lower()} revenue"])

    s = b.subdir(d, "products", "Products")
    b.page(d, s, "top", "Top Products", S, "Best-selling products ranked by revenue, with orders, units and margin.",
           ["revenue", "orders", "units", "margin_pct"], ["product", "category"], date_preset="last_30_days",
           synonyms=["best sellers", "top selling products", "top skus", "product ranking", "bestsellers", "top 10 products"])
    b.page(d, s, "grid", "Product Performance Grid", S, "Full product-level grid of revenue, units, AOV, margin and return rate.",
           ["revenue", "units", "aov", "margin_pct"], ["product", "channel"], grid_metrics=["revenue", "units", "aov", "margin_pct", "return_rate"],
           synonyms=["product table", "sku report", "product list", "product grid"], kind="grid")
    for p in C.PRODUCTS:
        b.page(d, s, slug(p), f"{p} Product Report", S, f"Product report for {p} ({C.PRODUCT_CATEGORY[p]}): sales by region and channel.",
               ["revenue", "units", "aov"], ["region", "channel"], presets={"product": p},
               synonyms=[f"{p.lower()} sales", f"{p.lower()} report"])

    s = b.subdir(d, "segments", "Customer Segments")
    b.page(d, s, "mix", "Segment Sales Mix", S, "Revenue and AOV split across New, Regular, Premium and Corporate customers.",
           sales_kpis, ["segment", "region"], synonyms=["segment sales", "customer type sales", "b2b vs b2c"])
    for seg in C.SEGMENTS:
        b.page(d, s, slug(seg), f"{seg} Customer Sales", S, f"Sales from {seg} customers by region and category.",
               sales_kpis, ["region", "category"], presets={"segment": seg}, synonyms=[f"{seg.lower()} customers sales", f"{seg.lower()} segment"])

    s = b.subdir(d, "region_category", "Region x Category")
    for r in C.REGIONS:
        for cat in C.CATEGORIES:
            b.page(d, s, f"{slug(r)}_{slug(cat)}", f"{r} {cat} Sales", S,
                   f"{cat} sales in the {r} region by product and city.",
                   ["revenue", "orders", "margin_pct"], ["product", "city"], presets={"region": r, "category": cat},
                   synonyms=[f"{cat.lower()} in {r.lower()}", f"{r.lower()} {cat.lower()}"])

    # ---------------- Operations / Delivery ----------------
    V = "delivery"
    dk = ["on_time_pct", "shipments", "late_shipments", "avg_delay_mins"]
    d = b.directory("ops", "Operations", "truck", "Fulfilment and last-mile delivery performance by warehouse, carrier and city")
    s = b.subdir(d, "delivery", "Delivery Performance")
    b.page(d, s, "overview", "Delivery Overview", V, "Shipments, on-time delivery %, late shipments and average delay by region and carrier.",
           dk, ["region", "carrier"], synonyms=["logistics dashboard", "fulfilment overview", "shipping dashboard", "last mile"])
    b.page(d, s, "on_time", "On-Time Performance", V, "On-time delivery % (SLA adherence) trend by warehouse and carrier.",
           ["on_time_pct", "shipments"], ["warehouse", "carrier"], synonyms=["otd", "sla report", "on time delivery report", "delivery sla"])
    b.page(d, s, "delays", "Delay Analysis", V, "Late shipments and average delay minutes by city and carrier to find bottlenecks.",
           ["late_shipments", "avg_delay_mins", "on_time_pct"], ["city", "carrier"], synonyms=["late deliveries", "delays report", "delivery delays"])
    b.page(d, s, "city_grid", "City Delivery Grid", V, "City-level grid of shipments, on-time % and delay.",
           dk, ["city", "warehouse"], kind="grid", synonyms=["city wise delivery", "delivery by city"])
    for r in C.REGIONS:
        b.page(d, s, slug(r), f"{r} Delivery Performance", V, f"Delivery performance in the {r} region by city and carrier.",
               dk, ["city", "carrier"], presets={"region": r}, synonyms=[f"{r.lower()} delivery", f"{r.lower()} logistics"])
    s = b.subdir(d, "carriers", "Carriers")
    b.page(d, s, "scorecard", "Carrier Scorecard", V, "Compare logistics partners on shipments, on-time % and delay.",
           dk, ["carrier", "region"], synonyms=["courier comparison", "logistics partner performance", "carrier comparison"])
    for cr in C.CARRIERS:
        b.page(d, s, slug(cr), f"{cr} Carrier Performance", V, f"Performance of carrier {cr} by region and city.",
               dk, ["region", "city"], presets={"carrier": cr}, synonyms=[f"{cr.lower()} performance"])
    s = b.subdir(d, "warehouses", "Warehouses")
    for w in C.WAREHOUSES:
        b.page(d, s, slug(w), f"{w} Dispatch", V, f"Dispatch and delivery performance for shipments from {w} by city and carrier.",
               dk, ["city", "carrier"], presets={"warehouse": w}, synonyms=[f"{w.lower()} dispatch", f"{w.lower()} deliveries"])

    # ---------------- Inventory ----------------
    V = "inventory"
    ik = ["stockout_days", "in_stock_rate", "avg_stock_units", "inbound_units"]
    d = b.directory("inventory", "Inventory", "package", "Stock availability, stockouts and replenishment across warehouses")
    s = b.subdir(d, "health", "Stock Health")
    b.page(d, s, "overview", "Inventory Overview", V, "Stock levels, in-stock rate, stockouts and inbound units by warehouse and category.",
           ik, ["warehouse", "category"], synonyms=["inventory dashboard", "stock dashboard", "warehouse stock"])
    b.page(d, s, "stockouts", "Stockout Monitor", V, "Stockout days by product and warehouse; flags out-of-stock SKUs.",
           ["stockout_days", "in_stock_rate"], ["product", "warehouse"], synonyms=["out of stock", "oos report", "stockout alerts", "availability issues", "stock-outs"])
    b.page(d, s, "levels", "Stock Levels Grid", V, "Average stock on hand and inbound units by product and warehouse.",
           ["avg_stock_units", "inbound_units", "stockout_days"], ["product", "warehouse"], kind="grid",
           synonyms=["stock on hand", "inventory levels", "stock report"])
    s = b.subdir(d, "warehouses", "By Warehouse")
    for w in C.WAREHOUSES:
        b.page(d, s, slug(w), f"{w} Inventory", V, f"Inventory health at {w}: stockouts and stock levels by category and product.",
               ik, ["category", "product"], presets={"warehouse": w}, synonyms=[f"{w.lower()} stock", f"{w.lower()} inventory"])
    s = b.subdir(d, "categories", "By Category")
    for cat in C.CATEGORIES:
        b.page(d, s, slug(cat), f"{cat} Stock Health", V, f"Stock availability for {cat} by warehouse and product.",
               ik, ["warehouse", "product"], presets={"category": cat}, synonyms=[f"{cat.lower()} stock", f"{cat.lower()} inventory"])

    # ---------------- Marketing ----------------
    V = "marketing"
    mk = ["spend", "conversions", "cpa", "roas"]
    d = b.directory("marketing", "Marketing", "megaphone", "Campaign spend, reach and efficiency across marketing channels")
    s = b.subdir(d, "performance", "Performance")
    b.page(d, s, "overview", "Marketing Overview", V, "Marketing spend, conversions, CPA and ROAS by channel and region.",
           mk, ["mkt_channel", "region"], synonyms=["marketing dashboard", "ads dashboard", "digital marketing"])
    b.page(d, s, "campaigns", "Campaign Performance", V, "Compare campaigns on spend, conversions, CPA and ROAS.",
           mk, ["campaign", "mkt_channel"], date_preset="last_12_months", synonyms=["campaign report", "campaign comparison", "all campaigns"])
    b.page(d, s, "roas", "ROAS Analysis", V, "Return on ad spend and attributed revenue by channel and campaign.",
           ["roas", "attributed_revenue", "spend"], ["mkt_channel", "campaign"], synonyms=["marketing roi", "return on ad spend", "roi"])
    b.page(d, s, "spend", "Spend Tracker", V, "Marketing spend pacing over time by channel and region.",
           ["spend", "impressions", "clicks", "ctr"], ["mkt_channel", "region"], synonyms=["budget tracker", "ad spend", "media spend", "budget pacing"])
    s = b.subdir(d, "channels", "Marketing Channels")
    for m in C.MKT_CHANNELS:
        b.page(d, s, slug(m), f"{m} Channel Performance", V, f"{m} spend, CTR, conversions and ROAS by region and campaign.",
               mk, ["region", "campaign"], presets={"mkt_channel": m}, synonyms=[f"{m.lower()} performance", f"{m.lower()} ads"])
    s = b.subdir(d, "campaigns", "Campaign Reports")
    for name, st, en in C.CAMPAIGNS:
        b.page(d, s, slug(name), f"{name} Campaign Report", V,
               f"Results of the {name} campaign ({st.strftime('%d %b %Y')} to {en.strftime('%d %b %Y')}) by channel and region.",
               mk, ["mkt_channel", "region"], presets={"campaign": name}, date_preset="all_time",
               synonyms=[f"{name.lower()} results", f"{name.lower()} campaign"], kind="report")
    s = b.subdir(d, "regions", "Regional Marketing")
    for r in C.REGIONS:
        b.page(d, s, slug(r), f"{r} Marketing", V, f"Marketing spend and efficiency in the {r} region.",
               mk, ["mkt_channel", "campaign"], presets={"region": r}, synonyms=[f"{r.lower()} marketing", f"{r.lower()} ads"])

    # ---------------- Customers ----------------
    V = "customers"
    ck = ["active_customers", "new_customers", "churn_rate", "retention_rate"]
    d = b.directory("customers", "Customers", "users", "Customer base, acquisition, churn and retention by segment and region")
    s = b.subdir(d, "health", "Customer Health")
    b.page(d, s, "overview", "Customer Overview", V, "Active, new and churned customers with churn and retention rates by segment and region.",
           ck, ["segment", "region"], date_preset="last_12_months", synonyms=["customer dashboard", "customer base", "crm overview"])
    b.page(d, s, "churn", "Churn Analysis", V, "Monthly churn rate and churned customers by segment and region.",
           ["churn_rate", "churned_customers", "active_customers"], ["segment", "region"], date_preset="last_12_months",
           synonyms=["attrition", "churn report", "customer churn", "lost customers"])
    b.page(d, s, "acquisition", "Customer Acquisition", V, "New customer acquisition trend by region and segment.",
           ["new_customers", "active_customers"], ["region", "segment"], date_preset="last_12_months",
           synonyms=["new customers", "signups", "customer growth", "acquisition report"])
    b.page(d, s, "retention", "Retention by Segment", V, "Retention rate trend for each customer segment.",
           ["retention_rate", "churn_rate"], ["segment", "region"], date_preset="last_12_months",
           synonyms=["retention report", "loyalty", "customer retention"])
    s = b.subdir(d, "segments", "Segments")
    for seg in C.SEGMENTS:
        b.page(d, s, slug(seg), f"{seg} Segment Health", V, f"Health of the {seg} customer segment: active base, acquisition, churn by region.",
               ck, ["region"], presets={"segment": seg}, date_preset="last_12_months",
               synonyms=[f"{seg.lower()} customers", f"{seg.lower()} churn"])
    s = b.subdir(d, "regions", "Regions")
    for r in C.REGIONS:
        b.page(d, s, slug(r), f"{r} Customer Base", V, f"Customer base, churn and acquisition in the {r} region by segment.",
               ck, ["segment"], presets={"region": r}, date_preset="last_12_months",
               synonyms=[f"{r.lower()} customers", f"{r.lower()} customer base"])

    # ---------------- Support ----------------
    V = "support"
    sk = ["tickets", "csat", "avg_resolution_hrs"]
    d = b.directory("support", "Support", "headset", "Customer support volume, satisfaction and resolution performance")
    s = b.subdir(d, "service", "Service Quality")
    b.page(d, s, "overview", "Support Overview", V, "Ticket volume, CSAT and resolution time by issue type and region.",
           sk, ["issue_type", "region"], synonyms=["support dashboard", "customer service dashboard", "helpdesk", "cx dashboard"])
    b.page(d, s, "volume", "Ticket Volume", V, "Support ticket volume trend by issue type and priority.",
           ["tickets"], ["issue_type", "priority"], synonyms=["complaints", "ticket trend", "complaint volume", "case volume"])
    b.page(d, s, "csat", "CSAT Analysis", V, "Customer satisfaction (CSAT) by region and issue type.",
           ["csat", "tickets"], ["region", "issue_type"], synonyms=["customer satisfaction", "satisfaction report", "nps"])
    b.page(d, s, "resolution", "Resolution Time", V, "Average resolution hours by priority and issue type.",
           ["avg_resolution_hrs", "tickets"], ["priority", "issue_type"], synonyms=["tat", "turnaround time", "resolution report", "sla breaches"])
    b.page(d, s, "priority_queue", "Priority Queue", V, "High and critical priority ticket volumes and resolution times.",
           sk, ["priority", "region"], presets={"priority": "Critical"}, synonyms=["critical tickets", "escalations", "urgent tickets"])
    s = b.subdir(d, "issues", "Issue Types")
    for it in C.ISSUE_TYPES:
        b.page(d, s, slug(it), f"{it} Tickets", V, f"Tickets about {it.lower()} by region and priority, with CSAT and resolution time.",
               sk, ["region", "priority"], presets={"issue_type": it}, synonyms=[f"{it.lower()} complaints", f"{it.lower()} issues"])
    s = b.subdir(d, "regions", "Regional Support")
    for r in C.REGIONS:
        b.page(d, s, slug(r), f"{r} Support", V, f"Support tickets, CSAT and resolution time in the {r} region by issue type.",
               sk, ["issue_type", "priority"], presets={"region": r}, synonyms=[f"{r.lower()} support", f"{r.lower()} complaints"])

    # ---------------- Finance ----------------
    d = b.directory("finance", "Finance", "landmark", "Profitability and periodic financial reports")
    s = b.subdir(d, "profitability", "Profitability")
    b.page(d, s, "pnl", "P&L Snapshot", S, "Revenue, gross margin, discounts and margin % snapshot.",
           ["revenue", "gross_margin", "discount", "margin_pct"], ["category", "region"], synonyms=["p&l", "profit and loss", "pnl", "income statement"])
    b.page(d, s, "category_margin", "Gross Margin by Category", S, "Gross margin and margin % for each category.",
           ["gross_margin", "margin_pct"], ["category", "product"], synonyms=["category profitability", "category margins"])
    b.page(d, s, "discount_leakage", "Discount Leakage", S, "Discount amount and discount % by channel and region to catch margin leakage.",
           ["discount", "discount_pct", "margin_pct"], ["channel", "region"], synonyms=["discount leakage", "margin leakage", "over-discounting"])
    b.page(d, s, "regional_profit", "Regional Profitability", S, "Gross margin and margin % by region and city.",
           ["gross_margin", "margin_pct", "revenue"], ["region", "city"], synonyms=["region profitability", "regional margins"])
    b.page(d, s, "channel_profit", "Channel Profitability", S, "Gross margin and discount depth by sales channel.",
           ["gross_margin", "margin_pct", "discount_pct"], ["channel", "category"], synonyms=["channel margins", "channel profitability"])
    s = b.subdir(d, "reports", "Periodic Reports")
    b.page(d, s, "monthly", "Monthly Revenue Report", S, "Month-by-month revenue, orders and margin report.",
           ["revenue", "orders", "gross_margin"], ["region", "channel"], date_preset="last_12_months", kind="report",
           synonyms=["monthly sales report", "month wise revenue", "monthly revenue"])
    b.page(d, s, "quarterly", "Quarterly Business Report", S, "Quarter-over-quarter revenue, margin and order report.",
           ["revenue", "gross_margin", "orders"], ["region", "category"], date_preset="last_quarter", kind="report",
           synonyms=["qbr", "quarterly report", "quarter results", "quarterly revenue"])
    b.page(d, s, "annual", "Annual Revenue Report", S, "Year-to-date and full-year revenue, margin and orders.",
           ["revenue", "gross_margin", "orders"], ["region", "category"], date_preset="year_to_date", kind="report",
           synonyms=["annual report", "yearly report", "ytd report", "year to date revenue"])

    views_meta = {}
    for vk, v in VIEWS.items():
        views_meta[vk] = {
            "label": v["label"], "description": v["description"], "min_grain": v["min_grain"],
            "dimensions": [{"field": dm, "label": C.DIMENSION_LABELS[dm], "values": C.DIMENSION_VALUES[dm]} for dm in v["dims"]],
            "metrics": [{"name": mk_, "label": md["label"], "format": md["fmt"], "additive": md["additive"],
                         "good_direction": md["good"]} for mk_, md in v["metrics"].items()],
            "default_metric": v["default_metric"],
        }

    meta = {
        "app": {"name": C.APP_NAME, "tenant": C.TENANT_NAME, "version": "1.0",
                "data_start": C.DATA_START.isoformat(), "data_end": C.DATA_END.isoformat()},
        "directories": b.dirs,
        "pages": b.pages,
        "routes": {p["route"]: pid for pid, p in b.pages.items()},
        "data_views": views_meta,
        "component_types": COMPONENT_TYPES,
        "date_presets": DATE_PRESETS,
    }
    return meta


def main():
    meta = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    n_w = sum(len(p["widgets"]) for p in meta["pages"].values())
    n_f = sum(len(p["filters"]) for p in meta["pages"].values())
    print(f"Wrote {OUT}: {len(meta['directories'])} directories, "
          f"{sum(len(d['subdirectories']) for d in meta['directories'])} subdirectories, "
          f"{len(meta['pages'])} pages, {n_w} widgets, {n_f} filter controls")


if __name__ == "__main__":
    main()
