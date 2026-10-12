"""
Synthetic business data for the Sahyadri Retail tenant, with PLANTED anomalies.

Why planted anomalies: "likely causes" answers are usually impossible to grade. Here every anomaly
has a known root cause recorded in data/ground_truth.json, so the eval harness can check whether the
agent's root-cause analysis finds it.

Tables written to data/lumen.duckdb:
  sales_daily      date, region, city, channel, category, product, segment, orders, units, revenue, discount, cost, returns
  delivery_daily   date, region, city, warehouse, carrier, shipments, on_time, late, delay_mins
  inventory_daily  date, region, warehouse, category, product, stock_units, inbound_units, stockout
  marketing_daily  date, region, mkt_channel, campaign, spend, impressions, clicks, conversions, attributed_revenue
  support_daily    date, region, issue_type, priority, tickets, resolution_hrs, csat_sum, csat_responses
  customers_monthly date, region, segment, active_customers, new_customers, churned_customers

Run:  python -m backend.data.generate_data
"""
import json
import os
from datetime import date, timedelta

import duckdb
import numpy as np
import pandas as pd

from backend import catalog as C

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "lumen.duckdb")
SEED = 42

PRICE = {
    "Smartphones": 18000, "Laptops": 52000, "Headphones": 2600, "Smartwatches": 6500,
    "Cookware": 2200, "Small Appliances": 4800, "Furniture": 14000, "Home Decor": 1500,
    "Men's Apparel": 1600, "Women's Apparel": 1900, "Footwear": 2400, "Accessories": 900,
    "Staples": 750, "Snacks": 380, "Beverages": 420, "Personal Care": 520,
    "Skincare": 950, "Makeup": 820, "Haircare": 610, "Fragrances": 2300,
    "Fitness Equipment": 7200, "Sportswear": 1800, "Outdoor Gear": 3600, "Cycles": 12500,
}
# relative order volume per product (per city-channel-day, before city/channel weights)
POPULARITY = {
    "Smartphones": 2.2, "Laptops": 0.7, "Headphones": 3.0, "Smartwatches": 1.4,
    "Cookware": 1.6, "Small Appliances": 1.3, "Furniture": 0.35, "Home Decor": 1.5,
    "Men's Apparel": 3.0, "Women's Apparel": 3.6, "Footwear": 2.4, "Accessories": 2.2,
    "Staples": 7.0, "Snacks": 6.0, "Beverages": 5.0, "Personal Care": 4.5,
    "Skincare": 2.6, "Makeup": 2.0, "Haircare": 2.2, "Fragrances": 0.9,
    "Fitness Equipment": 0.6, "Sportswear": 1.8, "Outdoor Gear": 0.7, "Cycles": 0.35,
}
UNITS_PER_ORDER = {p: 1.0 for p in C.PRODUCTS}
UNITS_PER_ORDER.update({"Staples": 2.6, "Snacks": 3.1, "Beverages": 2.8, "Personal Care": 2.2,
                        "Skincare": 1.6, "Makeup": 1.7, "Haircare": 1.5, "Men's Apparel": 1.4,
                        "Women's Apparel": 1.5, "Accessories": 1.3, "Home Decor": 1.4, "Cookware": 1.2})
COST_RATIO = {"Electronics": 0.86, "Home & Kitchen": 0.64, "Fashion": 0.54, "Grocery": 0.83,
              "Beauty": 0.50, "Sports": 0.62}
RETURN_RATE = {"Electronics": 0.040, "Home & Kitchen": 0.050, "Fashion": 0.115, "Grocery": 0.010,
               "Beauty": 0.030, "Sports": 0.050}
