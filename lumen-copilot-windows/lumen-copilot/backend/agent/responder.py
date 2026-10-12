"""
Builds the user-facing answer: text, cards (KPI / chart / table / drivers / hypotheses), citations and
follow-up suggestions. All numbers come from the FactBook, never generated, so every figure in the
reply is traceable to a semantic-layer query.
"""
import re

from backend import catalog as C
from backend.agent.analytics import filters_text
from backend.semantic.layer import VIEWS

NUM_RX = re.compile(r"[+\-−]?₹?\d(?:[\d,]*\d)?(?:\.\d+)?\s?(?:Cr|L|%|pp|x|min|hrs|/5)?")


def scope_text(filters):
    if not filters:
        return ""
    parts = []
    for k, v in filters.items():
        if len(v) > 3:
            parts.append(f"{len(v)} {C.DIMENSION_LABELS[k].lower()}s")
        else:
            parts.append(" + ".join(v))
    return " for " + ", ".join(parts)


def plural(w):
    if w.endswith("y") and not w.endswith(("ay", "ey", "oy")):
        return w[:-1] + "ies"
    if w.endswith(("s", "x")):
        return w + "es"
    return w + "s"


def arrow(direction):
    return {"up": "▲", "down": "▼"}.get(direction, "•")


def kpi_card(k, title=None):
    c = {"type": "kpi", "title": title or k["label"], "value": k["formatted"], "range": k["range"]["label"], "good": k["good"]}
    if "delta_pct_str" in k:
        c.update({"delta_pct_str": k["delta_pct_str"], "delta_abs_str": k["delta_abs_str"], "prev": k["prev_formatted"],
                  "cmp_label": k["cmp_range"]["label"], "direction": k["direction"]})
    return c


def faithfulness(text, facts):
    """Every numeric token in the reply must appear in some fact's formatted value."""
    pool = set()
    for f in facts:
        s = str(f["formatted"]).replace("−", "-")
        pool.add(s)
        pool.add(s.lstrip("+-"))
    found, traced, untraced = 0, 0, []
    for m in NUM_RX.finditer(text.replace("−", "-")):
        tok = m.group(0).strip()
        has_unit = bool(re.search(r"(₹|Cr|L|%|pp|x|min|hrs|/5)$", tok)) or tok.startswith(("₹", "+₹", "-₹"))
        if not has_unit and not re.search(r"\d,\d", tok):
            continue  # plain small integers (top 5, list numbering, years, days) are not claims
        found += 1
        core = tok.lstrip("+-")
        if tok in pool or core in pool or any(core in p for p in pool):
            traced += 1
        else:
            untraced.append(tok)
    return {"numbers": found, "traced": traced, "untraced": untraced,
            "score": 1.0 if found == 0 else round(traced / found, 3)}


