"""
Agent controller: a state graph of nodes

    understand -> plan -> validate -> execute -> respond
                     \\-> (clarify / refuse / help / undo / confirm) -> respond

implemented with LangGraph when it is installed (pip install langgraph), with an equivalent built-in
sequential runner as fallback. Every node is timed and logged into a trace that the UI shows.
"""
import copy
import json
import re
import time
import uuid
import threading
from typing import Any, Dict, Optional, TypedDict

from backend import catalog as C
from backend.agent import analytics as A
from backend.agent import dsl
from backend.agent import llm as LLM
from backend.agent.planner import Plan, Planner
from backend.agent.responder import Responder, faithfulness, kpi_card
from backend.agent.validator import Validator
from backend.nlu.parser import RuleParser
from backend.retrieval.graph import AppGraph
from backend.retrieval.index import MetadataIndex
from backend.semantic.layer import VIEWS

try:
    from langgraph.graph import StateGraph, END
    HAVE_LANGGRAPH = True
except Exception:  # pragma: no cover
    HAVE_LANGGRAPH = False

STEP_SPLIT = re.compile(r"\s*(?:;|\band then\b|,\s*then\b|\bthen\b|\bafter that\b)\s*", re.I)


class GState(TypedDict, total=False):
    session: Any
    text: str
    current_state: Optional[dict]
    parsed: Any
    plan: Any
    validation: dict
    result: dict
    facts: Any
    response: dict
    trace: list


class Session:
    def __init__(self, sid):
        self.id = sid
        self.history = []
        self.ctx = {}
        self.stack = []
        self.saved_views = []
        self.pending = {}
        self.turns = {}


