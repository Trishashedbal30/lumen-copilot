"""
Analytical reasoning over the semantic layer.

  kpi()              value + change vs comparison period
  rank()             top/bottom N members of a dimension
  compare_entities() side-by-side values for chosen members (e.g. North vs South)
  trend()            series, growth, peak/trough, anomalies (robust z-score)
  drivers()          contribution analysis: which dimension members explain a change (2 levels deep),
                     exact for additive metrics and for ratio metrics via weighted-share decomposition
  causes()           cross-view hypothesis testing along knowledge-graph links (e.g. sales <- inventory)

Every number produced here is recorded as a Fact with the exact query that produced it, so the
responder can only state numbers that are traceable to a view (explanation faithfulness).
"""
import statistics
from datetime import date

from backend import catalog as C
from backend.semantic import engine
from backend.semantic.engine import fmt_delta, fmt_value
from backend.semantic.layer import VIEWS, VIEW_LINKS, QuerySpec

# weight metric for ratio-metric decomposition: M = sum_i (w_i / W) * m_i
RATIO_WEIGHTS = {
    ("sales", "aov"): "orders", ("sales", "margin_pct"): "revenue", ("sales", "discount_pct"): "revenue",
    ("sales", "return_rate"): "orders", ("delivery", "on_time_pct"): "shipments",
    ("delivery", "avg_delay_mins"): "late_shipments", ("marketing", "ctr"): "impressions",
    ("marketing", "cpa"): "conversions", ("marketing", "roas"): "spend", ("support", "csat"): "tickets",
    ("support", "avg_resolution_hrs"): "tickets", ("customers", "churn_rate"): "active_customers",
    ("customers", "retention_rate"): "active_customers", ("inventory", "in_stock_rate"): None,
}
ADDITIVE_ACROSS_DIMS = {("inventory", "avg_stock_units"), ("customers", "active_customers")}

SIGNALS = {
    "sales": ["revenue", "orders", "aov"],
    "inventory": ["stockout_days", "in_stock_rate"],
    "marketing": ["spend", "conversions"],
    "delivery": ["on_time_pct", "avg_delay_mins"],
    "support": ["tickets", "csat"],
    "customers": ["churn_rate", "new_customers"],
}
# relation of a signal to "good outcomes": +1 more is good, -1 more is bad, 0 use metric's own 'good'
SIGNAL_POLARITY = {("marketing", "spend"): +1}


class FactBook:
    """Collects every number shown to the user, with provenance."""

    def __init__(self):
        self.facts = []

    def add(self, label, value, fmt, view, metric, filters, rng, sql, kind="value", page_id=None, extra=None):
        f = {"id": f"f{len(self.facts)+1}", "label": label, "value": value, "formatted": fmt_value(value, fmt),
             "fmt": fmt, "view": view, "metric": metric, "filters": filters, "range": rng, "sql": sql,
             "kind": kind, "page_id": page_id,
             "dataset": VIEWS[view].get("dataset", "Synthetic Sahyadri Retail demo"),
             "metric_definition": VIEWS[view]["metrics"][metric].get("definition", VIEWS[view]["metrics"][metric]["sql"])}
        if extra:
            f.update(extra)
        self.facts.append(f)
        return f

    def add_text(self, label, text, view, metric, filters, rng, sql, kind="delta", page_id=None):
        f = {"id": f"f{len(self.facts)+1}", "label": label, "value": None, "formatted": text, "fmt": "text",
             "view": view, "metric": metric, "filters": filters, "range": rng, "sql": sql, "kind": kind, "page_id": page_id,
             "dataset": VIEWS[view].get("dataset", "Synthetic Sahyadri Retail demo"),
             "metric_definition": VIEWS[view]["metrics"][metric].get("definition", VIEWS[view]["metrics"][metric]["sql"])}
        self.facts.append(f)
        return f


def _q(view, metrics, rng, filters=None, group_by=None, grain=None, sort=None, sort_dir="desc", limit=None):
    return QuerySpec(view=view, metrics=metrics, date_from=rng["start"], date_to=rng["end"], filters=filters or {},
                     group_by=group_by or [], time_grain=grain, sort=sort, sort_dir=sort_dir, limit=limit)


