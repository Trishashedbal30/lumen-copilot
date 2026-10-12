"""Server-side data for every widget on a page, given a UI state (the no-code app's runtime)."""
from datetime import date

from backend.agent.analytics import auto_grain, trim_partial_weeks
from backend.agent.planner import Planner
from backend.nlu import timeparse
from backend.semantic import engine
from backend.semantic.engine import fmt_delta, fmt_value
from backend.semantic.layer import VIEWS, QuerySpec


def resolve_state(planner: Planner, state: dict) -> dict:
    """Fill defaults and resolve presets so that the state is fully concrete."""
    pid = state.get("page_id")
    base = planner.default_state(pid)
    out = dict(base)
    for k, v in state.items():
        if v is not None:
            out[k] = v
    dr = out.get("date_range") or {}
    if dr.get("preset") and not dr.get("start"):
        from backend.datasets import bounds
        view = planner.pages[pid]["view"]
        lo, hi = bounds(view)
        out["date_range"] = (timeparse.Range(lo, hi, "All imported sales", "all_time").to_dict()
                             if (view == "retail" or view.startswith("olist_")) and dr["preset"] == "all_time" else timeparse.resolve_preset(dr["preset"], hi).to_dict())
    out["filters"] = {k: v for k, v in (out.get("filters") or {}).items() if v}
    out["cmp_range"] = Planner.comparison_range(out)
    return out


def _flt(view, filters):
    return {k: v for k, v in filters.items() if k in VIEWS[view]["dims"]}