CITY_WEIGHT = {
    "Delhi": 1.55, "Chandigarh": 0.55, "Jaipur": 0.65, "Lucknow": 0.6,
    "Bengaluru": 1.5, "Chennai": 1.15, "Hyderabad": 1.2, "Kochi": 0.55,
    "Kolkata": 1.0, "Bhubaneswar": 0.45, "Patna": 0.45,
    "Mumbai": 1.6, "Pune": 0.9, "Ahmedabad": 0.8, "Goa": 0.35,
    "Bhopal": 0.45, "Indore": 0.55, "Nagpur": 0.5,
}
CHANNEL_WEIGHT = {"Online Store": 0.30, "Mobile App": 0.28, "Retail Stores": 0.27, "Marketplace": 0.15}
CHANNEL_CATEGORY_AFFINITY = {  # multiplier on channel weight per category
    "Grocery": {"Retail Stores": 1.6, "Marketplace": 0.5},
    "Electronics": {"Marketplace": 1.7, "Retail Stores": 0.7},
    "Fashion": {"Mobile App": 1.3},
    "Beauty": {"Mobile App": 1.2, "Online Store": 1.1},
}
SEGMENT_SHARE = {"New": 0.24, "Regular": 0.46, "Premium": 0.20, "Corporate": 0.10}
CARRIER_SHARE = {"BlueDart": 0.30, "Delhivery": 0.35, "Ecom Express": 0.20, "In-house Fleet": 0.15}
CARRIER_ONTIME = {"BlueDart": 0.945, "Delhivery": 0.925, "Ecom Express": 0.895, "In-house Fleet": 0.955}

# ---------------------------------------------------------------------------
# Planted anomalies (ground truth)
# ---------------------------------------------------------------------------
A1_START, A1_END = date(2026, 8, 4), date(2026, 8, 26)      # Electronics stockout at South DCs
A2_START, A2_END = date(2026, 3, 1), date(2026, 3, 31)      # Spring Launch: Mobile App surge via Social Media
A3_START, A3_END = date(2026, 6, 10), date(2026, 7, 31)     # Monsoon delivery delays at West DCs
A4_START = date(2026, 7, 15)                                 # Premium loyalty change -> churn
A5_START, A5_END = date(2026, 9, 1), date(2026, 9, 30)      # North Beauty / Skincare launch

GROUND_TRUTH = [
    {
        "id": "A1", "title": "South revenue drop in August 2026",
        "question_examples": ["Why did South revenue drop in August?", "what caused the dip in southern sales in aug 2026",
                              "explain the fall in South region revenue last August"],
        "view": "sales", "metric": "revenue", "filters": {"region": ["South"]},
        "period": ["2026-08-01", "2026-08-31"], "comparison": ["2026-07-01", "2026-07-31"],
        "expected_direction": "down",
        "expected_driver": {"dimension": "category", "value": "Electronics", "accept": ["Electronics"]},
        "expected_cause": {"view": "inventory", "metric": "stockout_days",
                           "explanation": "Electronics stockout at Chennai DC and Bengaluru DC, 4-26 Aug 2026"},
    },
    {
        "id": "A2", "title": "Revenue surge in March 2026 (Mobile App)",
        "question_examples": ["Why did revenue spike in March 2026?", "what drove the jump in sales in march"],
        "view": "sales", "metric": "revenue", "filters": {},
        "period": ["2026-03-01", "2026-03-31"], "comparison": ["2026-02-01", "2026-02-28"],
        "expected_direction": "up",
        "expected_driver": {"dimension": "channel", "value": "Mobile App", "accept": ["Mobile App"]},
        "expected_cause": {"view": "marketing", "metric": "spend",
                           "explanation": "Spring Launch campaign tripled Social Media spend in March 2026"},
    },
    {
        "id": "A3", "title": "West on-time delivery collapse, Jun-Jul 2026",
        "question_examples": ["Why did on-time delivery fall in the West in July?", "what caused the drop in on-time delivery in west region in july 2026"],
        "view": "delivery", "metric": "on_time_pct", "filters": {"region": ["West"]},
        "period": ["2026-07-01", "2026-07-31"], "comparison": ["2026-05-01", "2026-05-31"],
        "expected_direction": "down",
        "expected_driver": {"dimension": "warehouse", "value": "Mumbai DC", "accept": ["Mumbai DC", "Mumbai"]},
        "expected_cause": {"view": "support", "metric": "tickets",
                           "explanation": "Monsoon disruption at Mumbai DC and Ahmedabad DC; Delivery Delay tickets tripled"},
    },
    {
        "id": "A4", "title": "Churn spike in August 2026 (Premium segment)",
        "question_examples": ["Why did churn go up in August?", "what is driving the increase in customer churn in aug 2026"],
        "view": "customers", "metric": "churn_rate", "filters": {},
        "period": ["2026-08-01", "2026-08-31"], "comparison": ["2026-06-01", "2026-06-30"],
        "expected_direction": "up",
        "expected_driver": {"dimension": "segment", "value": "Premium", "accept": ["Premium"]},
        "expected_cause": None,
    },
    {
        "id": "A5", "title": "North Beauty growth, Sep 2026",
        "question_examples": ["Why did beauty sales grow in the North in September?", "what drove north beauty revenue up in september"],
        "view": "sales", "metric": "revenue", "filters": {"region": ["North"], "category": ["Beauty"]},
        "period": ["2026-09-01", "2026-09-30"], "comparison": ["2026-08-01", "2026-08-31"],
        "expected_direction": "up",
        "expected_driver": {"dimension": "product", "value": "Skincare", "accept": ["Skincare"]},
        "expected_cause": None,
    },
]