def mdef(view, metric):
    return VIEWS[view]["metrics"][metric]


def filters_text(filters):
    if not filters:
        return "all data"
    return ", ".join(f"{C.DIMENSION_LABELS.get(k, k)}: {', '.join(v)}" for k, v in filters.items())


# ---------------------------------------------------------------------------
def kpi(fb, view, metric, filters, rng, cmp_rng=None, page_id=None):
    md = mdef(view, metric)
    recs, sql = engine.run_records(_q(view, [metric], rng, filters))
    cur = recs[0][metric] if recs else None
    f_cur = fb.add(f"{md['label']} ({rng['label']})", cur, md["fmt"], view, metric, filters, rng, sql, page_id=page_id)
    out = {"metric": metric, "view": view, "label": md["label"], "value": cur, "formatted": f_cur["formatted"],
           "fmt": md["fmt"], "good": md["good"], "range": rng, "fact": f_cur["id"]}
    if cmp_rng:
        recs2, sql2 = engine.run_records(_q(view, [metric], cmp_rng, filters))
        prev = recs2[0][metric] if recs2 else None
        f_prev = fb.add(f"{md['label']} ({cmp_rng['label']})", prev, md["fmt"], view, metric, filters, cmp_rng, sql2, page_id=page_id)
        abs_s, pct, pct_s = fmt_delta(cur, prev, md["fmt"])
        f_d = fb.add_text(f"Change in {md['label']}", f"{abs_s} ({pct_s})" if md["fmt"] != "pct" else abs_s,
                          view, metric, filters, rng, sql + " ; " + sql2, page_id=page_id)
        fb.add_text("pct", pct_s, view, metric, filters, rng, sql, kind="pct")
        fb.add_text("abs", abs_s, view, metric, filters, rng, sql, kind="abs")
        out.update({"prev": prev, "prev_formatted": f_prev["formatted"], "delta_abs": None if cur is None or prev is None else cur - prev,
                    "delta_abs_str": abs_s, "delta_pct": pct, "delta_pct_str": pct_s, "cmp_range": cmp_rng,
                    "direction": None if pct is None else ("up" if (cur - prev) > 0 else "down" if (cur - prev) < 0 else "flat"),
                    "fact_prev": f_prev["id"], "fact_delta": f_d["id"]})
    return out


def rank(fb, view, metric, dim, filters, rng, n=5, direction="desc", page_id=None):
    md = mdef(view, metric)
    recs, sql = engine.run_records(_q(view, [metric], rng, filters, group_by=[dim], sort=metric, sort_dir=direction, limit=max(n, 1)))
    total_recs, _ = engine.run_records(_q(view, [metric], rng, filters))
    total = total_recs[0][metric] if total_recs else None
    rows = []
    for r in recs:
        f = fb.add(f"{md['label']} for {r[dim]} ({rng['label']})", r[metric], md["fmt"], view, metric,
                   {**filters, dim: [r[dim]]}, rng, sql, page_id=page_id)
        share = (100.0 * r[metric] / total) if (md["additive"] and total) else None
        if share is not None:
            fb.add_text(f"share {r[dim]}", f"{share:.1f}%", view, metric, filters, rng, sql, kind="share")
        rows.append({"member": r[dim], "value": r[metric], "formatted": f["formatted"], "share": share,
                     "share_str": None if share is None else f"{share:.1f}%", "fact": f["id"]})
    return {"metric": metric, "label": md["label"], "dim": dim, "dim_label": C.DIMENSION_LABELS[dim], "rows": rows,
            "direction": direction, "fmt": md["fmt"], "sql": sql}


