"""Query execution on DuckDB plus number formatting (Indian conventions: lakh / crore)."""
import math
import os
import threading
from datetime import date, datetime

import duckdb

from backend.semantic.layer import QuerySpec, compile_query, sql_preview, VIEWS

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.environ.get("LUMEN_DB", os.path.join(ROOT, "data", "lumen.duckdb"))

_con = None
_retail_con = None
_olist_con = None
_lock = threading.Lock()


def connection(view=None):
    global _con, _retail_con, _olist_con
    if view and view.startswith("olist_"):
        from backend.olist import DB
        if _olist_con is None: _olist_con=duckdb.connect(str(DB),read_only=True)
        return _olist_con
    if view == "retail":
        from backend.datasets import RETAIL_DB
        if _retail_con is None:
            _retail_con = duckdb.connect(str(RETAIL_DB), read_only=True)
        return _retail_con
    if _con is None:
        if not os.path.exists(DB_PATH):
            raise RuntimeError(f"{DB_PATH} not found. Run: python -m backend.data.generate_data")
        _con = duckdb.connect(DB_PATH, read_only=True)
    return _con


def _clean(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10]
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, 4)
    if hasattr(v, "item"):
        return _clean(v.item())
    return v


def run(q: QuerySpec):
    """Execute a QuerySpec. Returns dict(columns, rows, sql)."""
    sql, params = compile_query(q)
    with _lock:
        cur = connection(q.view).cursor()
        res = cur.execute(sql, params)
        cols = [c[0] for c in res.description]
        rows = [[_clean(v) for v in r] for r in res.fetchall()]
        cur.close()
    return {"columns": cols, "rows": rows, "sql": sql_preview(sql, params)}


def run_records(q: QuerySpec):
    r = run(q)
    return [dict(zip(r["columns"], row)) for row in r["rows"]], r["sql"]


def scalar(view, metric, date_from, date_to, filters=None):
    recs, sql = run_records(QuerySpec(view=view, metrics=[metric], date_from=date_from, date_to=date_to,
                                      filters=filters or {}))
    return (recs[0][metric] if recs else None), sql


def data_bounds(view):
    table = VIEWS[view]["table"]
    with _lock:
        cur = connection(view).cursor()
        lo, hi = cur.execute(f"SELECT MIN(date), MAX(date) FROM {table}").fetchone()
        cur.close()
    return lo.isoformat(), hi.isoformat()


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
def indian_group(n: int) -> str:
    s = str(abs(int(n)))
    if len(s) <= 3:
        out = s
    else:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        out = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + out


def fmt_value(v, fmt):
    if v is None:
        return "–"
    if fmt == "brl":
        return f"BRL {v:,.2f}"
    if fmt == "days":
        return f"{v:.2f} days"
    if fmt == "gbp":
        return f"GBP {v:,.2f}"
    if fmt == "currency":
        a = abs(v)
        sign = "-" if v < 0 else ""
        if a >= 1e7:
            return f"{sign}₹{a/1e7:,.2f} Cr"
        if a >= 1e5:
            return f"{sign}₹{a/1e5:,.2f} L"
        return f"{sign}₹{indian_group(round(a))}"
    if fmt == "retail_int":
        return f"{v:,.0f}"
    if fmt == "int":
        return indian_group(round(v))
    if fmt == "pct":
        return f"{v:.1f}%"
    if fmt == "hours":
        return f"{v:.1f} hrs"
    if fmt == "minutes":
        return f"{v:.0f} min"
    if fmt == "rating":
        return f"{v:.2f}/5"
    if fmt == "ratio":
        return f"{v:.2f}x"
    return f"{v:,.2f}"


def fmt_delta(cur, prev, fmt):
    """Return (abs_delta_str, pct_delta or None, pct_str)."""
    if cur is None or prev is None:
        return "–", None, "–"
    d = cur - prev
    if fmt in ("pct",):
        abs_s = f"{d:+.1f} pp"
    elif fmt == "rating":
        abs_s = f"{d:+.2f}"
    else:
        abs_s = ("+" if d >= 0 else "") + fmt_value(d, fmt)
    pct = None if prev == 0 else 100.0 * d / abs(prev)
    pct_s = "–" if pct is None else f"{pct:+.1f}%"
    return abs_s, pct, pct_s

def monthly_totals_with_mean(q: QuerySpec):
    """Calendar month totals including zero-activity months; parameterized SQL mean."""
    if len(q.metrics) != 1 or q.time_grain != 'month' or q.group_by or not VIEWS[q.view]['metrics'][q.metrics[0]]['additive']:
        raise ValueError('Monthly mean requires one additive metric and monthly grain without dimensions.')
    base, params = compile_query(q)
    metric = q.metrics[0]
    sql = f'''WITH monthly AS ({base}),
      calendar AS (SELECT CAST(month AS DATE) AS period FROM generate_series(CAST(? AS DATE), CAST(? AS DATE), INTERVAL '1 month') AS t(month)),
      monthly_values AS (SELECT calendar.period, COALESCE(monthly."{metric}", 0) AS monthly_value FROM calendar LEFT JOIN monthly USING (period))
      SELECT period, monthly_value, AVG(monthly_value) OVER () AS monthly_average FROM monthly_values ORDER BY period'''
    params = list(params) + [q.date_from, q.date_to]
    with _lock:
        cur = connection(q.view).cursor()
        try:
            rows = cur.execute(sql, params).fetchall()
        finally:
            cur.close()
    return [{'period': _clean(p), 'value': _clean(v), 'average': _clean(a)} for p,v,a in rows], sql_preview(sql,params)