def daterange(a, b):
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def season_factor(dates):
    """Yearly seasonality + growth + weekly pattern, per date."""
    f = np.ones(len(dates))
    for i, d in enumerate(dates):
        m = d.month
        f[i] *= {1: 0.92, 2: 0.94, 3: 1.0, 4: 0.97, 5: 1.03, 6: 0.97, 7: 0.95, 8: 1.0, 9: 1.02,
                 10: 1.22, 11: 1.10, 12: 1.08}[m]
        t = (d - C.DATA_START).days / 365.0
        f[i] *= 1.0 + 0.20 * t  # ~20% YoY growth
        for name, s, e in C.CAMPAIGNS:
            if s <= d <= e:
                f[i] *= 1.30 if "Diwali" not in name else 1.55
                break
    return f


def active_campaign(d):
    for name, s, e in C.CAMPAIGNS:
        if s <= d <= e:
            return name
    return "Always-On"


def build_stockouts(rng, dates):
    """Stockout calendar: (date_idx, warehouse, product) -> 1. Random short stockouts + planted A1."""
    W, P = len(C.WAREHOUSES), len(C.PRODUCTS)
    so = np.zeros((len(dates), W, P), dtype=np.int8)
    # random short stockouts: ~0.4% chance per warehouse-product-day of starting a 1-4 day stockout
    starts = rng.random((len(dates), W, P)) < 0.004
    for di, wi, pi in zip(*np.nonzero(starts)):
        so[di:di + rng.integers(1, 5), wi, pi] = 1
    di0 = dates.index(A1_START)
    di1 = dates.index(A1_END)
    for w in ["Chennai DC", "Bengaluru DC"]:
        wi = C.WAREHOUSES.index(w)
        for p in C.CATEGORY_PRODUCTS["Electronics"]:
            so[di0:di1 + 1, wi, C.PRODUCTS.index(p)] = 1
    return so