def compare_entities(fb, view, metric, dim, members, filters, rng, cmp_rng=None, page_id=None):
    md = mdef(view, metric)
    f2 = {k: v for k, v in filters.items() if k != dim}
    f2[dim] = members
    recs, sql = engine.run_records(_q(view, [metric], rng, f2, group_by=[dim]))
    prev = {}
    if cmp_rng:
        recs2, sql2 = engine.run_records(_q(view, [metric], cmp_rng, f2, group_by=[dim]))
        prev = {r[dim]: r[metric] for r in recs2}
    rows = []
    for r in sorted(recs, key=lambda x: -(x[metric] or 0)):
        f = fb.add(f"{md['label']} for {r[dim]} ({rng['label']})", r[metric], md["fmt"], view, metric, {**f2, dim: [r[dim]]}, rng, sql, page_id=page_id)
        row = {"member": r[dim], "value": r[metric], "formatted": f["formatted"], "fact": f["id"]}
        if cmp_rng and r[dim] in prev:
            abs_s, pct, pct_s = fmt_delta(r[metric], prev[r[dim]], md["fmt"])
            fb.add_text(f"change {r[dim]}", pct_s, view, metric, f2, rng, sql, kind="pct")
            fb.add_text(f"change abs {r[dim]}", abs_s, view, metric, f2, rng, sql, kind="abs")
            row.update({"prev": prev[r[dim]], "delta_pct": pct, "delta_pct_str": pct_s, "delta_abs_str": abs_s})
        rows.append(row)
    gap = None
    if len(rows) >= 2 and rows[0]["value"] and rows[1]["value"]:
        g = 100.0 * (rows[0]["value"] - rows[1]["value"]) / abs(rows[1]["value"])
        gap = f"{g:.1f}%"
        fb.add_text("gap", gap, view, metric, f2, rng, sql, kind="pct")
    return {"metric": metric, "label": md["label"], "dim": dim, "dim_label": C.DIMENSION_LABELS[dim], "rows": rows,
            "gap_pct_str": gap, "fmt": md["fmt"], "sql": sql}


def period_label(p, grain):
    d = date.fromisoformat(p)
    if grain == "month":
        return d.strftime("%b %Y")
    if grain == "quarter":
        return f"Q{(d.month - 1)//3 + 1} {d.year}"
    if grain == "year":
        return str(d.year)
    if grain == "week":
        return "wk " + d.strftime("%d %b")
    return d.strftime("%d %b %Y")


def auto_grain(rng, view):
    days = (date.fromisoformat(rng["end"]) - date.fromisoformat(rng["start"])).days + 1
    if VIEWS[view]["min_grain"] == "month":
        return "month"
    if days > 370:
        return "month"
    if days > 200:
        return "month"
    if days > 45:
        return "week"
    return "day"


def trim_partial_weeks(rows, rng, key="period"):
    """Drop week buckets that are cut off by the range edges (they look like fake dips)."""
    from datetime import timedelta
    s, e = date.fromisoformat(rng["start"]), date.fromisoformat(rng["end"])
    out = []
    for r in rows:
        b = date.fromisoformat(r[key] if isinstance(r, dict) else r[0])
        if b < s or b + timedelta(days=6) > e:
            continue
        out.append(r)
    return out if len(out) >= 2 else rows


