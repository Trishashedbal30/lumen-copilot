"""
Semantic layer: named metrics and dimensions over the raw tables.

The agent never writes free-form SQL. It produces a structured QuerySpec (view, metrics, group_by,
filters, date range, sort, limit) and this module compiles it into parameterised SQL. Metric
definitions live in exactly one place, so "revenue" means the same thing on every page, in every
answer and in every eval check.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

VIEWS = {
    "sales": {
        "label": "Sales", "table": "sales_daily", "min_grain": "day",
        "description": "Orders, revenue, margin, discounts and returns by region, city, channel, category, product and segment.",
        "dims": ["region", "city", "channel", "category", "product", "segment"],
        "metrics": {
            "revenue": {"label": "Revenue", "sql": "SUM(revenue)", "fmt": "currency", "additive": True, "good": "up",
                        "synonyms": ["revenue", "sales", "turnover", "gmv", "topline", "top line", "income", "net sales", "business", "bikri"]},
            "orders": {"label": "Orders", "sql": "SUM(orders)", "fmt": "int", "additive": True, "good": "up",
                       "synonyms": ["orders", "order count", "number of orders", "no of orders", "transactions", "order volume"]},
            "units": {"label": "Units Sold", "sql": "SUM(units)", "fmt": "int", "additive": True, "good": "up",
                      "synonyms": ["units", "units sold", "quantity", "items sold", "volume", "qty"]},
            "aov": {"label": "Avg Order Value", "sql": "SUM(revenue)/NULLIF(SUM(orders),0)", "fmt": "currency", "additive": False, "good": "up",
                    "synonyms": ["aov", "average order value", "avg order value", "basket size", "ticket size", "average basket"]},
            "gross_margin": {"label": "Gross Margin", "sql": "SUM(revenue-cost)", "fmt": "currency", "additive": True, "good": "up",
                             "synonyms": ["gross margin", "margin", "profit", "gross profit", "contribution"]},
            "margin_pct": {"label": "Margin %", "sql": "100*SUM(revenue-cost)/NULLIF(SUM(revenue),0)", "fmt": "pct", "additive": False, "good": "up",
                           "synonyms": ["margin %", "margin percent", "margin percentage", "margin rate", "profitability", "gross margin %"]},
            "discount": {"label": "Discounts", "sql": "SUM(discount)", "fmt": "currency", "additive": True, "good": "down",
                         "synonyms": ["discount", "discounts", "markdown", "markdowns", "promotions", "promo spend", "discount amount"]},
            "discount_pct": {"label": "Discount %", "sql": "100*SUM(discount)/NULLIF(SUM(revenue+discount),0)", "fmt": "pct", "additive": False, "good": "down",
                             "synonyms": ["discount %", "discount rate", "discount percentage", "discount depth"]},
            "returns": {"label": "Returns", "sql": "SUM(returns)", "fmt": "int", "additive": True, "good": "down",
                        "synonyms": ["number of returns", "returned orders", "return count"]},
            "return_rate": {"label": "Return Rate", "sql": "100*SUM(returns)/NULLIF(SUM(orders),0)", "fmt": "pct", "additive": False, "good": "down",
                            "synonyms": ["return rate", "returns", "returns %", "return percentage", "rto"]},
        },
        "default_metric": "revenue",
    },
    "delivery": {
        "label": "Delivery", "table": "delivery_daily", "min_grain": "day",
        "description": "Shipments, on-time delivery and delays by region, city, warehouse and carrier.",
        "dims": ["region", "city", "warehouse", "carrier"],
        "metrics": {
            "shipments": {"label": "Shipments", "sql": "SUM(shipments)", "fmt": "int", "additive": True, "good": "up",
                          "synonyms": ["shipments", "deliveries", "dispatches", "parcels", "consignments"]},
            "on_time_pct": {"label": "On-Time Delivery %", "sql": "100*SUM(on_time)/NULLIF(SUM(shipments),0)", "fmt": "pct", "additive": False, "good": "up",
                            "synonyms": ["on-time delivery", "on time delivery", "on-time", "on time", "otd", "otif", "delivery sla", "sla", "delivery performance", "on-time rate", "punctuality"]},
            "late_shipments": {"label": "Late Shipments", "sql": "SUM(late)", "fmt": "int", "additive": True, "good": "down",
                               "synonyms": ["late shipments", "late deliveries", "delayed shipments", "delayed deliveries", "late orders"]},
            "avg_delay_mins": {"label": "Avg Delay (min)", "sql": "SUM(delay_mins)/NULLIF(SUM(late),0)", "fmt": "minutes", "additive": False, "good": "down",
                               "synonyms": ["delay", "delays", "average delay", "avg delay", "delay time", "lateness", "delivery delay"]},
        },
        "default_metric": "on_time_pct",
    },
    "inventory": {
        "label": "Inventory", "table": "inventory_daily", "min_grain": "day",
        "description": "Stock levels, inbound units and stockouts by warehouse, category and product.",
        "dims": ["region", "warehouse", "category", "product"],
        "metrics": {
            "stockout_days": {"label": "Stockout Days", "sql": "SUM(stockout)", "fmt": "int", "additive": True, "good": "down",
                              "synonyms": ["stockouts", "stockout", "stock-outs", "stock outs", "out of stock", "oos", "stockout days", "out-of-stock"]},
            "in_stock_rate": {"label": "In-Stock Rate", "sql": "100*(1-SUM(stockout)/NULLIF(COUNT(*),0))", "fmt": "pct", "additive": False, "good": "up",
                              "synonyms": ["in-stock rate", "in stock rate", "availability", "in stock", "fill rate", "on-shelf availability"]},
            "avg_stock_units": {"label": "Avg Stock (units)", "sql": "SUM(stock_units)/NULLIF(COUNT(DISTINCT date),0)", "fmt": "int", "additive": False, "good": "up",
                                "synonyms": ["stock", "stock level", "stock levels", "inventory level", "inventory levels", "on hand", "stock on hand", "inventory"]},
            "inbound_units": {"label": "Inbound Units", "sql": "SUM(inbound_units)", "fmt": "int", "additive": True, "good": "up",
                              "synonyms": ["inbound", "inbound units", "replenishment", "receipts", "inward"]},
        },
        "default_metric": "stockout_days",
    },
    "marketing": {
        "label": "Marketing", "table": "marketing_daily", "min_grain": "day",
        "description": "Spend, impressions, clicks, conversions, CPA and ROAS by region, marketing channel and campaign.",
        "dims": ["region", "mkt_channel", "campaign"],
        "metrics": {
            "spend": {"label": "Marketing Spend", "sql": "SUM(spend)", "fmt": "currency", "additive": True, "good": "neutral",
                      "synonyms": ["spend", "marketing spend", "ad spend", "media spend", "budget", "marketing budget", "ad cost"]},
            "impressions": {"label": "Impressions", "sql": "SUM(impressions)", "fmt": "int", "additive": True, "good": "up",
                            "synonyms": ["impressions", "reach", "views", "eyeballs"]},
            "clicks": {"label": "Clicks", "sql": "SUM(clicks)", "fmt": "int", "additive": True, "good": "up",
                       "synonyms": ["clicks", "traffic", "visits"]},
            "conversions": {"label": "Conversions", "sql": "SUM(conversions)", "fmt": "int", "additive": True, "good": "up",
                            "synonyms": ["conversions", "conversion", "leads", "acquisitions"]},
            "ctr": {"label": "CTR", "sql": "100*SUM(clicks)/NULLIF(SUM(impressions),0)", "fmt": "pct", "additive": False, "good": "up",
                    "synonyms": ["ctr", "click through rate", "click-through rate"]},
            "cpa": {"label": "Cost per Acquisition", "sql": "SUM(spend)/NULLIF(SUM(conversions),0)", "fmt": "currency", "additive": False, "good": "down",
                    "synonyms": ["cpa", "cost per acquisition", "cost per conversion", "cac", "acquisition cost"]},
            "roas": {"label": "ROAS", "sql": "SUM(attributed_revenue)/NULLIF(SUM(spend),0)", "fmt": "ratio", "additive": False, "good": "up",
                     "synonyms": ["roas", "return on ad spend", "marketing roi", "roi", "return on spend"]},
            "attributed_revenue": {"label": "Attributed Revenue", "sql": "SUM(attributed_revenue)", "fmt": "currency", "additive": True, "good": "up",
                                   "synonyms": ["attributed revenue", "marketing revenue", "campaign revenue"]},
        },
        "default_metric": "spend",
    },
    "support": {
        "label": "Support", "table": "support_daily", "min_grain": "day",
        "description": "Support tickets, CSAT and resolution time by region, issue type and priority.",
        "dims": ["region", "issue_type", "priority"],
        "metrics": {
            "tickets": {"label": "Tickets", "sql": "SUM(tickets)", "fmt": "int", "additive": True, "good": "down",
                        "synonyms": ["tickets", "support tickets", "complaints", "cases", "support cases", "escalations", "ticket volume"]},
            "csat": {"label": "CSAT", "sql": "SUM(csat_sum)/NULLIF(SUM(csat_responses),0)", "fmt": "rating", "additive": False, "good": "up",
                     "synonyms": ["csat", "customer satisfaction", "satisfaction", "satisfaction score", "rating"]},
            "avg_resolution_hrs": {"label": "Avg Resolution (hrs)", "sql": "SUM(resolution_hrs)/NULLIF(SUM(tickets),0)", "fmt": "hours", "additive": False, "good": "down",
                                   "synonyms": ["resolution time", "avg resolution time", "tat", "turnaround time", "time to resolve", "handling time"]},
        },
        "default_metric": "tickets",
    },
    "customers": {
        "label": "Customers", "table": "customers_monthly", "min_grain": "month",
        "description": "Active, new and churned customers and churn rate by region and segment (monthly).",
        "dims": ["region", "segment"],
        "metrics": {
            "active_customers": {"label": "Active Customers", "sql": "SUM(active_customers)/NULLIF(COUNT(DISTINCT date),0)", "fmt": "int", "additive": False, "good": "up",
                                 "synonyms": ["active customers", "customer base", "customers", "active users", "customer count"]},
            "new_customers": {"label": "New Customers", "sql": "SUM(new_customers)", "fmt": "int", "additive": True, "good": "up",
                              "synonyms": ["new customers", "acquisition", "customer acquisition", "new customer acquisition", "signups", "sign-ups", "new users"]},
            "churned_customers": {"label": "Churned Customers", "sql": "SUM(churned_customers)", "fmt": "int", "additive": True, "good": "down",
                                  "synonyms": ["churned customers", "lost customers", "churned users", "customers lost"]},
            "churn_rate": {"label": "Churn Rate", "sql": "100*SUM(churned_customers)/NULLIF(SUM(active_customers),0)", "fmt": "pct", "additive": False, "good": "down",
                           "synonyms": ["churn", "churn rate", "attrition", "attrition rate", "customer churn"]},
            "retention_rate": {"label": "Retention Rate", "sql": "100-100*SUM(churned_customers)/NULLIF(SUM(active_customers),0)", "fmt": "pct", "additive": False, "good": "up",
                               "synonyms": ["retention", "retention rate", "customer retention"]},
        },
        "default_metric": "churn_rate",
    },
}

# Relationships between views, used by the knowledge graph and the cause-hypothesis engine.
# (from_view, to_view, shared dims mapping {from_dim: to_dim}, relation label)
VIEW_LINKS = [
    ("sales", "inventory", {"region": "region", "category": "category", "product": "product", "city": "warehouse"}, "availability drives sales"),
    ("sales", "marketing", {"region": "region"}, "marketing drives demand"),
    ("sales", "delivery", {"region": "region", "city": "city"}, "fulfilment affects sales"),
    ("sales", "customers", {"region": "region", "segment": "segment"}, "customer base drives sales"),
    ("sales", "support", {"region": "region"}, "service issues follow sales problems"),
    ("delivery", "support", {"region": "region"}, "late deliveries create tickets"),
    ("delivery", "sales", {"region": "region", "city": "city"}, "fulfilment affects sales"),
    ("customers", "sales", {"region": "region", "segment": "segment"}, "churn shows up in orders"),
    ("customers", "support", {"region": "region"}, "service issues drive churn"),
    ("marketing", "sales", {"region": "region"}, "marketing drives demand"),
    ("support", "delivery", {"region": "region"}, "late deliveries create tickets"),
    ("inventory", "sales", {"region": "region", "category": "category", "product": "product"}, "availability drives sales"),
]

TIME_GRAINS = ["day", "week", "month", "quarter", "year"]


@dataclass
class QuerySpec:
    view: str
    metrics: List[str]
    date_from: str
    date_to: str
    group_by: List[str] = field(default_factory=list)
    time_grain: Optional[str] = None
    filters: Dict[str, List[str]] = field(default_factory=dict)
    sort: Optional[str] = None          # metric or dim name
    sort_dir: str = "desc"
    limit: Optional[int] = None

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}


class SemanticError(ValueError):
    pass


def metric_def(view: str, metric: str) -> dict:
    return VIEWS[view]["metrics"][metric]


def view_of_metric(metric: str) -> Optional[str]:
    for v, spec in VIEWS.items():
        if metric in spec["metrics"]:
            return v
    return None


def compile_query(q: QuerySpec):
    """Return (sql, params). Raises SemanticError on anything not in the semantic layer."""
    if q.view not in VIEWS:
        raise SemanticError(f"unknown view {q.view}")
    v = VIEWS[q.view]
    for m in q.metrics:
        if m not in v["metrics"]:
            raise SemanticError(f"metric {m} not in view {q.view}")
    for d in q.group_by:
        if d not in v["dims"]:
            raise SemanticError(f"dimension {d} not in view {q.view}")
    for d in q.filters:
        if d not in v["dims"]:
            raise SemanticError(f"filter {d} not in view {q.view}")
    if q.time_grain and q.time_grain not in TIME_GRAINS:
        raise SemanticError(f"bad grain {q.time_grain}")

    select, group = [], []
    if q.time_grain:
        grain = q.time_grain
        if v["min_grain"] == "month" and grain in ("day", "week"):
            grain = "month"
        select.append(f"CAST(date_trunc('{grain}', date) AS DATE) AS period")
        group.append("period")
    for d in q.group_by:
        select.append(f'"{d}"')
        group.append(f'"{d}"')
    for m in q.metrics:
        select.append(f'{v["metrics"][m]["sql"]} AS "{m}"')

    where, params = ["date BETWEEN ? AND ?"], [q.date_from, q.date_to]
    if v.get("base_predicate"):
        where.append(v["base_predicate"])
    if q.view == "retail" and "customer_id" in q.group_by:
        where.append("customer_id IS NOT NULL")
    for d, vals in q.filters.items():
        if not vals:
            continue
        where.append(f'"{d}" IN ({",".join(["?"] * len(vals))})')
        params.extend(vals)

    sql = f'SELECT {", ".join(select)} FROM {v["table"]} WHERE {" AND ".join(where)}'
    if group:
        sql += f' GROUP BY {", ".join(group)}'
    if q.time_grain:
        sql += " ORDER BY period"
    elif q.sort:
        if q.sort not in q.metrics and q.sort not in q.group_by:
            raise SemanticError(f"cannot sort by {q.sort}")
        sql += f' ORDER BY "{q.sort}" {"DESC" if q.sort_dir == "desc" else "ASC"} NULLS LAST'
    if q.limit:
        sql += f" LIMIT {int(q.limit)}"
    return sql, params


def sql_preview(sql, params):
    """Human-readable SQL with parameters inlined (for the 'show query' panel only)."""
    out = sql
    for p in params:
        out = out.replace("?", "'" + str(p).replace("'", "''") + "'", 1)
    return out

# Register genuine imported retail data only when an import manifest exists.
from backend import datasets
datasets.register(VIEWS)

from backend import olist
olist.register(VIEWS)