def generate_sales(rng, dates, stockouts):
    D, Ci, Ch, P = len(dates), len(C.CITIES), len(C.CHANNELS), len(C.PRODUCTS)
    season = season_factor(dates)[:, None, None, None]
    city_w = np.array([C_W for C_W in (CITY_WEIGHT[c] for c in C.CITIES)])[None, :, None, None]
    ch_w = np.zeros((Ch, P))
    for j, ch in enumerate(C.CHANNELS):
        for k, p in enumerate(C.PRODUCTS):
            cat = C.PRODUCT_CATEGORY[p]
            ch_w[j, k] = CHANNEL_WEIGHT[ch] * CHANNEL_CATEGORY_AFFINITY.get(cat, {}).get(ch, 1.0)
    ch_w = ch_w[None, None, :, :]
    pop = np.array([POPULARITY[p] for p in C.PRODUCTS])[None, None, None, :]

    # weekly pattern: weekends +18% for online/app, +28% for retail
    dow = np.array([d.weekday() for d in dates])
    wk = np.ones((D, 1, Ch, 1))
    weekend = dow >= 5
    for j, ch in enumerate(C.CHANNELS):
        wk[weekend, 0, j, 0] = 1.28 if ch == "Retail Stores" else 1.18

    lam = 4.2 * season * city_w * ch_w * pop * wk

    # --- anomalies on demand ---
    di = {d: i for i, d in enumerate(dates)}
    city_idx = {c: i for i, c in enumerate(C.CITIES)}
    ch_idx = {c: i for i, c in enumerate(C.CHANNELS)}
    p_idx = {p: i for i, p in enumerate(C.PRODUCTS)}
    # stockouts suppress sales in the cities served by that warehouse (A1 lives here)
    for ci, city in enumerate(C.CITIES):
        wi = C.WAREHOUSES.index(C.CITY_WAREHOUSE[city])
        lam[:, ci, :, :] *= np.where(stockouts[:, wi, :][:, None, :] == 1, 0.22, 1.0)
    # A2: Mobile App surge in March 2026
    a, b = di[A2_START], di[A2_END]
    lam[a:b + 1, :, ch_idx["Mobile App"], :] *= 1.55
    # A3: West delivery disruption slightly dents online/app/marketplace demand in West
    a, b = di[A3_START], di[A3_END]
    for city in C.REGION_CITIES["West"]:
        for ch in ["Online Store", "Mobile App", "Marketplace"]:
            lam[a:b + 1, city_idx[city], ch_idx[ch], :] *= 0.90
    # A5: North Beauty growth driven by Skincare launch
    a, b = di[A5_START], di[A5_END]
    for city in C.REGION_CITIES["North"]:
        lam[a:b + 1, city_idx[city], :, p_idx["Skincare"]] *= 2.1
        for p in ["Makeup", "Haircare", "Fragrances"]:
            lam[a:b + 1, city_idx[city], :, p_idx[p]] *= 1.08

    noise = rng.lognormal(0.0, 0.18, size=lam.shape)
    orders = rng.poisson(lam * noise)

    # flatten
    grid = np.array(np.meshgrid(np.arange(D), np.arange(Ci), np.arange(Ch), np.arange(P), indexing="ij"))
    grid = grid.reshape(4, -1)
    orders = orders.reshape(-1)
    keep = orders > 0
    grid, orders = grid[:, keep], orders[keep]
    d_i, c_i, ch_i, p_i = grid

    n = len(orders)
    seg_names = list(SEGMENT_SHARE)
    seg_i = rng.choice(len(seg_names), size=n, p=list(SEGMENT_SHARE.values()))
    # A4: Premium orders shrink after the loyalty change
    a4 = di[A4_START]
    prem = (seg_i == seg_names.index("Premium")) & (d_i >= a4)
    orders = np.where(prem, np.maximum(0, np.round(orders * 0.72)).astype(int), orders)

    prod_arr = np.array(C.PRODUCTS)
    cat_arr = np.array([C.PRODUCT_CATEGORY[p] for p in C.PRODUCTS])
    price = np.array([PRICE[p] for p in C.PRODUCTS])[p_i]
    upo = np.array([UNITS_PER_ORDER[p] for p in C.PRODUCTS])[p_i]
    units = np.maximum(orders, np.round(orders * upo * rng.lognormal(0, 0.08, n))).astype(int)

    camp = np.array([active_campaign(d) != "Always-On" for d in dates])[d_i]
    disc_rate = 0.055 + 0.13 * camp + np.where(np.array(C.CHANNELS)[ch_i] == "Marketplace", 0.03, 0.0)
    disc_rate = disc_rate + rng.normal(0, 0.01, n)
    disc_rate = np.clip(disc_rate, 0.0, 0.4)
    gross = units * price / upo * rng.lognormal(0, 0.07, n)  # price is per order-ish basket
    revenue = gross * (1 - disc_rate)
    discount = gross * disc_rate
    cost_ratio = np.array([COST_RATIO[C.PRODUCT_CATEGORY[p]] for p in C.PRODUCTS])[p_i]
    cost = gross * cost_ratio * rng.lognormal(0, 0.03, n)

    ret_rate = np.array([RETURN_RATE[C.PRODUCT_CATEGORY[p]] for p in C.PRODUCTS])[p_i]
    region_arr = np.array([C.CITY_REGION[c] for c in C.CITIES])[c_i]
    a, b = di[A3_START], di[A3_END]
    ret_rate = ret_rate + np.where((region_arr == "West") & (d_i >= a) & (d_i <= b), 0.03, 0.0)
    returns = rng.binomial(orders, np.clip(ret_rate, 0, 1))

    df = pd.DataFrame({
        "date": pd.to_datetime(np.array(dates, dtype="datetime64[D]")[d_i]),
        "region": region_arr,
        "city": np.array(C.CITIES)[c_i],
        "channel": np.array(C.CHANNELS)[ch_i],
        "category": cat_arr[p_i],
        "product": prod_arr[p_i],
        "segment": np.array(seg_names)[seg_i],
        "orders": orders.astype(np.int32),
        "units": units.astype(np.int32),
        "revenue": np.round(revenue, 2),
        "discount": np.round(discount, 2),
        "cost": np.round(cost, 2),
        "returns": returns.astype(np.int32),
    })
    return df[df.orders > 0].reset_index(drop=True)