def trend(fb, view, metric, filters, rng, grain=None, page_id=None):
    md = mdef(view, metric)
    g = grain if grain and grain != "auto" else auto_grain(rng, view)
    recs, sql = engine.run_records(_q(view, [metric], rng, filters, grain=g))
    if g == "week":
        recs = trim_partial_weeks(recs, rng)
    pts = [(period_label(r["period"], g), r[metric]) for r in recs if r[metric] is not None]
    if view == "retail":
        from backend.nlu import timeparse
        lo, hi = date.fromisoformat(rng["start"]), date.fromisoformat(rng["end"])
        labelled = []
        for row, (label, value) in zip([r for r in recs if r[metric] is not None], pts):
            start = date.fromisoformat(row["period"])
            end = timeparse.month_end(start.year, start.month) if g == "month" else start
            partial = g == "month" and (start < lo or end > hi)
            label += " (partial)" if partial else ""
            labelled.append((label,value))
            fb.add(f"{md['label']} in {label}",value,md["fmt"],view,metric,filters,rng,sql,page_id=page_id,
                   extra={"period_start":max(start,lo).isoformat(),"period_end":min(end,hi).isoformat()})
        pts = labelled
    out = {"metric": metric, "label": md["label"], "grain": g, "points": pts, "fmt": md["fmt"], "sql": sql}
    if len(pts) < 2:
        return out
    # drop a trailing partial week (week buckets that start before range end but are cut)
    vals = [v for _, v in pts]
    first, last = pts[0], pts[-1]
    f_first = fb.add(f"{md['label']} in first period ({first[0]})", first[1], md["fmt"], view, metric, filters, rng, sql, page_id=page_id)
    f_last = fb.add(f"{md['label']} in last period ({last[0]})", last[1], md["fmt"], view, metric, filters, rng, sql, page_id=page_id)
    abs_s, pct, pct_s = fmt_delta(last[1], first[1], md["fmt"])
    fb.add_text("trend change", pct_s, view, metric, filters, rng, sql, kind="pct")
    fb.add_text("trend change abs", abs_s, view, metric, filters, rng, sql, kind="abs")
    peak = max(pts, key=lambda x: x[1])
    trough = min(pts, key=lambda x: x[1])
    f_peak = fb.add(f"Peak {md['label']} ({peak[0]})", peak[1], md["fmt"], view, metric, filters, rng, sql, page_id=page_id)
    f_trough = fb.add(f"Lowest {md['label']} ({trough[0]})", trough[1], md["fmt"], view, metric, filters, rng, sql, page_id=page_id)
    # linear slope (% of mean per period)
    n = len(vals)
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(vals) / n
    den = sum((x - mx) ** 2 for x in xs) or 1
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, vals)) / den
    slope_pct = 100 * slope / my if my else 0
    fb.add_text("slope", f"{slope_pct:+.1f}%", view, metric, filters, rng, sql, kind="pct")
    # robust anomalies vs median absolute deviation of period-over-period changes
    anomalies = []
    if n >= 5:
        med = statistics.median(vals)
        mad = statistics.median([abs(v - med) for v in vals]) or 1e-9
        for (p, v) in pts:
            z = 0.6745 * (v - med) / mad
            if abs(z) > 3.0:
                fa = fb.add(f"{md['label']} in {p}", v, md["fmt"], view, metric, filters, rng, sql, page_id=page_id)
                anomalies.append({"period": p, "value": v, "formatted": fa["formatted"], "z": round(z, 1),
                                  "kind": "spike" if z > 0 else "dip"})
    out.update({"first": {"period": first[0], "formatted": f_first["formatted"]},
                "last": {"period": last[0], "formatted": f_last["formatted"]},
                "change_pct": pct, "change_pct_str": pct_s, "change_abs_str": abs_s,
                "peak": {"period": peak[0], "formatted": f_peak["formatted"]},
                "trough": {"period": trough[0], "formatted": f_trough["formatted"]},
                "slope_pct": slope_pct, "slope_str": f"{slope_pct:+.1f}%", "anomalies": anomalies[:4]})
    return out


# ---------------------------------------------------------------------------
# Driver (contribution) analysis
# ---------------------------------------------------------------------------
def _decompose(view, metric, dim, filters, rng, cmp_rng):
    """Return (rows, total_cur, total_prev, sql) where rows have contribution c_i and base share s_i."""
    md = mdef(view, metric)
    additive = md["additive"] or (view, metric) in ADDITIVE_ACROSS_DIMS
    wm = RATIO_WEIGHTS.get((view, metric))
    metrics = [metric] + ([wm] if (not additive and wm) else [])
    cur, sql1 = engine.run_records(_q(view, metrics, rng, filters, group_by=[dim]))
    prev, sql2 = engine.run_records(_q(view, metrics, cmp_rng, filters, group_by=[dim]))
    tc, _ = engine.run_records(_q(view, [metric], rng, filters))
    tp, _ = engine.run_records(_q(view, [metric], cmp_rng, filters))
    T1 = tc[0][metric] if tc else None
    T0 = tp[0][metric] if tp else None
    members = sorted({r[dim] for r in cur} | {r[dim] for r in prev})
    c = {r[dim]: r for r in cur}
    p = {r[dim]: r for r in prev}
    rows = []
    if additive:
        base_tot = sum((p.get(m, {}).get(metric) or 0) for m in members) or 1e-9
        for m in members:
            v1 = c.get(m, {}).get(metric) or 0
            v0 = p.get(m, {}).get(metric) or 0
            rows.append({"member": m, "cur": v1, "prev": v0, "contrib": v1 - v0, "base_share": v0 / base_tot})
    else:
        if wm:
            W1 = sum((c.get(m, {}).get(wm) or 0) for m in members) or 1e-9
            W0 = sum((p.get(m, {}).get(wm) or 0) for m in members) or 1e-9
        for m in members:
            v1 = c.get(m, {}).get(metric)
            v0 = p.get(m, {}).get(metric)
            if wm:
                s1 = (c.get(m, {}).get(wm) or 0) / W1
                s0 = (p.get(m, {}).get(wm) or 0) / W0
            else:
                s1 = s0 = 1.0 / max(1, len(members))
            contrib = s1 * (v1 or 0) - s0 * (v0 or 0)
            rows.append({"member": m, "cur": v1, "prev": v0, "contrib": contrib, "base_share": s0})
    return rows, T1, T0, sql1 + " ; " + sql2


