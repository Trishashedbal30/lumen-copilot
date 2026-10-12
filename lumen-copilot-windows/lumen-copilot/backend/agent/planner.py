"""
Planner: ParsedRequest (+ conversation context + current UI state) -> Plan.

Plan = destination page + target UI state + typed actions + which analysis to run.
Page selection is a two-stage retrieve-then-rerank over the app metadata:
  stage 1: hybrid text retrieval over page documents (BM25 + char n-gram vectors)
  stage 2: structured re-ranking using the knowledge graph (view/metric binding, preset filters,
           filterable fields, breakdown dimensions, explicit page mentions)
"""
import copy
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional

from backend import catalog as C
from backend.datasets import bounds
from backend.agent import dsl
from backend.nlu import timeparse
from backend.nlu.parser import ParsedRequest
from backend.semantic.layer import VIEWS

FIELD_VIEW_PRIORITY = {  # which view a filter field most likely refers to when no metric is given
    "issue_type": "support", "priority": "support", "carrier": "delivery", "mkt_channel": "marketing",
    "campaign": "marketing", "warehouse": "inventory", "channel": "sales", "product": "sales", "category": "sales",
    "city": "sales", "segment": "sales", "region": "sales",
}
SORT_ALIASES = {"gross_margin": "margin_pct", "margin_pct": "gross_margin", "discount": "discount_pct", "discount_pct": "discount",
                "returns": "return_rate", "return_rate": "returns", "late_shipments": "avg_delay_mins", "stockout_days": "in_stock_rate",
                "churned_customers": "churn_rate"}
SUPERLATIVE_HIGH = {"highest", "most", "top", "biggest", "largest", "max", "maximum", "leading", "first"}
SUPERLATIVE_LOW = {"lowest", "least", "bottom", "smallest", "min", "minimum", "lagging", "last"}
SUPERLATIVE_GOOD = {"best"}
SUPERLATIVE_BAD = {"worst", "poorest"}


@dataclass
class Plan:
    kind: str = "act"                 # act | clarify | refuse | help | explain | undo | confirm | greet | reset
    intent: str = "show"
    view: Optional[str] = None
    metrics: List[str] = field(default_factory=list)
    filters: Dict[str, List[str]] = field(default_factory=dict)
    group_by: List[str] = field(default_factory=list)
    range: Optional[dict] = None
    cmp_range: Optional[dict] = None
    cmp_mode: str = "previous_period"
    sort: Optional[dict] = None
    top_n: Optional[int] = None
    grain: str = "auto"
    page_id: Optional[str] = None
    target_state: Optional[dict] = None
    actions: list = field(default_factory=list)
    analysis: Optional[str] = None
    average_direction: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    clarify: Optional[dict] = None
    message: Optional[str] = None
    candidates: list = field(default_factory=list)
    period_options: list = field(default_factory=list)
    entity_compare: Optional[dict] = None
    superlative: Optional[str] = None


def rng_dict(r: timeparse.Range):
    return r.to_dict() if r else None


def to_range(d):
    return timeparse.Range(date.fromisoformat(d["start"]), date.fromisoformat(d["end"]), d.get("label", ""), d.get("preset"))


def implied(field_, value, filters):
    """Is page preset field=value implied by the requested filters (e.g. city=Chennai implies region=South)?"""
    if field_ == "region":
        if "city" in filters and all(C.CITY_REGION.get(c) == value for c in filters["city"]):
            return True
        if "warehouse" in filters and all(C.WAREHOUSE_REGION.get(w) == value for w in filters["warehouse"]):
            return True
    if field_ == "category" and "product" in filters:
        return all(C.PRODUCT_CATEGORY.get(p) == value for p in filters["product"])
    if field_ == "warehouse" and "city" in filters:
        return all(C.CITY_WAREHOUSE.get(c) == value for c in filters["city"])
    return False