def generate_delivery(rng, dates, sales):
    ship = (sales[sales.channel != "Retail Stores"]
            .groupby(["date", "city"], as_index=False)["orders"].sum())
    rows = []
    a3s, a3e = pd.Timestamp(A3_START), pd.Timestamp(A3_END)
    diwali = [(pd.Timestamp(s), pd.Timestamp(e)) for n, s, e in C.CAMPAIGNS if "Diwali" in n or "Year End" in n]
    for carrier, share in CARRIER_SHARE.items():
        part = ship.copy()
        part["carrier"] = carrier
        part["shipments"] = rng.binomial(part["orders"].values, share)
        p = np.full(len(part), CARRIER_ONTIME[carrier])
        p += rng.normal(0, 0.012, len(part))
        for s, e in diwali:
            p = np.where((part.date >= s) & (part.date <= e), p - 0.06, p)
        wh = part.city.map(C.CITY_WAREHOUSE)
        hit = (part.date >= a3s) & (part.date <= a3e) & wh.isin(["Mumbai DC", "Ahmedabad DC"])
        severity = np.where(wh == "Mumbai DC", 0.30, 0.20)
        p = np.where(hit, p - severity, p)
        p = np.clip(p, 0.3, 0.995)
        part["on_time"] = rng.binomial(part["shipments"].values, p)
        rows.append(part)
    df = pd.concat(rows, ignore_index=True)
    df["late"] = df.shipments - df.on_time
    base_delay = np.where(df.city.map(C.CITY_WAREHOUSE).isin(["Mumbai DC", "Ahmedabad DC"])
                          & (df.date >= a3s) & (df.date <= a3e), 410.0, 190.0)
    df["delay_mins"] = np.round(df.late * base_delay * rng.lognormal(0, 0.2, len(df)), 1)
    df["region"] = df.city.map(C.CITY_REGION)
    df["warehouse"] = df.city.map(C.CITY_WAREHOUSE)
    df = df[df.shipments > 0]
    return df[["date", "region", "city", "warehouse", "carrier", "shipments", "on_time", "late", "delay_mins"]]