def drivers(fb, view, metric, filters, rng, cmp_rng, locate=None):
    md = mdef(view, metric)
    head = kpi(fb, view, metric, filters, rng, cmp_rng)
    T1, T0 = head["value"], head.get("prev")
    if T1 is None or T0 is None:
        return {"status": "no_data", "headline": head}
    delta = T1 - T0
    rel = abs(delta) / abs(T0) if T0 else 0
    material = rel >= 0.03 or (md["fmt"] == "pct" and abs(delta) >= 0.3)
    result = {"status": "ok" if material else "no_material_change", "headline": head, "levels": []}
    if not material:
        return result

    def best_dim(flt, exclude):
        best = None
        for dim in VIEWS[view]["dims"]:
            if dim in exclude or (dim in flt and len(flt[dim]) == 1):
                continue
            rows, t1, t0, sql = _decompose(view, metric, dim, flt, rng, cmp_rng)
            if len(rows) < 2:
                continue
            dtot = (t1 or 0) - (t0 or 0)
            if abs(dtot) < 1e-12:
                continue
            for r in rows:
                r["share_of_change"] = r["contrib"] / dtot
                r["excess"] = r["share_of_change"] - r["base_share"]
            rows.sort(key=lambda r: -r["share_of_change"])
            top = rows[0]
            # concentration score: how much more of the change the top member explains than its normal share
            score = top["excess"]
            if best is None or score > best["score"]:
                best = {"dim": dim, "rows": rows, "score": score, "sql": sql, "delta": dtot}
        return best

    lvl1 = best_dim(filters, exclude=set())
    if not lvl1:
        return result
    top1 = lvl1["rows"][0]

    def record_level(lv, flt):
        dim = lv["dim"]
        members = []
        for r in lv["rows"][:4]:
            if r["share_of_change"] <= 0.03:
                continue
            abs_s, pct, pct_s = fmt_delta(r["cur"], r["prev"], md["fmt"])
            fv = fb.add(f"{md['label']} for {r['member']} ({rng['label']})", r["cur"], md["fmt"], view, metric,
                        {**flt, dim: [r["member"]]}, rng, lv["sql"])
            fp = fb.add(f"{md['label']} for {r['member']} ({cmp_rng['label']})", r["prev"], md["fmt"], view, metric,
                        {**flt, dim: [r["member"]]}, cmp_rng, lv["sql"])
            share = f"{100*r['share_of_change']:.0f}%"
            fb.add_text(f"share of change {r['member']}", share, view, metric, flt, rng, lv["sql"], kind="share")
            fb.add_text(f"usual share {r['member']}", f"{100*r['base_share']:.0f}%", view, metric, flt, cmp_rng, lv["sql"], kind="share")
            fb.add_text(f"pct change {r['member']}", pct_s, view, metric, flt, rng, lv["sql"], kind="pct")
            fb.add_text(f"abs change {r['member']}", abs_s, view, metric, flt, rng, lv["sql"], kind="abs")
            members.append({"member": r["member"], "cur": fv["formatted"], "prev": fp["formatted"],
                            "delta_pct_str": pct_s, "delta_abs_str": abs_s, "share_of_change": r["share_of_change"],
                            "share_str": share, "base_share_str": f"{100*r['base_share']:.0f}%"})
        page = locate(view, metric, flt, [dim]) if locate else None
        return {"dim": dim, "dim_label": C.DIMENSION_LABELS[dim], "members": members, "page_id": page,
                "filters": flt, "score": round(lv["score"], 3)}

    result["levels"].append(record_level(lvl1, filters))
    f2 = {**filters, lvl1["dim"]: [top1["member"]]}
    lvl2 = best_dim(f2, exclude={lvl1["dim"]})
    if lvl2 and lvl2["rows"][0]["share_of_change"] > 0.2 and lvl2["score"] > 0.08:
        result["levels"].append(record_level(lvl2, f2))
    else:
        result["broad_within_driver"] = True
    result["driver"] = {"dim": lvl1["dim"], "member": top1["member"], "share_of_change": top1["share_of_change"]}

    # volume vs price split for revenue
    if view == "sales" and metric == "revenue":
        o = kpi(fb, "sales", "orders", filters, rng, cmp_rng)
        a = kpi(fb, "sales", "aov", filters, rng, cmp_rng)
        result["mix"] = {"orders": o, "aov": a}
    return result