class Responder:
    def __init__(self, metadata):
        self.meta = metadata
        self.pages = metadata["pages"]

    def crumb(self, pid):
        return " › ".join(self.pages[pid]["breadcrumb"])

    # ------------------------------------------------------------------
    def kpi(self, plan, res):
        k = res["kpi"]
        md = VIEWS[plan.view]["metrics"][k["metric"]]
        txt = f"**{md['label']}**{scope_text(plan.filters)} in {k['range']['label']}: **{k['formatted']}**"
        if "delta_pct_str" in k and k.get("prev") is not None:
            ch = k["delta_abs_str"] if md["fmt"] == "pct" else k["delta_pct_str"]
            txt += f", {arrow(k['direction'])} {ch} vs {k['cmp_range']['label']} ({k['prev_formatted']})."
        else:
            txt += "."
        cards = [kpi_card(k)]
        return txt, cards

    def rank(self, plan, res):
        r = res["rank"]
        if not r["rows"]:
            return "No data for that selection.", []
        rng = plan.range["label"]
        word = "Top" if r["direction"] == "desc" else "Bottom"
        n = len(r["rows"])
        if n == 1:
            row = r["rows"][0]
            sup = plan.superlative or ("highest" if r["direction"] == "desc" else "lowest")
            txt = f"**{row['member']}** has the {sup} {r['label'].lower()}{scope_text(plan.filters)} in {rng}: **{row['formatted']}**"
            txt += f" ({row['share_str']} of total)." if row.get("share_str") else "."
        else:
            txt = f"{word} {n} {plural(r['dim_label'].lower())} by {r['label'].lower()}{scope_text(plan.filters)} ({rng}):"
            for i, row in enumerate(r["rows"], 1):
                txt += f"\n{i}. **{row['member']}**: {row['formatted']}" + (f" ({row['share_str']})" if row.get("share_str") else "")
        cards = [{"type": "bar", "title": f"{r['label']} by {r['dim_label']} · {rng}", "labels": [x["member"] for x in r["rows"]],
                  "series": [{"name": r["label"], "values": [x["value"] for x in r["rows"]]}], "fmt": r["fmt"], "horizontal": True}]
        return txt, cards

    def compare_periods(self, plan, res):
        k = res["kpi"]
        md = VIEWS[plan.view]["metrics"][k["metric"]]
        if k.get("prev") is None:
            return self.kpi(plan, res)
        ch = k["delta_abs_str"] if md["fmt"] == "pct" else f"{k['delta_pct_str']}, {k['delta_abs_str']}"
        txt = (f"**{md['label']}**{scope_text(plan.filters)}: **{k['formatted']}** in {k['range']['label']} vs "
               f"**{k['prev_formatted']}** in {k['cmp_range']['label']} ({arrow(k['direction'])} {ch}).")
        cards = [kpi_card(k)]
        mv = res.get("movers")
        if mv and mv["rows"]:
            rows = [x for x in mv["rows"] if x.get("delta_pct_str")]
            rows.sort(key=lambda x: -abs((x.get("value") or 0) - (x.get("prev") or 0)))
            top = rows[:3]
            if top:
                txt += f"\nBiggest movers by {mv['dim_label'].lower()}: " + "; ".join(
                    f"{x['member']} {x['delta_pct_str']}" for x in top) + "."
            cards.append({"type": "bar", "title": f"{md['label']} by {mv['dim_label']}: {k['range']['label']} vs {k['cmp_range']['label']}",
                          "labels": [x["member"] for x in mv["rows"]],
                          "series": [{"name": k["range"]["label"], "values": [x["value"] for x in mv["rows"]]},
                                     {"name": k["cmp_range"]["label"], "values": [x.get("prev") for x in mv["rows"]]}],
                          "fmt": mv["fmt"]})
        return txt, cards

    def compare_entities(self, plan, res):
        ce = res["entities"]
        rows = ce["rows"]
        if not rows:
            return "No data for that comparison.", []
        parts = [f"**{r['member']}** {r['formatted']}" + (f" ({r['delta_pct_str']} vs {plan.cmp_range['label']})" if r.get("delta_pct_str") and plan.cmp_range else "") for r in rows]
        txt = f"{ce['label']} ({plan.range['label']}): " + " vs ".join(parts) + "."
        if ce.get("gap_pct_str") and len(rows) >= 2:
            txt += f" {rows[0]['member']} is ahead of {rows[1]['member']} by {ce['gap_pct_str']}."
        cards = [{"type": "bar", "title": f"{ce['label']} by {ce['dim_label']} · {plan.range['label']}", "labels": [r["member"] for r in rows],
                  "series": [{"name": plan.range["label"], "values": [r["value"] for r in rows]}] +
                            ([{"name": plan.cmp_range["label"], "values": [r.get("prev") for r in rows]}] if plan.cmp_range and any(r.get("prev") is not None for r in rows) else []),
                  "fmt": ce["fmt"]}]
        return txt, cards

    def trend(self, plan, res):
        t = res["trend"]
        md = VIEWS[plan.view]["metrics"][t["metric"]]
        if len(t["points"]) < 2:
            return f"Not enough data points to describe a trend for {md['label']} in {plan.range['label']}.", []
        verb = "rose" if (t.get("change_pct") or 0) > 1 else "fell" if (t.get("change_pct") or 0) < -1 else "was broadly flat"
        ch = t["change_abs_str"] if md["fmt"] == "pct" else t["change_pct_str"]
        txt = (f"**{md['label']}**{scope_text(plan.filters)} {verb} ({ch}) from {t['first']['formatted']} ({t['first']['period']}) to "
               f"**{t['last']['formatted']}** ({t['last']['period']}), by {t['grain']}. "
               f"Peak: {t['peak']['formatted']} ({t['peak']['period']}); low: {t['trough']['formatted']} ({t['trough']['period']}).")
        if t.get("anomalies"):
            txt += " Unusual points: " + "; ".join(f"{a['kind']} in {a['period']} ({a['formatted']})" for a in t["anomalies"]) + "."
        cards = [{"type": "line", "title": f"{md['label']} by {t['grain']}", "labels": [p for p, _ in t["points"]],
                  "series": [{"name": md["label"], "values": [v for _, v in t["points"]]}], "fmt": t["fmt"],
                  "anomalies": [a["period"] for a in t.get("anomalies", [])]}]
        return txt, cards

    def monthly_average(self, plan, res):
        result = res["monthly_average"]
        matches = [row for row in result["rows"] if row["matches"]]
        text = f"Average monthly {result['label'].lower()}{scope_text(plan.filters)} in {plan.range['label']}: **{result['average_formatted']}**."
        text += "\nThis is the arithmetic mean of complete calendar-month totals, including zero-activity months."
        text += f"\nMonths strictly {result['direction']} this average:"
        if matches:
            text += "\n" + "\n".join(f"- **{row['period']}**: {row['formatted']}" for row in matches)
        else:
            text += " none."
        cards = [{"type":"line", "title":f"Monthly {result['label']} versus average", "labels":[row['period'] for row in result['rows']],
                  "series":[{"name":result['label'],"values":[row['value'] for row in result['rows']]},
                            {"name":"Monthly average","values":[result['average'] for row in result['rows']]}], "fmt":result['fmt']}]
        return text, cards

    def drivers(self, plan, res, intent_text=""):
        d = res["drivers"]
        k = d["headline"]
        md = VIEWS[plan.view]["metrics"][k["metric"]]
        if d["status"] == "no_data":
            return "I couldn't find data for that period and selection.", []
        ch = k["delta_abs_str"] if md["fmt"] == "pct" else k["delta_pct_str"]
        moved = "rose" if k["direction"] == "up" else "fell" if k["direction"] == "down" else "was flat"
        asked_down = bool(re.search(r"\b(drop|dip|fall|fell|decline|decrease|down|lower|loss|worse|gira|drop)\b", intent_text))
        asked_up = bool(re.search(r"\b(spike|jump|increase|rise|rose|grow|growth|up|higher|surge|better|badh)\b", intent_text))
        lines = []
        if (asked_down and k["direction"] == "up") or (asked_up and k["direction"] == "down"):
            lines.append(f"Small correction: {md['label'].lower()} actually **{moved}**, it didn't {'drop' if asked_down else 'rise'}.")
        lines.append(f"**{md['label']}**{scope_text(plan.filters)} {moved} **{ch}**: {k['formatted']} in {k['range']['label']} vs {k['prev_formatted']} in {k['cmp_range']['label']}.")
        cards = [kpi_card(k)]
        if d["status"] == "no_material_change":
            lines.append("That change is within normal variation, so there's no single driver to point to.")
            return "\n".join(lines), cards
        lv = d["levels"]
        if lv:
            l1 = lv[0]
            m = l1["members"][0] if l1["members"] else None
            if m:
                dk = "delta_abs_str" if md["fmt"] == "pct" else "delta_pct_str"
                lines.append(f"**Where:** {m['member']} ({l1['dim_label'].lower()}) accounts for **{m['share_str']}** of the change "
                             f"({m['prev']} → {m['cur']}, {m[dk]}), versus its usual {m['base_share_str']} share.")
                others = [x for x in l1["members"][1:3]]
                if others:
                    lines.append("Next: " + "; ".join(f"{x['member']} {x['share_str']} ({x[dk]})" for x in others) + ".")
            if len(lv) > 1 and lv[1]["members"]:
                l2 = lv[1]
                lines.append(f"Within {m['member']}, it's concentrated in " + ", ".join(
                    f"{x['member']} ({x[dk]})" for x in l2["members"][:2]) + ".")
            elif d.get("broad_within_driver") and m:
                others_d = [C.DIMENSION_LABELS[x].lower() for x in VIEWS[plan.view]["dims"] if x != l1["dim"] and x not in plan.filters][:3]
                lines.append(f"Within {m['member']} the change is broad-based: no single {', '.join(others_d) or 'sub-group'} stands out.")
            cards.append({"type": "drivers", "title": f"Contribution to change by {l1['dim_label']}",
                          "labels": [x["member"] for x in l1["members"]],
                          "values": [round(100 * x["share_of_change"], 1) for x in l1["members"]],
                          "detail": [f"{x['prev']} → {x['cur']} ({x['delta_pct_str']})" for x in l1["members"]]})
        mix = d.get("mix")
        if mix and mix["orders"].get("delta_pct_str"):
            lines.append(f"**Volume vs price:** orders {mix['orders']['delta_pct_str']}, average order value {mix['aov']['delta_pct_str']}.")
        hy = res.get("causes") or []
        if hy and hy[0]["confidence"] == "strong":
            hy = [h for h in hy if h["confidence"] != "weak"]
        res["causes"] = hy
        if hy:
            items = []
            for i, h in enumerate(hy, 1):
                where = ""
                if h.get("where") and h["where"]["members"]:
                    where = ", concentrated in " + " and ".join(f"{x['member']} ({x['prev']} → {x['cur']})" for x in h["where"]["members"])
                focus = f" ({h['focus']['member']} {h['focus']['delta_pct_str']})" if h.get("focus") and not h.get("where") else ""
                arrow_s = "↑" if h["direction"] == "up" else "↓"
                if i == 1:
                    lines.append(f"**Most likely cause:** {h['view_label'].lower()} data shows **{h['label']} {arrow_s}** {h['prev']} → {h['cur']}{focus}{where} *{h['confidence']}*. "
                                 + ("Other co-moving signals are listed below. " if len(hy) > 1 else "")
                                 + "This is a correlation across linked data, not proof.")
                items.append({"title": f"{h['view_label']}: {h['label']} {arrow_s}", "detail": f"{h['prev']} → {h['cur']}{where}",
                              "confidence": h["confidence"], "relation": h["relation"], "page_id": h.get("page_id"),
                              "filters": h["filters"]})
            cards.append({"type": "hypotheses", "title": "Likely causes", "items": items})
        else:
            lines.append("I didn't find a consistent signal in related data (inventory, marketing, delivery, support, customers), so the cause may be outside the data I can see.")
        return "\n".join(lines), cards

    # ------------------------------------------------------------------
    def suggestions(self, plan, res):
        s = []
        if plan.kind != "act":
            return s
        v = plan.view
        if v.startswith('olist_'):
            return [{'label':'Delivery and reviews','utterance':'Compare review scores for late and on-time deliveries in 2017'},
                    {'label':'Late-delivery states','utterance':'Top 5 states by late delivery rate in 2017'},
                    {'label':'Sales trend','utterance':'Show monthly sales value for 2017'}]
        if v == "retail" and plan.analysis in ('compare_periods','drivers') and plan.metrics[0]=='revenue':
            return [{"label":"Product contributors","utterance":"Which products contributed most to the change?"},
                    {"label":"Country contributors","utterance":"Which countries contributed most to the change?"},
                    {"label":"Top customers","utterance":"Top 10 customers by revenue"}]
        if v == "retail":
            return [{"label":"Compare available months","utterance":"Compare revenue in two available months"},
                    {"label":"Top countries","utterance":"Top 5 countries by revenue"},
                    {"label":"Top products","utterance":"Top 5 products by revenue"},
                    {"label":"Monthly trend","utterance":"Show monthly revenue"}]
        if plan.analysis in ("kpi", "compare_periods", "rank"):
            s.append({"label": "Why did it change?", "utterance": "why did it change?"})
            if plan.analysis != "rank":
                b = self.pages[plan.page_id]["breakdowns"]
                if b:
                    s.append({"label": f"Break down by {C.DIMENSION_LABELS[b[0]].lower()}", "utterance": f"show it by {C.DIMENSION_LABELS[b[0]].lower()}"})
            s.append({"label": "Compare with last year", "utterance": "compare with same period last year"})
            s.append({"label": "Show the trend", "utterance": "show the trend over the last 12 months"})
        elif plan.analysis == "drivers":
            hy = res.get("causes") or []
            if hy and hy[0].get("page_id"):
                s.append({"label": f"Open {self.pages[hy[0]['page_id']]['title']}", "utterance": f"open {self.pages[hy[0]['page_id']]['title'].lower()} for {plan.range['label'].lower()}"})
            s.append({"label": "Show the trend", "utterance": "show the trend over the last 12 months"})
            s.append({"label": "Compare with last year", "utterance": "compare with same period last year"})
        elif plan.analysis == "trend":
            s.append({"label": "Why did it change?", "utterance": "why did it change last month?"})
            s.append({"label": "Show by month", "utterance": "show it monthly"})
        elif plan.analysis == "compare_entities":
            s.append({"label": "Why the gap?", "utterance": "why did it change?"})
            s.append({"label": "Show the trend", "utterance": "show the trend over the last 12 months"})
        return s[:4]

    def citations(self, plan, res):
        cites = []
        if plan.target_state:
            cites.append({"label": self.crumb(plan.page_id), "state": plan.target_state, "kind": "destination"})
        d = res.get("drivers") or {}
        for lv in d.get("levels", [])[:1]:
            if lv.get("page_id"):
                cites.append({"label": f"{self.pages[lv['page_id']]['title']} · {lv['dim_label']}",
                              "state": {"page_id": lv["page_id"], "filters": lv["filters"], "date_range": plan.range,
                                        "compare": "custom" if plan.cmp_range else "none", "compare_range": plan.cmp_range},
                              "kind": "evidence"})
        for h in (res.get("causes") or []):
            if h.get("page_id"):
                cites.append({"label": f"{self.pages[h['page_id']]['title']} · {h['label']}",
                              "state": {"page_id": h["page_id"], "filters": h["filters"], "date_range": plan.range,
                                        "compare": "custom" if plan.cmp_range else "none", "compare_range": plan.cmp_range},
                              "kind": "hypothesis"})
        return cites