def render_page(planner: Planner, state: dict) -> dict:
    st = resolve_state(planner, state)
    page = planner.pages[st["page_id"]]
    rng, cmp = st["date_range"], st.get("cmp_range")
    out = {"state": st, "widgets": [], "warnings": []}
    if page['view']=='retail':
        from backend.datasets import bounds
        from backend.nlu.timeparse import month_end
        lo,hi=bounds('retail')
        if rng['end']==hi.isoformat() and hi!=month_end(hi.year,hi.month):
            out['warnings'].append(f"Incomplete month: {hi.strftime('%B %Y')} has data only through {hi.strftime('%d %B')}. Full-month comparisons can be misleading.")
        if page['id'].endswith('.customers'):
            out['warnings'].append("Customer rankings exclude missing Customer IDs. Summary totals include all eligible sales unless filtered to a customer; revenue shares use that total.")
    if page['view'].startswith('olist_'):
        from backend.datasets import bounds
        from backend.nlu.timeparse import month_end
        lo,hi=bounds(page['view'])
        if rng['end']==hi.isoformat() and hi!=month_end(hi.year,hi.month):
            out['warnings'].append(f"Final month is incomplete: purchase-date coverage ends on {hi}. This view excludes orders that are not eligible for its metric definitions.")
        out['warnings'].append("Sales exclude freight and non-delivered orders. Delivery rates use comparable delivered orders; reviews average within each order before comparing groups.")
    for w in page["widgets"]:
        view = w["view"]
        flt = _flt(view, st["filters"])
        try:
            if w["type"] == "kpi":
                md = VIEWS[view]["metrics"][w["metric"]]
                cur, sql = engine.scalar(view, w["metric"], rng["start"], rng["end"], flt)
                d = {"id": w["id"], "type": "kpi", "title": w["title"], "value": cur, "formatted": fmt_value(cur, md["fmt"]),
                     "good": md["good"], "sql": sql}
                if cmp:
                    prev, _ = engine.scalar(view, w["metric"], cmp["start"], cmp["end"], flt)
                    abs_s, pct, pct_s = fmt_delta(cur, prev, md["fmt"])
                    d.update({"prev": prev, "prev_formatted": fmt_value(prev, md["fmt"]), "delta_pct": pct,
                              "delta_pct_str": pct_s, "delta_abs_str": abs_s, "cmp_label": cmp["label"]})
                out["widgets"].append(d)
            elif w["type"] == "line":
                g = st.get("grain") if st.get("grain") not in (None, "auto") else auto_grain(rng, view)
                if VIEWS[view]["min_grain"] == "month":
                    g = "month"
                q = QuerySpec(view=view, metrics=w["metrics"], date_from=rng["start"], date_to=rng["end"], filters=flt, time_grain=g)
                r = engine.run(q)
                if g == "week":
                    r["rows"] = trim_partial_weeks(r["rows"], rng)
                labels = [row[0] for row in r["rows"]]
                series = [{"name": VIEWS[view]["metrics"][m]["label"], "values": [row[i + 1] for row in r["rows"]]}
                          for i, m in enumerate(w["metrics"])]
                d = {"id": w["id"], "type": "line", "title": w["title"], "labels": labels, "series": series, "grain": g,
                     "fmt": VIEWS[view]["metrics"][w["metrics"][0]]["fmt"], "sql": r["sql"]}
                if cmp:
                    q2 = QuerySpec(view=view, metrics=w["metrics"][:1], date_from=cmp["start"], date_to=cmp["end"], filters=flt, time_grain=g)
                    r2 = engine.run(q2)
                    if g == "week":
                        r2["rows"] = trim_partial_weeks(r2["rows"], cmp)
                    d["compare"] = {"name": f"{series[0]['name']} ({cmp['label']})", "values": [row[1] for row in r2["rows"]][:len(labels)]}
                out["widgets"].append(d)
            elif w["type"] in ("bar", "donut"):
                dim, m = w["dimension"], w["metric"]
                q = QuerySpec(view=view, metrics=[m], date_from=rng["start"], date_to=rng["end"], filters=flt,
                              group_by=[dim], sort=m, sort_dir="desc", limit=st.get("top_n") or w.get("limit", 12))
                r = engine.run(q)
                d = {"id": w["id"], "type": w["type"], "title": w["title"], "dimension": dim,
                     "labels": [row[0] for row in r["rows"]], "values": [row[1] for row in r["rows"]],
                     "fmt": VIEWS[view]["metrics"][m]["fmt"], "sql": r["sql"]}
                if cmp and w["type"] == "bar":
                    q2 = QuerySpec(view=view, metrics=[m], date_from=cmp["start"], date_to=cmp["end"], filters=flt, group_by=[dim])
                    prev = {row[0]: row[1] for row in engine.run(q2)["rows"]}
                    d["prev_values"] = [prev.get(l) for l in d["labels"]]
                    d["cmp_label"] = cmp["label"]
                out["widgets"].append(d)
            elif w["type"] == "grid":
                dims, ms = w["dimensions"], w["metrics"]
                srt = st.get("sort") or {}
                sf = srt.get("field") if srt.get("field") in ms + dims else ms[0]
                q = QuerySpec(view=view, metrics=ms, date_from=rng["start"], date_to=rng["end"], filters=flt, group_by=dims,
                              sort=sf, sort_dir=srt.get("dir", "desc"), limit=st.get("top_n") or w.get("top_n", 25))
                r = engine.run(q)
                cols = [{"field": c, "label": (VIEWS[view]["metrics"][c]["label"] if c in VIEWS[view]["metrics"] else c.replace("_", " ").title()),
                         "fmt": VIEWS[view]["metrics"][c]["fmt"] if c in VIEWS[view]["metrics"] else "text"} for c in r["columns"]]
                rows = [[(fmt_value(v, cols[i]["fmt"]) if cols[i]["fmt"] != "text" else v) for i, v in enumerate(row)] for row in r["rows"]]
                out["widgets"].append({"id": w["id"], "type": "grid", "title": w["title"], "columns": cols, "rows": rows,
                                       "raw": r["rows"], "sort": {"field": sf, "dir": srt.get("dir", "desc")}, "sql": r["sql"]})
        except Exception as e:  # never break the whole page because of one widget
            out["widgets"].append({"id": w["id"], "type": w["type"], "title": w["title"], "error": str(e)})
    return out


def grid_csv(planner: Planner, state: dict) -> str:
    data = render_page(planner, state)
    grid = next((w for w in data["widgets"] if w["type"] == "grid" and "raw" in w), None)
    if not grid:
        return ""
    import csv
    import io
    buf = io.StringIO()
    wr = csv.writer(buf)
    wr.writerow([c["label"] for c in grid["columns"]])
    for row in grid["raw"]:
        wr.writerow(row)
    return buf.getvalue()