# ---------------------------------------------------------------------------
# Cross-view cause hypotheses
# ---------------------------------------------------------------------------
def _map_filters(filters, mapping, to_view):
    out = {}
    for f, vals in filters.items():
        if f not in mapping:
            continue
        tf = mapping[f]
        if tf not in VIEWS[to_view]["dims"]:
            continue
        if f == "city" and tf == "warehouse":
            vals = sorted({C.CITY_WAREHOUSE[v] for v in vals})
        out.setdefault(tf, [])
        for v in vals:
            if v not in out[tf]:
                out[tf].append(v)
    return out


def _goodness(view, metric, delta):
    pol = SIGNAL_POLARITY.get((view, metric))
    if pol is None:
        g = mdef(view, metric)["good"]
        pol = +1 if g == "up" else -1 if g == "down" else 0
    return pol * (1 if delta > 0 else -1 if delta < 0 else 0)


def causes(fb, view, metric, filters, rng, cmp_rng, driver=None, locate=None):
    head_cur, _ = engine.scalar(view, metric, rng["start"], rng["end"], filters)
    head_prev, _ = engine.scalar(view, metric, cmp_rng["start"], cmp_rng["end"], filters)
    if head_cur is None or head_prev is None:
        return []
    target_good = _goodness(view, metric, head_cur - head_prev)
    if target_good == 0:
        target_good = 1 if head_cur > head_prev else -1
    hyps = []
    seen = set()
    for a, b, mapping, label in VIEW_LINKS:
        if a != view:
            continue
        base = _map_filters(filters, mapping, b)
        sliced = dict(base)
        is_sliced = False
        if driver and driver["dim"] in mapping:
            extra = _map_filters({driver["dim"]: [driver["member"]]}, mapping, b)
            for k, v in extra.items():
                sliced[k] = v
                is_sliced = True
        for sm in SIGNALS[b]:
            if (b, sm) in seen or (b == view and sm == metric):
                continue
            seen.add((b, sm))
            flt = sliced
            v1, sql1 = engine.scalar(b, sm, rng["start"], rng["end"], flt)
            v0, sql0 = engine.scalar(b, sm, cmp_rng["start"], cmp_rng["end"], flt)
            if v1 is None or v0 is None:
                continue
            d = v1 - v0
            pct = (100 * d / abs(v0)) if v0 else (999.0 if d > 0 else 0.0)
            if abs(pct) < 5:
                continue
            g = _goodness(b, sm, d)
            consistent = (g != 0 and g == target_good)
            if not consistent:
                continue
            strength = min(abs(pct), 300) / 100 * (1.0 if is_sliced else 0.75)
            md = mdef(b, sm)
            f1 = fb.add(f"{md['label']} ({rng['label']})", v1, md["fmt"], b, sm, flt, rng, sql1)
            f0 = fb.add(f"{md['label']} ({cmp_rng['label']})", v0, md["fmt"], b, sm, flt, cmp_rng, sql0)
            abs_s, _, pct_s = fmt_delta(v1, v0, md["fmt"])
            if v0 == 0:
                pct_s = "new"
            fb.add_text(f"{md['label']} change", pct_s, b, sm, flt, rng, sql1, kind="pct")
            fb.add_text(f"{md['label']} change abs", abs_s, b, sm, flt, rng, sql1, kind="abs")
            hyps.append({"view": b, "view_label": VIEWS[b]["label"], "metric": sm, "label": md["label"],
                         "relation": label, "filters": flt, "cur": f1["formatted"], "prev": f0["formatted"],
                         "delta_pct_str": pct_s, "delta_abs_str": abs_s, "strength": strength, "sliced": is_sliced,
                         "direction": "up" if d > 0 else "down"})
    hyps.sort(key=lambda h: -h["strength"])
    hyps = hyps[:5]
    for h in hyps:
        # localise the signal: where in the related view did it move most?
        best = None
        for dim in VIEWS[h["view"]]["dims"]:
            if dim in h["filters"] and len(h["filters"][dim]) == 1:
                continue
            q1, s1 = engine.run_records(_q(h["view"], [h["metric"]], rng, h["filters"], group_by=[dim]))
            q0, _ = engine.run_records(_q(h["view"], [h["metric"]], cmp_rng, h["filters"], group_by=[dim]))
            p0 = {r[dim]: r[h["metric"]] for r in q0}
            diffs = []
            for r in q1:
                if r[h["metric"]] is None or p0.get(r[dim]) is None:
                    continue
                diffs.append((r[dim], r[h["metric"]] - p0[r[dim]], r[h["metric"]], p0[r[dim]]))
            if len(diffs) < 2:
                continue
            tot = sum(abs(x[1]) for x in diffs) or 1e-9
            diffs.sort(key=lambda x: -abs(x[1]))
            conc = abs(diffs[0][1]) / tot
            if best is None or conc > best["conc"]:
                best = {"dim": dim, "conc": conc, "top": diffs[:2], "sql": s1}
        if best and best["conc"] >= 0.3:
            md = mdef(h["view"], h["metric"])
            where = []
            for member, dlt, v1, v0 in best["top"]:
                if abs(dlt) / (sum(abs(x[1]) for x in best["top"]) or 1) < 0.15:
                    continue
                fv = fb.add(f"{md['label']} for {member} ({rng['label']})", v1, md["fmt"], h["view"], h["metric"],
                            {**h["filters"], best["dim"]: [member]}, rng, best["sql"])
                fp = fb.add(f"{md['label']} for {member} ({cmp_rng['label']})", v0, md["fmt"], h["view"], h["metric"],
                            {**h["filters"], best["dim"]: [member]}, cmp_rng, best["sql"])
                where.append({"member": member, "cur": fv["formatted"], "prev": fp["formatted"]})
            h["where"] = {"dim": best["dim"], "dim_label": C.DIMENSION_LABELS[best["dim"]], "members": where}
            # a signal that is concentrated in one member (e.g. Delivery Delay tickets doubling) is stronger
            # evidence than the diluted total; only trust members with a material base
            member, dlt, v1, v0 = best["top"][0]
            if v0 and abs(v0) > 0 and md["additive"]:
                mpct = 100 * dlt / abs(v0)
                if _goodness(h["view"], h["metric"], dlt) == target_good and abs(mpct) > abs(float(h["delta_pct_str"].rstrip("%").replace("+", "") or 0) if h["delta_pct_str"] not in ("new", "–") else 0):
                    h["strength"] = max(h["strength"], min(abs(mpct), 300) / 100 * 0.8 * min(1.0, best["conc"] + 0.3))
                    h["focus"] = {"member": member, "delta_pct_str": f"{mpct:+.1f}%"}
                    fb.add_text("focus pct", f"{mpct:+.1f}%", h["view"], h["metric"], h["filters"], rng, best["sql"], kind="pct")
        h["page_id"] = locate(h["view"], h["metric"], h["filters"], [h["where"]["dim"]] if h.get("where") else []) if locate else None
    hyps.sort(key=lambda h: -h["strength"])
    hyps = hyps[:3]
    for h in hyps:
        h["confidence"] = "strong" if h["strength"] >= 1.0 else "moderate" if h["strength"] >= 0.3 else "weak"
    return hyps