class Planner:
    def __init__(self, metadata, index, graph):
        self.meta = metadata
        self.pages = metadata["pages"]
        self.index = index
        self.graph = graph

    # ------------------------------------------------------------------
    # page selection
    # ------------------------------------------------------------------
    def score_page(self, pid, view, metric, filters, group_by, retr=None, mentions=None, parsed=None, ablate=None):
        p = self.pages[pid]
        ablate = ablate or set()
        s = 0.0
        has_metric_widget = pid in self.graph.pages_by_metric.get((view, metric), set())
        if p["view"] == view:
            s += 2.0
        elif has_metric_widget:
            s += 0.8
        else:
            s -= 4.0
        if "structure" not in ablate:
            pm = p["primary_metrics"]
            if metric in pm:
                s += 0.6 + (0.5 if pm[0] == metric else 0.0)
            elif has_metric_widget:
                s += 0.2
            else:
                s -= 0.6
            for f, v in p.get("presets", {}).items():
                req = filters.get(f)
                if req == [v]:
                    s += 2.5
                    # A city is the more specific destination for a city/category intersection.
                    if f == "city" and filters.get("category"):
                        s += 0.8
                elif req and v in req:
                    s -= 2.5
                elif req:
                    s -= 6.0
                elif implied(f, v, filters):
                    s += 0.4
                else:
                    s -= 2.2
            ff = {x["field"] for x in p["filters"]}
            for f in filters:
                if f not in ff:
                    s -= 3.0
            for i, g in enumerate(group_by):
                if p["breakdowns"] and p["breakdowns"][0] == g:
                    s += 1.5 if i == 0 else 0.5
                elif g in p["breakdowns"]:
                    s += 0.8 if i == 0 else 0.3
                else:
                    s -= 0.3
            if p["directory"] == "exec" and not (mentions and pid in mentions):
                s -= 0.4
            if parsed is not None:
                t = p["title"].lower()
                if parsed.intent == "trend" and "trend" in t:
                    s += 0.6
                if p["kind"] == "report":
                    s += 0.4 if re.search(r"\b(report|review|pack|results)\b", parsed.normalized) else -0.6
                if any(w in parsed.normalized.split() for w in ("grid", "table")) and p["kind"] == "grid":
                    s += 0.5
        if view == "retail" and pid == "uci.sales.overview" and "customer_id" not in group_by and "customer_id" not in filters:
            s += 1.0
        if retr and "retrieval" not in ablate:
            s += 2.0 * retr.get(pid, 0.0)
        if mentions and pid in mentions and "mentions" not in ablate:
            s += (4.0 if mentions[pid] >= 0.6 * 1.0 and self._is_title_mention(pid, parsed) else 1.6) * mentions[pid]
        return s

    def _is_title_mention(self, pid, parsed):
        if parsed is None:
            return True
        for p_id, sc, phrase in parsed.page_mentions:
            if p_id == pid:
                from backend.nlu.lexicon import norm
                return phrase == norm(self.pages[pid]["title"]) or phrase == "(llm)"
        return False

    def rank_pages(self, view, metric, filters, group_by, query_text=None, parsed=None, ablate=None):
        retr = {}
        if query_text:
            for pid, sc, _ in self.index.search(query_text, k=40):
                retr[pid] = sc
        mentions = {pid: sc for pid, sc, _ in (parsed.page_mentions if parsed else [])}
        scored = [(pid, self.score_page(pid, view, metric, filters, group_by, retr, mentions, parsed, ablate))
                  for pid in self.pages]
        scored.sort(key=lambda x: -x[1])
        return scored

    def locate(self, view, metric, filters, group_by):
        """Best page to show (view, metric, filters, group_by): used for evidence links."""
        return self.rank_pages(view, metric, filters, group_by)[0][0]

    # ------------------------------------------------------------------
    def merge_context(self, pr: ParsedRequest, ctx: dict, current_state: Optional[dict]):
        """Carry slots over from the previous turn for follow-ups ("what about North?", "why?", "last year?")."""
        if not ctx:
            return pr, False
        anchored = bool(pr.metrics or pr.page_mentions)
        if anchored and not pr.followup and not (pr.intent == "configure" and not pr.page_mentions):
            return pr, False
        if anchored and pr.page_mentions and not pr.filters and not (pr.time and pr.time.main):
            return pr, False
        if not pr.followup and not (pr.intent == "configure" and not pr.page_mentions):
            return pr, False
        # a filter that the previous topic's data can't take means the user switched topic
        cview = ctx.get("view")
        if cview and not pr.metrics and any(f not in VIEWS[cview]["dims"] for f in list(pr.filters) + list(pr.excluded)):
            return pr, False
        pr = copy.copy(pr)
        if not pr.average_direction and ctx.get("average_direction") and pr.intent in ("show", "query", "trend", "configure") and (not pr.time or pr.time.grain in (None, "month")):
            pr.average_direction = ctx["average_direction"]
            pr.intent = "trend"
        if not pr.metrics and ctx.get("metrics"):
            pr.metrics = [{"view": ctx["view"], "metric": m, "weak": False, "phrase": "(context)"} for m in ctx["metrics"]]
        new_f = {k: list(v) for k, v in ctx.get("filters", {}).items()}
        if pr.metrics and ctx.get("view") and pr.metrics[0]["view"] != ctx["view"]:
            new_f = {k: v for k, v in new_f.items() if k in VIEWS[pr.metrics[0]["view"]]["dims"]}
        for f, vals in pr.filters.items():
            new_f[f] = vals
            # keep hierarchy consistent
            if f == "region":
                if "city" in new_f and any(C.CITY_REGION[c] not in vals for c in new_f["city"]):
                    new_f.pop("city")
                if "warehouse" in new_f and any(C.WAREHOUSE_REGION[w] not in vals for w in new_f["warehouse"]):
                    new_f.pop("warehouse")
            if f == "city":
                if "region" in new_f and any(C.CITY_REGION[c] not in new_f["region"] for c in vals):
                    new_f.pop("region")
            if f == "category" and "product" in new_f and any(C.PRODUCT_CATEGORY[p] not in vals for p in new_f["product"]):
                new_f.pop("product")
            if f == "product" and "category" in new_f and any(C.PRODUCT_CATEGORY[p] not in new_f["category"] for p in vals):
                new_f.pop("category")
        for f in pr.excluded:
            new_f.pop(f, None)
        pr.filters = new_f
        if not pr.group_by and ctx.get("group_by") and pr.intent not in ("why",):
            pr.group_by = list(ctx["group_by"])
        if pr.time is None or pr.time.main is None:
            tp = timeparse.TimeParse()
            if ctx.get("range"):
                tp.main = to_range(ctx["range"])
            if pr.time is not None:
                tp.compare_mode = pr.time.compare_mode
                tp.grain = pr.time.grain
                tp.comparison = pr.time.comparison
            if tp.compare_mode is None and ctx.get("cmp_range") and ctx.get("cmp_mode") == "custom":
                tp.comparison = to_range(ctx["cmp_range"])
                tp.compare_mode = "custom"
            pr.time = tp
        if pr.intent in ("show", "query") and ctx.get("intent") in ("why", "compare", "trend") and not pr.group_by:
            pr.intent = ctx["intent"]
        if pr.intent == "compare" and ctx.get("intent") == "compare" and pr.time and pr.time.comparison is None \
                and ctx.get("cmp_mode") and pr.time.compare_mode is None:
            pr.time.compare_mode = ctx["cmp_mode"]
        return pr, True

    # ------------------------------------------------------------------
    def plan(self, pr: ParsedRequest, ctx: dict, current_state: Optional[dict], ablate=None) -> Plan:
        P = Plan(intent=pr.intent)
        # ---- special intents ----
        if pr.intent == "write_blocked":
            P.kind = "refuse"
            P.message = ("I have read-only access to this workspace, so I can't change, delete or insert data. "
                         "I can navigate, filter and analyse. Nothing was modified.")
            return P
        if pr.intent == "out_of_scope":
            P.kind = "refuse"
            P.message = ("That's outside this workspace. I can only work with Sahyadri Retail's pages and data "
                         "(sales, delivery, inventory, marketing, customers and support).")
            return P
        if pr.intent == "greeting":
            P.kind = "greet"
            return P
        if pr.intent == "help":
            P.kind = "help"
            return P
        if pr.intent == "undo":
            P.kind = "undo"
            return P
        if pr.intent == "explain_page":
            P.kind = "explain"
            P.page_id = (current_state or {}).get("page_id")
            return P
        if pr.clarification_question:
            P.kind = "clarify"
            P.clarify = {"question": pr.clarification_question, "options": pr.clarification_options}
            return P
        if pr.unknown_entities:
            P.kind = "clarify"
            ent = pr.unknown_entities[0]
            P.clarify = {"question": f"I don't have any data for {ent}. Sahyadri Retail operates in these cities. Which one did you mean?",
                         "options": [{"label": c, "utterance": pr.text.replace(ent, c).replace(ent.lower(), c)} for c in
                                     ["Mumbai", "Bengaluru", "Delhi", "Pune", "Hyderabad"]]}
            return P
        if pr.ambiguities:
            a = pr.ambiguities[0]
            P.kind = "clarify"
            P.clarify = {"question": f"“{a['term']}” could mean more than one thing. Which did you mean?",
                         "options": []}
            for o in a["options"]:
                lab = f"{o['value']} ({C.DIMENSION_LABELS[o['field']].lower()})"
                utt = pr.text.lower().replace(a["term"], o["value"].lower())
                P.clarify["options"].append({"label": lab, "utterance": utt})
            return P

        if pr.intent == "reset":
            P.kind = "reset"
        if pr.intent == "save_view":
            P.kind = "confirm"
            if current_state and not pr.page_mentions:
                P.page_id = current_state["page_id"]
                P.view = self.pages[P.page_id]["view"]
                P.target_state = copy.deepcopy(current_state)
                # Render-time comparison resolution is derived, not a persisted UI control.
                P.target_state.pop("cmp_range", None)
                return P
        if pr.intent == "export":
            P.kind = "export"

        # ---- context carry-over ----
        pr, used_ctx = self.merge_context(pr, ctx, current_state)
        cur_page = (current_state or {}).get("page_id")
        cur_p = self.pages.get(cur_page) if cur_page else None

        # ---- choose view + metric ----
        view, metric = None, None
        if pr.metrics:
            view, metric = pr.metrics[0]["view"], pr.metrics[0]["metric"]
        elif pr.page_mentions and pr.page_mentions[0][1] >= 0.6:
            pp = self.pages[pr.page_mentions[0][0]]
            view, metric = pp["view"], pp["primary_metrics"][0]
        elif pr.view_hints:
            view = pr.view_hints[0]
        else:
            fields = list(pr.filters) + list(pr.excluded)
            special = [FIELD_VIEW_PRIORITY[f] for f in fields if FIELD_VIEW_PRIORITY.get(f) not in (None, "sales")]
            if special:
                view = special[0]
            elif cur_p and (pr.intent in ("configure", "reset", "export", "save_view") or (pr.followup and not ctx)):
                view, metric = cur_p["view"], cur_p["primary_metrics"][0]
            elif fields or pr.group_by or (pr.time and pr.time.main):
                view = cur_p["view"] if cur_p else "sales"
            elif pr.page_mentions:
                pp = self.pages[pr.page_mentions[0][0]]
                view, metric = pp["view"], pp["primary_metrics"][0]
        if view is None:
            if cur_p and pr.intent in ("configure", "reset", "export", "save_view", "query", "show", "compare", "trend", "why"):
                view, metric = cur_p["view"], cur_p["primary_metrics"][0]
            else:
                P.kind = "clarify"
                P.clarify = {"question": "I'm not sure which part of the app you mean. What would you like to look at?",
                             "options": [{"label": "Revenue", "utterance": "show revenue for last month"},
                                         {"label": "On-time delivery", "utterance": "show on-time delivery for last month"},
                                         {"label": "Stockouts", "utterance": "open the stockout monitor"},
                                         {"label": "Customer churn", "utterance": "show churn rate for the last 12 months"}]}
                return P
        if metric is None:
            # prefer the page's primary metric when a page is clearly meant, else the view default
            metric = VIEWS[view]["default_metric"]
        P.view, P.metrics = view, [m["metric"] for m in pr.metrics if m["view"] == view] or [metric]

        # ---- filters: validate against view, map, exclusions ----
        filters = {}
        if getattr(pr, "state_mapped", None):
            st_name, cities = pr.state_mapped
            P.notes.append(f"Data is organised by city, so I used {', '.join(cities)} for {st_name}.")
        for f, vals in pr.filters.items():
            if f in VIEWS[view]["dims"]:
                filters[f] = list(vals)
            elif f == "city" and "warehouse" in VIEWS[view]["dims"]:
                whs = sorted({C.CITY_WAREHOUSE[c] for c in vals})
                filters["warehouse"] = whs
                P.notes.append(f"{VIEWS[view]['label']} data is tracked per warehouse, so I mapped {', '.join(vals)} to {', '.join(whs)}.")
            elif f == "city" and "region" in VIEWS[view]["dims"]:
                regs = sorted({C.CITY_REGION[c] for c in vals})
                filters["region"] = regs
                P.notes.append(f"{VIEWS[view]['label']} data isn't split by city, so I used the {', '.join(regs)} region instead.")
            elif f == "warehouse" and "region" in VIEWS[view]["dims"]:
                regs = sorted({C.WAREHOUSE_REGION[w] for w in vals})
                filters["region"] = regs
                P.notes.append(f"{VIEWS[view]['label']} data isn't split by warehouse, so I used the {', '.join(regs)} region.")
            else:
                P.notes.append(f"{VIEWS[view]['label']} data can't be filtered by {C.DIMENSION_LABELS[f].lower()}, so I ignored “{', '.join(vals)}”.")
        for f, vals in pr.excluded.items():
            if f in VIEWS[view]["dims"]:
                keep = [v for v in C.DIMENSION_VALUES[f] if v not in vals]
                filters[f] = keep
                P.notes.append(f"Excluded {', '.join(vals)}: {C.DIMENSION_LABELS[f].lower()} filter set to the remaining {len(keep)} values.")
        group_by = [g for g in pr.group_by if g in VIEWS[view]["dims"]]
        dropped_g = [g for g in pr.group_by if g not in VIEWS[view]["dims"]]
        for g in dropped_g:
            if g == "city" and "warehouse" in VIEWS[view]["dims"]:
                group_by.append("warehouse")
            else:
                P.notes.append(f"{VIEWS[view]['label']} data can't be broken down by {C.DIMENSION_LABELS[g].lower()}.")

        # entity comparison: "north vs south", "compare mobile app and online store"
        multi = [f for f, v in pr.filters.items() if len(v) >= 2 and f in filters and f not in pr.excluded]
        if pr.intent == "compare" and multi and not (pr.time and pr.time.comparison):
            fld = multi[0]
            P.entity_compare = {"field": fld, "members": filters[fld]}
            if fld not in group_by:
                group_by = [fld] + group_by
        P.filters, P.group_by = filters, group_by

        # ---- time ----
        tp = pr.time or timeparse.TimeParse()
        main = tp.main
        if (view == "retail" or view.startswith("olist_")) and main and main.preset == "all_time":
            lo, hi = bounds(view)
            main = timeparse.Range(lo, hi, "All imported sales", "all_time")
        if main is None and cur_p and used_ctx is False and pr.intent in ("configure", "export", "save_view") and current_state:
            main = to_range(current_state["date_range"]) if current_state.get("date_range", {}).get("start") else None
        if main is None and tp.comparison is not None:
            main = timeparse.resolve_preset("last_month", bounds(view)[1])
            if main.start <= tp.comparison.start:
                main = timeparse.Range(tp.comparison.start, tp.comparison.end, tp.comparison.label)
        if main is None and pr.intent == "why":
            main = timeparse.resolve_preset("last_month", bounds(view)[1])
        if main is None and pr.intent == "trend":
            main = timeparse.resolve_preset("last_12_months", bounds(view)[1])
        data_lo, data_hi = bounds(view)
        if main is not None:
            if main.start > data_hi or main.end < data_lo:
                P.kind = "clarify"
                P.clarify = {"question": f"There's no data for {main.label}. The data covers {data_lo.strftime('%d %b %Y')} to {data_hi.strftime('%d %b %Y')}. Which period should I use instead?",
                             "options": [{"label": "Last month", "utterance": pr.text + " last month"},
                                         {"label": "Year to date", "utterance": pr.text + " this year"},
                                         {"label": "Last 12 months", "utterance": pr.text + " last 12 months"}]}
                return P
            if main.end > data_hi or main.start < data_lo:
                s0, e0 = max(main.start, data_lo), min(main.end, data_hi)
                P.notes.append(f"Data is only available from {data_lo.strftime('%d %b %Y')} to {data_hi.strftime('%d %b %Y')}, so I limited the range to {timeparse.fmt_range_label(s0, e0)}.")
                main = timeparse.Range(s0, e0, timeparse.fmt_range_label(s0, e0))
        cmp_mode = tp.compare_mode or ("previous_period")
        if view.startswith('olist_') and not tp.compare_mode and tp.comparison is None and (P.entity_compare or pr.intent not in ('compare','why')):
            cmp_mode='none'
        cmp_rng = None
        if tp.comparison is not None:
            cmp_rng = tp.comparison
            cmp_mode = "custom"
        P.cmp_mode = cmp_mode
        P.grain = tp.grain or "auto"
        if view == "retail" and not pr.average_direction and main and P.grain == "month" and (main.start.day != 1 or main.end != timeparse.month_end(main.end.year, main.end.month)):
            P.notes.append("Edge months are partial. Compare complete months before interpreting a full-month revenue change.")
        if pr.intent == "trend" and P.grain == "auto" and main is not None and (main.end - main.start).days > 120:
            P.grain = "month"

        # ---- sort / top-n / superlatives ----
        if pr.sort:
            P.sort = dict(pr.sort)
            if not P.sort.get("field"):
                P.sort["field"] = P.metrics[0]
        if pr.superlative:
            P.superlative = pr.superlative
            good = VIEWS[view]["metrics"][P.metrics[0]]["good"]
            sup = pr.superlative
            if sup in SUPERLATIVE_HIGH:
                d = "desc"
            elif sup in SUPERLATIVE_LOW:
                d = "asc"
            elif sup in SUPERLATIVE_GOOD:
                d = "asc" if good == "down" else "desc"
            elif sup in SUPERLATIVE_BAD:
                d = "desc" if good == "down" else "asc"
            else:
                d = "desc"
            if not P.sort:
                P.sort = {"field": P.metrics[0], "dir": d}
        P.top_n = pr.top_n

        # ---- page selection ----
        if P.kind in ("reset", "export", "confirm") and cur_page and not pr.page_mentions:
            page_id = cur_page
        else:
            q_text = re.sub(r"\b(compare|comparison|compared|vs|versus|against|trend|why|caused|cause)\b", " ", pr.masked or pr.normalized)
            ranked = self.rank_pages(view, P.metrics[0], filters, group_by, q_text, pr, ablate)
            P.candidates = ranked[:5]
            page_id = ranked[0][0]
            # follow-up with no new anchor: stay on the current page if it can show the request
            if used_ctx and cur_p and not pr.page_mentions and cur_p["view"] == view and \
                    any(w.get("metric") == P.metrics[0] or P.metrics[0] in w.get("metrics", []) for w in cur_p["widgets"]):
                ff = {x["field"] for x in cur_p["filters"]}
                pres = cur_p.get("presets", {})
                ok = all(f in ff for f in filters) and all(filters.get(f) in (None, [v]) for f, v in pres.items()) \
                    and all(f in filters or implied(f, v, filters) for f, v in pres.items()) \
                    and (not group_by or group_by[0] in cur_p["breakdowns"])
                if ok:
                    page_id = cur_page
            # configure-only request on a compatible current page: stay
            if cur_p and pr.intent == "configure" and not pr.page_mentions and cur_p["view"] == view:
                ff = {x["field"] for x in cur_p["filters"]}
                conflict = any(f in cur_p.get("presets", {}) and filters.get(f) != [v] for f, v in cur_p.get("presets", {}).items() if f in filters)
                if all(f in ff for f in filters) and not conflict:
                    page_id = cur_page
        P.page_id = page_id
        page = self.pages[page_id]

        # superlative without a dimension -> rank by page's main breakdown
        if pr.superlative and not group_by and pr.intent in ("query", "show") and page["breakdowns"] and \
                any(w in pr.normalized.split() for w in ("which", "what", "who", "top", "bottom", "best", "worst")):
            P.group_by = group_by = [page["breakdowns"][0]]

        # ---- target UI state ----
        if P.kind == "reset":
            state = self.default_state(page_id)
            P.target_state = state
            P.actions = self.diff_actions(current_state, state)
            return P
        state = self.default_state(page_id)
        for f, v in page.get("presets", {}).items():
            state["filters"][f] = [v]
        for f, vals in filters.items():
            state["filters"][f] = vals
        if P.entity_compare:
            fld = P.entity_compare["field"]
            if fld in page.get("presets", {}):
                state["filters"][fld] = P.entity_compare["members"]
        if main is not None:
            state["date_range"] = rng_dict(main)
        if cmp_mode == "custom" and cmp_rng is not None:
            state["compare"] = "custom"
            state["compare_range"] = rng_dict(cmp_rng)
        else:
            state["compare"] = cmp_mode
            state["compare_range"] = None
        if P.sort:
            opts = {o["field"] for o in page["sort_options"]}
            if P.sort["field"] not in opts and SORT_ALIASES.get(P.sort["field"]) in opts:
                P.sort["field"] = SORT_ALIASES[P.sort["field"]]
            if P.sort["field"] in opts:
                state["sort"] = {"field": P.sort["field"], "dir": P.sort["dir"]}
            elif P.sort["field"] in VIEWS[view]["metrics"] or P.sort["field"] in VIEWS[view]["dims"]:
                P.notes.append(f"This page's grid can't be sorted by {P.sort['field'].replace('_', ' ')}; I sorted by {page['sort_options'][0]['label'] if page['sort_options'] else 'its default'} instead and answered from the data directly.")
        if P.top_n:
            state["top_n"] = max(1, min(100, int(P.top_n)))
        state["grain"] = P.grain if P.grain in ("auto", "day", "week", "month", "quarter") else "auto"
        if pr.average_direction:
            if not VIEWS[view]["metrics"][P.metrics[0]]["additive"]:
                P.kind = "clarify"
                P.clarify = {"question": "Monthly-average comparison supports additive totals such as revenue; choose a supported metric.", "options": []}
                return P
            start, end = date.fromisoformat(state["date_range"]["start"]), date.fromisoformat(state["date_range"]["end"])
            full_start = start if start.day == 1 else timeparse.month_end(start.year, start.month) + timedelta(days=1)
            full_end = end if end == timeparse.month_end(end.year, end.month) else end.replace(day=1) - timedelta(days=1)
            if full_start > full_end:
                P.kind = "clarify"
                P.clarify = {"question": "Choose a date range containing at least one complete calendar month to compare monthly totals with their average.", "options": []}
                return P
            if (full_start, full_end) != (start, end):
                P.notes.append("Excluded partial edge months so the average compares complete calendar months.")
            state["date_range"] = {"start": full_start.isoformat(), "end": full_end.isoformat(), "label": timeparse.fmt_range_label(full_start, full_end)}
            state["grain"] = P.grain = "month"
            state["compare"] = P.cmp_mode = "none"
            state["compare_range"] = None
            P.group_by = []
            P.average_direction = pr.average_direction
        P.target_state = state
        P.range = state["date_range"]
        P.cmp_range = self.comparison_range(state)
        if (view == "retail" or view.startswith("olist_")) and P.cmp_range:
            lo, hi = bounds(view)
            cs, ce = date.fromisoformat(P.cmp_range["start"]), date.fromisoformat(P.cmp_range["end"])
            if cs < lo or ce > hi:
                if cs <= hi and ce >= lo and (pr.intent == "compare" or tp.comparison is not None):
                    clipped={"start":max(cs,lo).isoformat(),"end":min(ce,hi).isoformat(),"label":timeparse.fmt_range_label(max(cs,lo),min(ce,hi))}
                    P.cmp_range=state["compare_range"]=clipped
                    state["compare"]="custom"
                    P.notes.append(f"Comparison period is incomplete; only {clipped['start']} to {clipped['end']} is available.")
                elif pr.intent == "compare" or tp.comparison is not None:
                    P.kind = "clarify"
                    P.clarify = {"question": f"Choose two periods within {lo} to {hi}; the requested comparison is not fully available.", "options": []}
                    P.target_state = None
                    return P
                else:
                    state["compare"] = "none"; state["compare_range"] = None; P.cmp_range = None
                    P.notes.append("Comparison disabled: the full comparison period is outside imported date coverage.")

        if view == "retail":
            lo,hi=bounds(view)
            if P.range['end']==hi.isoformat() and hi.day != timeparse.month_end(hi.year,hi.month).day:
                P.notes.append(f"Incomplete month: {hi.strftime('%B %Y')} has data only through {hi.strftime('%d %B')}; this is not a full-month total.")
            if 'customer_id' in P.group_by or 'customer_id' in filters :
                P.notes.append("Customer rankings exclude missing Customer IDs. Customers are identified by ID, not name; shares use all eligible sales in the selected scope.")
            if P.cmp_range:
                a,b=to_range(P.range),to_range(P.cmp_range)
                if a.start.day==b.start.day==1 and a.start.month==a.end.month and b.start.month==b.end.month and a.end.day!=b.end.day:
                    days=min(a.end.day,b.end.day)
                    md=VIEWS[view]['metrics'][P.metrics[0]]['label']
                    scope=''.join(' for '+C.DIMENSION_LABELS[f]+' '+', '.join(vals) for f,vals in filters.items())
                    P.notes.append("These periods contain different numbers of days; use the equivalent-day comparison for a fairer view.")
                    P.period_options=[{"label":f"Compare first {days} days", "utterance":f"Compare {md}{scope} from {a.start} to {a.start.replace(day=days)} vs {b.start} to {b.start.replace(day=days)}"}]

        # ---- analysis ----
        if P.kind == "confirm":
            P.analysis = None
        elif P.kind == "export":
            P.analysis = None
        elif pr.average_direction:
            P.analysis = "monthly_average"
        elif pr.intent == "why":
            P.analysis = "drivers"
        elif pr.intent == "trend" or (pr.intent in ("show", "query") and tp.grain and not group_by and not pr.superlative and not any(self._is_title_mention(pid, pr) for pid, _, _ in pr.page_mentions)):
            P.analysis = "trend"
        elif pr.intent == "compare":
            P.analysis = "compare_entities" if P.entity_compare else "compare_periods"
        elif group_by and (pr.intent in ("query", "show", "configure") and (pr.superlative or pr.top_n or pr.intent == "query" or pr.sort)):
            P.analysis = "rank"
        elif group_by and pr.intent in ("show",):
            P.analysis = "rank"
        else:
            P.analysis = "kpi"

        P.actions = self.diff_actions(current_state, state)
        return P

    # ------------------------------------------------------------------
    def default_state(self, page_id):
        p = self.pages[page_id]
        ds = p["default_state"]
        lo, hi = bounds(p["view"])
        preset = ds["date_range"]["preset"]
        r = (timeparse.Range(lo, hi, "All imported sales", "all_time") if (p["view"] == "retail" or p["view"].startswith("olist_")) and preset == "all_time"
             else timeparse.resolve_preset(preset, hi))
        return {
            "page_id": page_id,
            "filters": {k: list(v) for k, v in ds["filters"].items()},
            "date_range": r.to_dict(),
            "compare": ds["compare"],
            "compare_range": None,
            "sort": dict(ds["sort"]) if ds.get("sort") else None,
            "top_n": ds.get("top_n"),
            "grain": "auto",
        }

    @staticmethod
    def comparison_range(state):
        dr = state["date_range"]
        r = to_range(dr)
        if state.get("compare") == "custom" and state.get("compare_range"):
            return state["compare_range"]
        if state.get("compare") == "previous_year":
            return timeparse.previous_year(r).to_dict()
        if state.get("compare") == "none":
            return None
        return timeparse.previous_period(r).to_dict()

    def diff_actions(self, cur, tgt):
        acts = []
        same_page = cur and cur.get("page_id") == tgt["page_id"]
        if not same_page:
            acts.append(dsl.Navigate(page_id=tgt["page_id"]))
            base = self.default_state(tgt["page_id"])
        else:
            base = cur
        bf = base.get("filters", {}) or {}
        for f in sorted(set(bf) | set(tgt["filters"])):
            a, b = sorted(bf.get(f, [])), sorted(tgt["filters"].get(f, []))
            if a != b:
                if b:
                    acts.append(dsl.SetFilter(field=f, values=tgt["filters"][f]))
                else:
                    acts.append(dsl.ClearFilter(field=f))
        bd, td = base.get("date_range") or {}, tgt["date_range"]
        if (bd.get("start"), bd.get("end")) != (td["start"], td["end"]) or not same_page and td.get("preset") is None:
            acts.append(dsl.SetDateRange(range=dsl.DateRange(**{k: (td.get(k) or "") if k == "label" else td.get(k) for k in ("start", "end", "label", "preset")})))
        if base.get("compare") != tgt["compare"] or (tgt["compare"] == "custom" and base.get("compare_range") != tgt.get("compare_range")):
            rng = dsl.DateRange(**tgt["compare_range"]) if tgt.get("compare_range") else None
            acts.append(dsl.SetCompare(mode=tgt["compare"], range=rng))
        if tgt.get("sort") and base.get("sort") != tgt["sort"]:
            acts.append(dsl.SetSort(field=tgt["sort"]["field"], dir=tgt["sort"]["dir"]))
        if tgt.get("top_n") and base.get("top_n") != tgt["top_n"]:
            acts.append(dsl.SetTopN(n=tgt["top_n"]))
        if tgt.get("grain") and tgt["grain"] != (base.get("grain") or "auto"):
            acts.append(dsl.SetGrain(grain=tgt["grain"]))
        return acts