def generate_inventory(rng, dates, sales, stockouts):
    demand = (sales.assign(warehouse=sales.city.map(C.CITY_WAREHOUSE))
              .groupby(["warehouse", "product"])["units"].sum() / len(dates))
    rows = []
    for wi, w in enumerate(C.WAREHOUSES):
        for pi, p in enumerate(C.PRODUCTS):
            avg = float(demand.get((w, p), 1.0))
            so = stockouts[:, wi, pi]
            cover = rng.normal(18, 3, len(dates)).clip(6, 30)
            stock = np.where(so == 1, 0, np.round(avg * cover)).astype(int)
            inbound = np.where(so == 1, 0, np.round(avg * rng.lognormal(0, 0.25, len(dates)))).astype(int)
            rows.append(pd.DataFrame({
                "date": pd.to_datetime(np.array(dates, dtype="datetime64[D]")),
                "region": C.WAREHOUSE_REGION[w], "warehouse": w,
                "category": C.PRODUCT_CATEGORY[p], "product": p,
                "stock_units": stock, "inbound_units": inbound, "stockout": so.astype(np.int32),
            }))
    return pd.concat(rows, ignore_index=True)


def generate_marketing(rng, dates):
    share = {"Search Ads": 0.35, "Social Media": 0.25, "Email": 0.05, "Affiliates": 0.15, "TV": 0.20}
    cpm = {"Search Ads": 160, "Social Media": 95, "Email": 15, "Affiliates": 120, "TV": 260}
    ctr = {"Search Ads": 0.032, "Social Media": 0.011, "Email": 0.045, "Affiliates": 0.018, "TV": 0.002}
    cvr = {"Search Ads": 0.041, "Social Media": 0.026, "Email": 0.052, "Affiliates": 0.034, "TV": 0.02}
    reg_w = {"North": 1.1, "South": 1.05, "East": 0.6, "West": 1.15, "Central": 0.45}
    rows = []
    season = season_factor(dates)
    for i, d in enumerate(dates):
        camp = active_campaign(d)
        for r, rw in reg_w.items():
            for m, s in share.items():
                spend = 42000 * rw * s * season[i] * (1.9 if camp != "Always-On" else 1.0)
                if camp == "Spring Launch" and m == "Social Media":
                    spend *= 3.0
                spend *= rng.lognormal(0, 0.12)
                imp = spend / cpm[m] * 1000 * rng.lognormal(0, 0.05)
                clicks = imp * ctr[m] * rng.lognormal(0, 0.08)
                conv_rate = cvr[m] * (1.35 if (camp == "Spring Launch" and m == "Social Media") else 1.0)
                conv = clicks * conv_rate * rng.lognormal(0, 0.1)
                rows.append((d, r, m, camp, round(spend, 2), int(imp), int(clicks), int(conv),
                             round(conv * 2900 * rng.lognormal(0, 0.1), 2)))
    df = pd.DataFrame(rows, columns=["date", "region", "mkt_channel", "campaign", "spend", "impressions",
                                     "clicks", "conversions", "attributed_revenue"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def generate_support(rng, dates, sales):
    reg_orders = sales.groupby(["date", "region"])["orders"].sum()
    issue_share = {"Delivery Delay": 0.28, "Damaged Item": 0.14, "Refund": 0.22, "Payment Issue": 0.12,
                   "Product Quality": 0.16, "Account": 0.08}
    pr_share = {"Low": 0.35, "Medium": 0.40, "High": 0.20, "Critical": 0.05}
    pr_hrs = {"Low": 30, "Medium": 20, "High": 10, "Critical": 4}
    a3s, a3e = pd.Timestamp(A3_START), pd.Timestamp(A3_END)
    a1s, a1e = pd.Timestamp(A1_START), pd.Timestamp(A1_END)
    rows = []
    for (d, r), o in reg_orders.items():
        for it, s in issue_share.items():
            mult = 1.0
            if r == "West" and a3s <= d <= a3e and it == "Delivery Delay":
                mult = 3.2
            if r == "South" and a1s <= d <= a1e and it == "Refund":
                mult = 1.7
            for pr, ps in pr_share.items():
                lam = o / 1000 * 9 * s * ps * mult
                t = rng.poisson(lam)
                if t == 0:
                    continue
                hrs = t * pr_hrs[pr] * rng.lognormal(0, 0.15) * (1.5 if mult > 2 else 1.0)
                resp = rng.binomial(t, 0.6)
                csat_mean = 4.25 - (0.9 if mult > 2 else 0.0) - (0.3 if it == "Delivery Delay" else 0.0)
                csat_sum = float(np.clip(rng.normal(csat_mean, 0.25, resp), 1, 5).sum()) if resp else 0.0
                rows.append((d, r, it, pr, t, round(hrs, 1), round(csat_sum, 2), resp))
    df = pd.DataFrame(rows, columns=["date", "region", "issue_type", "priority", "tickets", "resolution_hrs",
                                     "csat_sum", "csat_responses"])
    return df


def generate_customers(rng):
    base = {"North": 410000, "South": 395000, "East": 190000, "West": 430000, "Central": 150000}
    seg_mix = {"New": 0.18, "Regular": 0.52, "Premium": 0.21, "Corporate": 0.09}
    churn = {"New": 0.062, "Regular": 0.031, "Premium": 0.018, "Corporate": 0.012}
    rows = []
    months = pd.date_range(C.DATA_START, C.DATA_END, freq="MS")
    for r, b in base.items():
        for s, mx in seg_mix.items():
            active = b * mx
            for m in months:
                cr = churn[s] * rng.lognormal(0, 0.06)
                if s == "Premium" and m >= pd.Timestamp(2026, 7, 1):
                    cr *= 2.3 if m.month == 7 else 2.9
                new = active * (0.055 if s != "New" else 0.30) * rng.lognormal(0, 0.06)
                churned = active * cr
                rows.append((m, r, s, int(active), int(new), int(churned)))
                # steady ~1.2% monthly base growth; a churn spike shrinks the base
                active = active * (1.012 * rng.lognormal(0, 0.01)) - max(0.0, churned - active * churn[s])
    df = pd.DataFrame(rows, columns=["date", "region", "segment", "active_customers", "new_customers",
                                     "churned_customers"])
    return df


def main():
    rng = np.random.default_rng(SEED)
    os.makedirs(DATA_DIR, exist_ok=True)
    dates = daterange(C.DATA_START, C.DATA_END)
    print(f"Generating {len(dates)} days of data ...")
    stockouts = build_stockouts(rng, dates)
    sales = generate_sales(rng, dates, stockouts)
    print(f"  sales_daily: {len(sales):,} rows, revenue Rs {sales.revenue.sum()/1e7:,.0f} Cr")
    delivery = generate_delivery(rng, dates, sales)
    inventory = generate_inventory(rng, dates, sales, stockouts)
    marketing = generate_marketing(rng, dates)
    support = generate_support(rng, dates, sales)
    customers = generate_customers(rng)
    for name, df in [("delivery_daily", delivery), ("inventory_daily", inventory), ("marketing_daily", marketing),
                     ("support_daily", support), ("customers_monthly", customers)]:
        print(f"  {name}: {len(df):,} rows")

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = duckdb.connect(DB_PATH)
    for name, df in [("sales_daily", sales), ("delivery_daily", delivery), ("inventory_daily", inventory),
                     ("marketing_daily", marketing), ("support_daily", support), ("customers_monthly", customers)]:
        con.register("tmp_df", df)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM tmp_df")
        con.execute(f"ALTER TABLE {name} ALTER COLUMN date TYPE DATE")
        con.unregister("tmp_df")
    con.close()
    with open(os.path.join(DATA_DIR, "ground_truth.json"), "w", encoding="utf-8") as f:
        json.dump(GROUND_TRUTH, f, indent=2)
    print(f"Wrote {DB_PATH}")


if __name__ == "__main__":
    main()