def retail_contributors(fb, filters, rng, cmp_rng, dim="country", page_id=None):
    """Exact additive deltas over the union of members in both periods."""
    if not cmp_rng: return []
    cur, sql = engine.run_records(_q("retail", ["revenue"], rng, filters, group_by=[dim]))
    prev, sql2 = engine.run_records(_q("retail", ["revenue"], cmp_rng, filters, group_by=[dim]))
    a={r[dim]:r["revenue"] for r in cur}; b={r[dim]:r["revenue"] for r in prev}
    rows=[{'member':member,'delta':(a.get(member) or 0)-(b.get(member) or 0),
           'current':a.get(member,0),'previous':b.get(member,0)} for member in set(a)|set(b)]
    rows.sort(key=lambda x:(-abs(x['delta']),str(x['member'])))
    for row in rows[:5]:
        member=row['member']
        f=fb.add(f"Revenue change attributable to {member}",row['delta'],"gbp","retail","revenue",
                 {**filters,dim:[member]},rng,sql+" ; "+sql2,kind="contribution",page_id=page_id,
                 extra={"comparison_range":cmp_rng,"calculation":"current member revenue minus comparison revenue; absent members count as zero"})
        row['formatted']=f['formatted']
    remainder=sum(row['delta'] for row in rows[5:])
    fb.add("Revenue change from all remaining members",remainder,"gbp","retail","revenue",filters,rng,sql+" ; "+sql2,
           kind="contribution",page_id=page_id,extra={"comparison_range":cmp_rng,"calculation":"sum of member changes outside the five displayed contributors"})
    return rows