class Agent:
    def __init__(self, metadata):
        self.lock = threading.RLock()
        self.meta = metadata
        self.parser = RuleParser(metadata)
        self.index = MetadataIndex(metadata)
        self.graph = AppGraph(metadata)
        self.planner = Planner(metadata, self.index, self.graph)
        self.validator = Validator(metadata)
        self.responder = Responder(metadata)
        self.llm = LLM.LLMUnderstanding(metadata, self.parser.lex)
        self.llm.index = self.index
        self.sessions: Dict[str, Session] = {}
        self.metrics = {"turns": 0, "steps": 0, "actions": 0, "clarifications": 0, "refusals": 0,
                        "blocked_actions": 0, "verified": 0, "verified_ok": 0, "latencies": [],
                        "faithfulness_numbers": 0, "faithfulness_traced": 0, "llm_used": 0}
        self.app = self._build_graph() if HAVE_LANGGRAPH else None

    # ------------------------------------------------------------------
    def session(self, sid):
        if not sid or sid not in self.sessions:
            sid = sid or uuid.uuid4().hex[:12]
            self.sessions[sid] = Session(sid)
        return self.sessions[sid]

    def _t(self, st, node, t0, **detail):
        st.setdefault("trace", []).append({"node": node, "ms": round((time.time() - t0) * 1000, 1), **detail})

    # ---------------- nodes ----------------
    def n_understand(self, st: GState):
        t0 = time.time()
        sess = st["session"]
        text = st["text"]
        from backend.nlu.retail import active_view, adapt
        from backend.datasets import bounds
        view = active_view(text, st.get("current_state"), self.meta)
        family=lambda v: 'olist' if v and v.startswith('olist_') else 'retail' if v=='retail' else 'synthetic'
        if sess.ctx.get('view') and family(sess.ctx['view'])!=family(view):sess.ctx={}
        pr = adapt(self.parser.parse(text, today=bounds(view)[1]), text, view)
        if view.startswith('olist_') and pr.followup and sess.ctx.get('intent')=='compare' and pr.intent in ('show','query','configure') and not (pr.time and pr.time.main):
            pr.intent='compare'
        if pr.average_direction and st.get("current_state"):
            current = st["current_state"]
            if not pr.time.main and current.get("date_range"):
                from backend.agent.planner import to_range
                pr.time.main = to_range(current["date_range"])
            if self.meta["pages"][current["page_id"]]["view"] == view:
                pr.filters = {**(current.get("filters") or {}), **pr.filters}
        used = "rules"
        request_status = "not_requested"
        model_error = None
        m = LLM.mode()
        if LLM.configured() and m in ("llm", "hybrid"):
            weak = (not pr.metrics and not pr.page_mentions and not pr.filters and not pr.view_hints
                    and pr.intent in ("show", "query")) or bool(pr.ambiguities)
            if (m == "llm" or weak) and pr.intent not in ("write_blocked", "out_of_scope", "undo", "reset", "save_view", "export", "help", "greeting", "explain_page") and not pr.ambiguities and not pr.clarification_question:
                request_status = "requested"
                try:
                    model_text = pr.normalized if pr.typo_fixes else text
                    lp = self.llm.parse(model_text, sess.ctx, (st.get("current_state") or {}).get("page_id"))
                    lp.text = text
                    request_status = "response_received_blocked_slots" if getattr(lp, "llm_blocked", []) else "succeeded"
                    if m == "llm" or lp.metrics or lp.filters or lp.page_mentions or lp.clarification_question:
                        # keep deterministic exact controls that the LLM may have missed
                        lp.filters = {**lp.filters, **pr.filters}
                        if not lp.group_by: lp.group_by = list(pr.group_by)
                        if lp.top_n is None: lp.top_n = pr.top_n
                        if pr.superlative and pr.metrics:
                            # Ranking controls are grounded by the exact top/bottom request.
                            lp.superlative = pr.superlative
                            lp.sort = pr.sort or {"field":pr.metrics[0]["metric"],"dir":"asc" if pr.superlative in ("bottom","lowest","least") else "desc"}
                        if pr.time and lp.time: lp.time.grain = lp.time.grain or pr.time.grain
                        if pr.time and pr.time.main:
                            lp.time.main = pr.time.main
                        if pr.intent == "compare" and pr.time.main and pr.time.comparison:
                            lp.time = pr.time
                            lp.intent = "compare"
                            if not getattr(lp, "llm_blocked", []) and not pr.ambiguities and not pr.unknown_entities:
                                lp.clarification_question = pr.clarification_question
                        if pr.intent == "trend" and pr.time.grain and not pr.group_by and not pr.superlative:
                            lp.intent = "trend"
                        if pr.average_direction:
                            lp.average_direction = pr.average_direction
                            lp.metrics = pr.metrics or lp.metrics
                            # The grounded mean operation is unambiguous; retain actual blocked-slot errors.
                            if not getattr(lp, "llm_blocked", []) and not pr.ambiguities and not pr.unknown_entities:
                                lp.clarification_question = pr.clarification_question
                            lp.intent = "trend"
                            lp.group_by = []
                            lp.time = pr.time
                        if view=='retail' and (any(m['metric'] in ('retail_orders','retail_quantity','retail_aov') for m in pr.metrics) or 'customer_id' in pr.group_by or pr.intent=='why'):
                            lp.metrics=pr.metrics or lp.metrics
                            lp.group_by=pr.group_by or lp.group_by
                            lp.intent=pr.intent
                            lp.followup=pr.followup
                            if not getattr(lp,'llm_blocked',[]): lp.clarification_question=pr.clarification_question
                        if view.startswith('olist_'):
                            lp.metrics=pr.metrics or lp.metrics;lp.group_by=pr.group_by or lp.group_by;lp.intent=pr.intent;lp.followup=pr.followup
                            if not getattr(lp,'llm_blocked',[]):lp.clarification_question=pr.clarification_question
                        lp.typo_fixes = list(dict.fromkeys(tuple(fix) for fix in lp.typo_fixes + pr.typo_fixes))
                        lp.unknown_entities = list(dict.fromkeys(lp.unknown_entities + pr.unknown_entities))
                        pr = adapt(lp, text, view)
                        used = "llm"
                        self.metrics["llm_used"] += 1
                except Exception as e:
                    request_status = "failed_fallback_to_rules"
                    model_error = str(e)[:200]
                    st.setdefault("trace", []).append({"node": "llm_error", "ms": 0, "error": str(e)[:200]})
        self._t(st, "understand", t0, source=used, intent=pr.intent, model_request_status=request_status,
                model_error=model_error, model_configuration=LLM.configuration(),
                slots={"metrics": [m_["metric"] for m_ in pr.metrics], "filters": pr.filters, "excluded": pr.excluded,
                       "group_by": pr.group_by, "time": pr.time.main.label if pr.time and pr.time.main else None,
                       "typos_fixed": pr.typo_fixes, "followup": pr.followup})
        return {"parsed": pr, "trace": st["trace"]}

    def n_plan(self, st: GState):
        t0 = time.time()
        sess = st["session"]
        plan = self.planner.plan(st["parsed"], sess.ctx, st.get("current_state"))
        self._t(st, "retrieve+plan", t0, kind=plan.kind, page=plan.page_id,
                candidates=[(pid, round(s, 2)) for pid, s in plan.candidates[:3]], analysis=plan.analysis)
        return {"plan": plan, "trace": st["trace"]}

    def n_validate(self, st: GState):
        t0 = time.time()
        plan: Plan = st["plan"]
        v_state = self.validator.check_state(plan.target_state) if plan.target_state else []
        v_act = self.validator.check_actions(plan.actions, plan.target_state) if plan.target_state else []
        blocked = len(v_state) + len(v_act)
        if blocked and not any(v["code"] in ("unknown_page", "invalid_state_shape") for v in v_state):
            plan.target_state, notes = self.validator.repair_state(plan.target_state)
            plan.notes.extend(notes)
        self.metrics["blocked_actions"] += blocked
        post = self.validator.check_state(plan.target_state) if plan.target_state else []
        if post:
            # Validation must be a barrier, not merely a trace entry.
            plan.kind = "refuse"
            plan.message = "The requested view failed validation. Please choose a valid page, date range and filters."
            plan.target_state = None
            plan.actions = []
        elif blocked:
            plan.actions = self.planner.diff_actions(st.get("current_state"), plan.target_state)
        self._t(st, "validate", t0, violations=v_state + v_act, repaired=bool(blocked), remaining=post)
        return {"validation": {"violations": v_state + v_act, "remaining": post}, "trace": st["trace"]}

    def n_execute(self, st: GState):
        t0 = time.time()
        plan: Plan = st["plan"]
        fb = A.FactBook()
        res = {}
        loc = self.planner.locate
        a = plan.analysis
        flt = {k: v for k, v in plan.filters.items()}
        # page presets are part of the scope of the answer too
        for f, v in self.meta["pages"][plan.page_id].get("presets", {}).items():
            if f in VIEWS[plan.view]["dims"] and f not in flt:
                flt[f] = [v]
        if plan.entity_compare:
            flt.pop(plan.entity_compare["field"], None)
        plan.filters = flt
        metric = plan.metrics[0]
        if a == "kpi":
            res["kpi"] = A.kpi(fb, plan.view, metric, flt, plan.range, plan.cmp_range, plan.page_id)
        elif a == "rank":
            dim = plan.group_by[0]
            d = (plan.sort or {}).get("dir", "desc")
            n = plan.top_n or (1 if plan.superlative and not re.search(r"\b(top|bottom)\b", st["text"].lower()) else 5)
            res["rank"] = A.rank(fb, plan.view, metric, dim, flt, plan.range, n, d, plan.page_id)
        elif a == "compare_periods":
            res["kpi"] = A.kpi(fb, plan.view, metric, flt, plan.range, plan.cmp_range, plan.page_id)
            b = self.meta["pages"][plan.page_id]["breakdowns"]
            dim = (plan.group_by or b or [None])[0]
            if dim and plan.cmp_range and not (plan.view=="retail" and dim in ("retail_product","customer_id")):
                members = C.DIMENSION_VALUES[dim] if dim not in flt else flt[dim]
                res["movers"] = A.compare_entities(fb, plan.view, metric, dim, (members if plan.view == "retail" else members[:24]), flt, plan.range, plan.cmp_range, plan.page_id)
            if plan.view == "retail":
                res["retail_contributors"] = A.retail_contributors(fb, flt, plan.range, plan.cmp_range, dim=(plan.group_by or ["country"])[0], page_id=plan.page_id) if metric == "revenue" else []
        elif a == "compare_entities":
            ec = plan.entity_compare
            res["entities"] = A.compare_entities(fb, plan.view, metric, ec["field"], ec["members"], flt, plan.range, plan.cmp_range, plan.page_id)
        elif a == "monthly_average":
            res["monthly_average"] = A.monthly_average(fb, plan.view, metric, flt, plan.range, plan.average_direction, plan.page_id)
        elif a == "trend":
            res["trend"] = A.trend(fb, plan.view, metric, flt, plan.range, plan.grain, plan.page_id)
        elif a == "drivers" and plan.view == "retail":
            res["kpi"] = A.kpi(fb, plan.view, metric, flt, plan.range, plan.cmp_range, plan.page_id)
            res["retail_contributors"] = A.retail_contributors(fb, flt, plan.range, plan.cmp_range, dim=(plan.group_by or ["country"])[0], page_id=plan.page_id) if metric == "revenue" else []
        elif a == "drivers" and plan.view.startswith('olist_'):
            res['kpi']=A.kpi(fb,plan.view,metric,flt,plan.range,plan.cmp_range,plan.page_id)
            if metric=='olist_revenue' and plan.cmp_range:
                res['olist_contributors']=A.olist_contributors(fb,plan.view,metric,(plan.group_by or ['br_state'])[0],flt,plan.range,plan.cmp_range,plan.page_id)
        elif a == "drivers":
            if not plan.cmp_range:
                plan.cmp_range = Planner.comparison_range({**plan.target_state, "compare": "previous_period"})
            d = A.drivers(fb, plan.view, metric, flt, plan.range, plan.cmp_range, locate=loc)
            res["drivers"] = d
            if d.get("status") == "ok":
                res["causes"] = A.causes(fb, plan.view, metric, flt, plan.range, plan.cmp_range, driver=d.get("driver"), locate=loc)
                # show the page that best displays the driver breakdown
                dd = d["driver"]["dim"]
                pf = {k: v for k, v in plan.filters.items()}
                ranked = self.planner.rank_pages(plan.view, metric, pf, [dd], st["parsed"].normalized, None)
                new_pid = ranked[0][0]
                if new_pid != plan.page_id:
                    plan.page_id = new_pid
                    ts = self.planner.default_state(new_pid)
                    for f, v in self.meta["pages"][new_pid].get("presets", {}).items():
                        ts["filters"][f] = [v]
                    for f, v in pf.items():
                        if f in {x["field"] for x in self.meta["pages"][new_pid]["filters"]}:
                            ts["filters"][f] = v
                    ts["date_range"] = plan.range
                    ts["compare"] = "custom"
                    ts["compare_range"] = plan.cmp_range
                    plan.target_state, _ = self.validator.repair_state(ts)
                else:
                    plan.target_state["compare"] = "custom"
                    plan.target_state["compare_range"] = plan.cmp_range
                plan.actions = self.planner.diff_actions(st.get("current_state"), plan.target_state)
        # data-reading / analysis actions for the trace
        page = self.meta["pages"][plan.page_id]
        extra = []
        desc = {"kpi": "Read KPI", "rank": "Rank members", "compare_periods": "Compare periods",
                "compare_entities": "Compare members", "trend": "Analyse trend", "monthly_average": "Compare monthly totals with their mean", "drivers": "Contribution analysis + cross-view cause tests"}
        if a:
            extra.append(dsl.Analyze(kind={"drivers": "drivers"}.get(a, a) if a in ("kpi", "rank", "compare_periods", "compare_entities", "trend", "monthly_average", "drivers") else "kpi",
                                     description=f"{desc.get(a, a)}: {VIEWS[plan.view]['metrics'][metric]['label']} ({len(fb.facts)} figures, {len({f['sql'] for f in fb.facts})} queries)"))
        hl = self._pick_widget(page, plan, metric)
        if hl:
            extra.append(dsl.Highlight(widget_id=hl))
        plan.actions = list(plan.actions) + extra
        self._t(st, "execute", t0, analysis=a, facts=len(fb.facts), queries=len({f["sql"] for f in fb.facts}))
        return {"result": res, "facts": fb, "plan": plan, "trace": st["trace"]}

    def _pick_widget(self, page, plan, metric):
        want = "grid" if plan.analysis == "rank" else "line" if plan.analysis in ("trend", "monthly_average") else "bar" if plan.analysis in ("drivers", "compare_entities", "compare_periods") else "kpi"
        if plan.analysis == "rank" and plan.group_by:
            matching = next((w for w in page["widgets"] if w["type"] == "grid" and w.get("dimensions", [])[:1] == plan.group_by[:1] and metric in w.get("metrics", [])), None)
            if matching: return matching["id"]
        for w in page["widgets"]:
            if w["type"] == want and (w.get("metric") == metric or metric in w.get("metrics", [])):
                return w["id"]
        for w in page["widgets"]:
            if w.get("metric") == metric or metric in w.get("metrics", []):
                return w["id"]
        return None

    def n_respond(self, st: GState):
        t0 = time.time()
        plan: Plan = st["plan"]
        sess: Session = st["session"]
        res = st.get("result") or {}
        fb = st.get("facts")
        R = self.responder
        cards, cites, sugg, needs_conf = [], [], [], None
        text = ""
        if plan.kind == "refuse":
            text = plan.message
            self.metrics["refusals"] += 1
        elif plan.kind == "greet":
            text = (f"Hi! I'm the {C.APP_NAME} copilot for {C.TENANT_NAME}. I can open any of the {len(self.meta['pages'])} pages, "
                    "set filters and dates, answer questions from the data and explain why numbers moved.")
            sugg = self.help_examples()[:4]
        elif plan.kind == "help":
            text = ("I can **navigate** (“open the stockout monitor”), **configure** (“only Mobile App, sort by AOV”), **answer** "
                    "(“top 5 cities by revenue last quarter”), **compare** (“August vs July”, “North vs South”), show **trends** and explain "
                    "**why** a metric moved, with evidence you can click. I can't modify data. I'll ask before saving anything.")
            sugg = self.help_examples()
        elif plan.kind == "clarify":
            text = plan.clarify["question"]
            sugg = plan.clarify["options"]
            self.metrics["clarifications"] += 1
        elif plan.kind == "explain":
            text, cards = self.explain_page(plan.page_id, st.get("current_state"))
        elif plan.kind == "undo":
            if sess.stack:
                prev = sess.stack.pop()
                plan.target_state = prev
                plan.actions = self.planner.diff_actions(st.get("current_state"), prev)
                text = f"Back to {R.crumb(prev['page_id'])} ({prev['date_range'].get('label', '')})."
                return self._finish(st, text, [], [], [], None, undo=True)
            text = "There's nothing to undo yet."
        elif plan.kind == "confirm":
            cid = uuid.uuid4().hex[:8]
            name = f"{self.meta['pages'][plan.page_id]['title']} · {plan.target_state['date_range'].get('label', '')}"
            sess.pending[cid] = {"type": "save_view", "name": name, "state": plan.target_state}
            needs_conf = {"id": cid, "title": "Save this view?",
                          "detail": f"This will save “{name}” with its filters to your saved views (a persistent change).",
                          "action": dsl.SaveView(name=name).model_dump()}
            text = "Please confirm: should I save the current view?"
            plan.actions = []
        elif plan.kind == "export":
            grid = next((w for w in self.meta["pages"][plan.page_id]["widgets"] if w["type"] == "grid"), None)
            if grid:
                plan.actions = [dsl.Export(widget_id=grid["id"])]
                text = f"Exporting “{grid['title']}” as CSV with the current filters."
            else:
                text = "This page doesn't have a data grid to export."
        elif plan.kind in ("act", "reset"):
            a = plan.analysis
            if plan.kind == "reset":
                text = f"Reset {self.meta['pages'][plan.page_id]['title']} to its default view."
            elif a == "kpi":
                text, cards = R.kpi(plan, res)
            elif a == "rank":
                text, cards = R.rank(plan, res)
            elif a == "compare_periods":
                text, cards = R.compare_periods(plan, res)
            elif a == "compare_entities":
                text, cards = R.compare_entities(plan, res)
            elif a == "monthly_average":
                text, cards = R.monthly_average(plan, res)
            elif a == "trend":
                text, cards = R.trend(plan, res)
            elif a == "drivers" and plan.view == "retail":
                text, cards = R.compare_periods(plan, res)
            elif a == "drivers" and plan.view.startswith("olist_"):
                text, cards = R.compare_periods(plan,res)
            elif a == "drivers":
                text, cards = R.drivers(plan, res, st["parsed"].normalized)
            if plan.view == "retail" and res.get("retail_contributors"):
                text += "\nNumerical contributors by " + C.DIMENSION_LABELS[(plan.group_by or ["country"])[0]] + " to the change: " + "; ".join(f"{x['member']}: {x['formatted']}" for x in res["retail_contributors"][:5]) + "."
                remainder=sum(x["delta"] for x in res["retail_contributors"][5:])
                if (plan.group_by or ['country'])[0]=='retail_product':
                    rows=res['retail_contributors'][:5]
                    cards.append({'type':'bar','title':'Product contributions to revenue change (GBP)',
                                  'labels':[x['member'] for x in rows]+['All remaining products'],
                                  'series':[{'name':'Revenue change','values':[x['delta'] for x in rows]+[remainder]}],
                                  'fmt':'gbp','horizontal':True})
                text += " All remaining members combined: " + A.fmt_value(remainder,"gbp") + ". These contributions reconcile to the total revenue change."
            if res.get('olist_contributors'):
                text += "\nNumerical sales contributors: " + '; '.join(f"{x['member']}: {x['formatted']}" for x in res['olist_contributors']) + ". These are accounting contributions, not external causes."
            cites = R.citations(plan, res) if plan.kind == "act" else []
            if plan.analysis == "monthly_average" and plan.kind == "act":
                cites.append({"label":"Complete monthly totals and arithmetic mean", "state":copy.deepcopy(plan.target_state), "kind":"evidence"})
            if plan.view == "retail" and plan.kind == "act":
                cites.append({"label":"UCI sales calculation scope", "state":copy.deepcopy(plan.target_state), "kind":"evidence"})
            if plan.view and plan.view.startswith('olist_') and plan.kind=='act':
                cites.append({'label':'Olist calculation scope','state':copy.deepcopy(plan.target_state),'kind':'evidence'})
            # citations must be valid states too
            clean = []
            for c in cites:
                s = self.planner.default_state(c["state"]["page_id"])
                s.update({k: v for k, v in c["state"].items() if v is not None})
                s, _ = self.validator.repair_state(s)
                c["state"] = s
                clean.append(c)
            cites = clean
            sugg = plan.period_options + R.suggestions(plan, res)
        notes = [n for n in plan.notes if n]
        if notes:
            text += "\n" + "\n".join(f"_Note: {n}_" for n in notes)
        return self._finish(st, text, cards, cites, sugg, needs_conf)

    def _finish(self, st, text, cards, cites, sugg, needs_conf, undo=False):
        plan: Plan = st["plan"]
        sess: Session = st["session"]
        fb = st.get("facts")
        facts = fb.facts if fb else []
        if plan.view == "retail" and plan.kind == "act":
            text += "\n_Dataset: UCI Online Retail II / imported historical sales / GBP. External causes are not established by transaction data._"
        if plan.view and plan.view.startswith('olist_') and plan.kind=='act':
            text += "\n_Dataset: Olist Brazilian E-Commerce / real imported data / BRL. Dates group orders by purchase date. Review/delivery relationships are associations, not proven causes._"
        faith = faithfulness(text, facts)
        self.metrics["faithfulness_numbers"] += faith["numbers"]
        self.metrics["faithfulness_traced"] += faith["traced"]
        actions = [a.model_dump() if hasattr(a, "model_dump") else a for a in plan.actions]
        for a, obj in zip(actions, plan.actions):
            a["label"] = dsl.describe_action(obj, self.meta)
        self.metrics["actions"] += sum(1 for a in actions if a["type"] in dsl.STATE_CHANGING)
        # memory: remember slots for follow-ups, and the previous state for undo
        if plan.kind in ("act", "reset") and plan.target_state:
            if st.get("current_state") and st["current_state"].get("page_id"):
                sess.stack.append(copy.deepcopy(st["current_state"]))
                sess.stack = sess.stack[-20:]
            sess.ctx = {"view": plan.view, "metrics": plan.metrics, "filters": {k: v for k, v in plan.filters.items()},
                        "group_by": plan.group_by, "range": plan.range, "cmp_range": plan.cmp_range,
                        "cmp_mode": plan.target_state.get("compare"), "intent": plan.intent if plan.intent in ("why", "compare", "trend", "query") else "show",
                        "page_id": plan.page_id, "average_direction": plan.average_direction}
            if plan.entity_compare:
                sess.ctx["filters"][plan.entity_compare["field"]] = plan.entity_compare["members"]
        res = st.get("result") or {}
        analysis = None
        if res.get("drivers"):
            d = res["drivers"]
            analysis = {"status": d.get("status"), "driver": d.get("driver"),
                        "direction": (d.get("headline") or {}).get("direction"),
                        "causes": [{"view": h["view"], "metric": h["metric"], "confidence": h["confidence"]} for h in (res.get("causes") or [])]}
        if res.get('retail_contributors'):
            rows=res['retail_contributors']
            analysis={'status':'ok','dimension':(plan.group_by or ['country'])[0], 'metric':'revenue',
                      'total_delta':sum(x['delta'] for x in rows), 'remaining_delta':sum(x['delta'] for x in rows[5:]),
                      'contributors':rows[:5], 'member_count':len(rows)}
        resp = {
            "analysis": analysis,
            "reply": text, "cards": cards, "citations": cites, "suggestions": sugg,
            "actions": actions, "target_state": plan.target_state if (plan.kind in ("act", "reset") or undo) else None,
            "needs_confirmation": needs_conf, "kind": plan.kind, "intent": plan.intent,
            "faithfulness": faith, "facts": facts[:200],
            "trace": st.get("trace", []), "notes": plan.notes,
        }
        self._t(st, "respond", time.time(), facts=len(facts), faithfulness=faith["score"])
        resp["trace"] = st["trace"]
        return {"response": resp, "trace": st["trace"]}

    # ---------------- graph ----------------
    def _route_after_plan(self, st):
        return "execute" if st["plan"].kind == "act" else ("validate" if st["plan"].kind == "reset" else "respond")

    def _build_graph(self):
        g = StateGraph(GState)
        g.add_node("understand", self.n_understand)
        g.add_node("plan", self.n_plan)
        g.add_node("validate", self.n_validate)
        g.add_node("execute", self.n_execute)
        g.add_node("respond", self.n_respond)
        g.set_entry_point("understand")
        g.add_edge("understand", "plan")
        g.add_conditional_edges("plan", lambda s: "validate" if s["plan"].kind in ("act", "reset") else "respond",
                                {"validate": "validate", "respond": "respond"})
        g.add_conditional_edges("validate", lambda s: "execute" if s["plan"].kind == "act" else "respond",
                                {"execute": "execute", "respond": "respond"})
        g.add_edge("execute", "respond")
        g.add_edge("respond", END)
        return g.compile()

    def _run_step(self, sess, text, current_state):
        st: GState = {"session": sess, "text": text, "current_state": current_state, "trace": []}
        if self.app is not None:
            out = self.app.invoke(st)
            return out["response"]
        st.update(self.n_understand(st))
        st.update(self.n_plan(st))
        if st["plan"].kind in ("act", "reset"):
            st.update(self.n_validate(st))
        if st["plan"].kind == "act":
            st.update(self.n_execute(st))
        st.update(self.n_respond(st))
        return st["response"]

    # ------------------------------------------------------------------
    def handle(self, session_id, text, current_state=None):
        t0 = time.time()
        sess = self.session(session_id)
        self.metrics["turns"] += 1
        parts = [p for p in STEP_SPLIT.split(text.strip()) if p and len(p.strip()) > 1]
        if len(parts) > 4:
            parts = parts[:4]
        responses = []
        state = current_state
        for p in parts:
            r = self._run_step(sess, p.strip(), state)
            responses.append((p, r))
            self.metrics["steps"] += 1
            if r.get("target_state"):
                state = r["target_state"]
            if r["kind"] in ("clarify", "refuse") or r.get("needs_confirmation"):
                break
        if len(responses) == 1:
            out = responses[0][1]
        else:
            out = {"reply": "\n\n".join(f"**Step {i+1}:** {r['reply']}" for i, (_, r) in enumerate(responses)),
                   "cards": [c for _, r in responses for c in r["cards"]][-4:],
                   "citations": [c for _, r in responses for c in r["citations"]][-4:],
                   "suggestions": responses[-1][1]["suggestions"],
                   "actions": [dict(a, step=i + 1) for i, (_, r) in enumerate(responses) for a in r["actions"]],
                   "target_state": next((r["target_state"] for _, r in reversed(responses) if r.get("target_state")), None),
                   "needs_confirmation": responses[-1][1].get("needs_confirmation"),
                   "kind": "multi_step", "intent": "+".join(r["intent"] for _, r in responses),
                   "faithfulness": {"numbers": sum(r["faithfulness"]["numbers"] for _, r in responses),
                                    "traced": sum(r["faithfulness"]["traced"] for _, r in responses)},
                   "facts": [f for _, r in responses for f in r["facts"]][:300],
                   "trace": [dict(t, step=i + 1) for i, (_, r) in enumerate(responses) for t in r["trace"]],
                   "notes": [n for _, r in responses for n in r["notes"]], "steps": [p for p, _ in responses]}
            fn = out["faithfulness"]
            fn["score"] = 1.0 if fn["numbers"] == 0 else round(fn["traced"] / fn["numbers"], 3)
        out["session_id"] = sess.id
        out["turn_id"] = uuid.uuid4().hex[:10]
        out["latency_ms"] = round((time.time() - t0) * 1000, 1)
        out["engine"] = {"langgraph": self.app is not None, "mode": LLM.mode(), "llm": LLM.configured()}
        self.metrics["latencies"].append(out["latency_ms"])
        self.metrics["latencies"] = self.metrics["latencies"][-500:]
        sess.turns[out["turn_id"]] = out.get("target_state")
        sess.history.append({"user": text, "reply": out["reply"], "kind": out["kind"]})
        return out

    def verify(self, session_id, turn_id, applied):
        """Compare the state the UI reports after executing actions with the intended state."""
        sess = self.session(session_id)
        tgt = sess.turns.get(turn_id)
        if not tgt:
            return {"ok": None, "diff": []}
        diff = []
        for k in ("page_id", "compare"):
            if (tgt.get(k) or None) != (applied.get(k) or None):
                diff.append({"field": k, "expected": tgt.get(k), "actual": applied.get(k)})
        tf = {k: sorted(v) for k, v in (tgt.get("filters") or {}).items() if v}
        af = {k: sorted(v) for k, v in (applied.get("filters") or {}).items() if v}
        if tf != af:
            diff.append({"field": "filters", "expected": tf, "actual": af})
        td, ad = tgt.get("date_range") or {}, applied.get("date_range") or {}
        if (td.get("start"), td.get("end")) != (ad.get("start"), ad.get("end")):
            diff.append({"field": "date_range", "expected": td, "actual": ad})
        if (tgt.get("sort") or None) != (applied.get("sort") or None):
            diff.append({"field": "sort", "expected": tgt.get("sort"), "actual": applied.get("sort")})
        for k in ("top_n", "grain"):
            if tgt.get(k) != applied.get(k):
                diff.append({"field": k, "expected": tgt.get(k), "actual": applied.get(k)})
        if tgt.get("compare") == "custom":
            tr, ar = tgt.get("compare_range") or {}, applied.get("compare_range") or {}
            if (tr.get("start"), tr.get("end")) != (ar.get("start"), ar.get("end")):
                diff.append({"field": "compare_range", "expected": tr, "actual": ar})
        self.metrics["verified"] += 1
        if not diff:
            self.metrics["verified_ok"] += 1
        return {"ok": not diff, "diff": diff}

    def confirm(self, session_id, cid, approve):
        sess = self.session(session_id)
        p = sess.pending.pop(cid, None)
        if not p:
            return {"reply": "That request has expired.", "ok": False}
        if not approve:
            return {"reply": "Cancelled. Nothing was saved.", "ok": False}
        sess.saved_views.append({"name": p["name"], "state": p["state"]})
        return {"reply": f"View “{p['name']}” is ready to bookmark in this browser.", "ok": True, "saved_views": sess.saved_views, "saved_view": sess.saved_views[-1]}

    def explain_page(self, pid, cur):
        if not pid or pid not in self.meta["pages"]:
            return "Open a page first and I'll explain what it shows.", []
        p = self.meta["pages"][pid]
        wt = {}
        for w in p["widgets"]:
            wt.setdefault(w["type"], []).append(w["title"])
        names = {"kpi": "KPI cards", "line": "trend chart", "bar": "bar chart", "donut": "mix chart", "grid": "data grid"}
        parts = [f"{names[k]}: {', '.join(v)}" for k, v in wt.items()]
        filt = ", ".join(f["label"] for f in p["filters"])
        state_txt = ""
        if cur:
            f = cur.get("filters") or {}
            state_txt = f"\nCurrently showing {cur.get('date_range', {}).get('label', '')}" + (f" with {A.filters_text(f)}" if f else " for all data") + "."
        txt = (f"**{p['title']}** ({' › '.join(p['breadcrumb'][:-1])}): {p['description']}\n"
               + "\n".join(f"• {x}" for x in parts) + f"\nYou can filter by {filt}, change the date range and compare periods." + state_txt)
        return txt, []

    def help_examples(self):
        return [
            {"label": "Why did South revenue drop in August?", "utterance": "Why did South revenue drop in August?"},
            {"label": "Top 5 cities by revenue last quarter", "utterance": "Top 5 cities by revenue last quarter"},
            {"label": "Open the stockout monitor for Chennai DC", "utterance": "Open the stockout monitor for Chennai DC"},
            {"label": "Compare North vs South revenue YTD", "utterance": "Compare North vs South revenue this year"},
            {"label": "On-time delivery trend in the West", "utterance": "Show the on-time delivery trend in the West for the last 6 months"},
            {"label": "South ka revenue dikhao pichle mahine", "utterance": "south ka revenue dikhao pichle mahine"},
        ]

    def live_kpis(self):
        L = sorted(self.metrics["latencies"])
        p = lambda q: (L[min(len(L) - 1, int(q * len(L)))] if L else None)
        m = self.metrics
        return {"turns": m["turns"], "steps": m["steps"], "state_changing_actions": m["actions"],
                "clarifications": m["clarifications"], "refusals": m["refusals"],
                "blocked_invalid_actions": m["blocked_actions"],
                "ui_state_verified": m["verified"], "ui_state_verified_ok": m["verified_ok"],
                "ui_state_correctness": None if not m["verified"] else round(m["verified_ok"] / m["verified"], 3),
                "faithfulness": None if not m["faithfulness_numbers"] else round(m["faithfulness_traced"] / m["faithfulness_numbers"], 3),
                "latency_p50_ms": p(0.5), "latency_p95_ms": p(0.95), "llm_used": m["llm_used"],
                "llm_stats": self.llm.stats}