def monthly_average(fb, view, metric, filters, rng, direction='above', page_id=None):
    md = mdef(view, metric)
    records, sql = engine.monthly_totals_with_mean(_q(view,[metric],rng,filters,grain='month'))
    average = records[0]['average'] if records else None
    mean = fb.add('Arithmetic mean of complete monthly totals', average, md['fmt'], view, metric, filters, rng, sql,
                  kind='monthly_average', page_id=page_id,
                  extra={'calculation':'SUM(monthly totals) / number of complete calendar months; zero-activity months count as zero; strict comparison.', 'month_count':len(records)})
    rows=[]
    for record in records:
        fact=fb.add(f"{md['label']} in {period_label(record['period'],'month')}",record['value'],md['fmt'],view,metric,filters,rng,sql,
                    page_id=page_id,extra={'period_start':record['period']})
        rows.append({'period':period_label(record['period'],'month'),'value':record['value'],'formatted':fact['formatted'],
                     'matches':record['value']>average if direction=='above' else record['value']<average})
    return {'rows':rows,'average':average,'average_formatted':mean['formatted'],'direction':direction,'fmt':md['fmt'],'label':md['label']}


def olist_contributors(fb,view,metric,dim,filters,rng,cmp_rng,page_id):
    cur,sql=engine.run_records(_q(view,[metric],rng,filters,group_by=[dim]))
    prev,sql2=engine.run_records(_q(view,[metric],cmp_rng,filters,group_by=[dim]))
    a={r[dim]:r[metric] for r in cur};b={r[dim]:r[metric] for r in prev}
    rows=[{'member':m,'delta':(a.get(m) or 0)-(b.get(m) or 0)} for m in set(a)|set(b)]
    rows.sort(key=lambda x:-abs(x['delta']))
    shown=rows[:5]+[{'member':'All remaining members','delta':sum(r['delta'] for r in rows[5:])}]
    for row in shown:
        f=fb.add('Sales change / '+row['member'],row['delta'],'brl',view,metric,filters,rng,sql+' ; '+sql2,
                 kind='contribution',page_id=page_id,extra={'comparison_range':cmp_rng,'calculation':'current member sales minus comparison sales; remaining members summed'})
        row['formatted']=f['formatted']
    return shown
