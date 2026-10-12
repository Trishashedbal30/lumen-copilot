"""
Guardrail layer: every action and the final UI state are checked against the app metadata
before execution. An action that references something that does not exist is an action
hallucination. It is blocked, repaired where that is safe, and counted (exposed as a KPI).
"""
from datetime import date

from backend import catalog as C
from backend.datasets import bounds
from backend.agent import dsl
from backend.semantic.layer import VIEWS


class Validator:
    def __init__(self, metadata):
        self.meta = metadata
        self.pages = metadata["pages"]

    def check_state(self, st):
        """Return list of violations for a target UI state."""
        v = []
        try:
            dsl.UIState.model_validate(st)
        except Exception as exc:
            return [{"code": "invalid_state_shape", "detail": str(exc)[:400]}]
        pid = st.get("page_id")
        if pid not in self.pages:
            return [{"code": "unknown_page", "detail": pid}]
        page = self.pages[pid]
        fields = {f["field"]: set(f["options"]) for f in page["filters"]}
        for f, vals in (st.get("filters") or {}).items():
            if f not in fields:
                v.append({"code": "unknown_filter_field", "detail": f})
                continue
            bad = [x for x in vals if x not in fields[f]]
            if bad:
                v.append({"code": "invalid_filter_value", "detail": f"{f}={bad}"})
            if not vals:
                v.append({"code": "empty_filter", "detail": f})
        dr = st.get("date_range") or {}
        try:
            s, e = date.fromisoformat(dr["start"]), date.fromisoformat(dr["end"])
            if s > e:
                v.append({"code": "inverted_date_range", "detail": f"{s}>{e}"})
            lo, hi = bounds(page["view"])
            if e < lo or s > hi or ((page["view"] == "retail" or page["view"].startswith("olist_")) and (s < lo or e > hi)):
                v.append({"code": "date_out_of_range", "detail": f"{s}..{e}"})
        except Exception:
            v.append({"code": "bad_date_range", "detail": str(dr)})
        if st.get("compare") not in ("none", "previous_period", "previous_year", "custom"):
            v.append({"code": "bad_compare", "detail": st.get("compare")})
        if st.get("compare") == "custom":
            try:
                cr = st.get("compare_range") or {}
                cs, ce = date.fromisoformat(cr["start"]), date.fromisoformat(cr["end"])
                if (page["view"] == "retail" or page["view"].startswith("olist_")) and (cs < bounds(page["view"])[0] or ce > bounds(page["view"])[1]):
                    raise ValueError("comparison outside imported coverage")
                if cs > ce:
                    raise ValueError("comparison start is after end")
            except Exception:
                v.append({"code": "bad_compare_range", "detail": str(st.get("compare_range"))})
        srt = st.get("sort")
        if srt:
            opts = {o["field"] for o in page["sort_options"]}
            if srt.get("field") not in opts:
                v.append({"code": "invalid_sort_field", "detail": srt.get("field")})
            if srt.get("dir") not in ("asc", "desc"):
                v.append({"code": "invalid_sort_dir", "detail": srt.get("dir")})
        tn = st.get("top_n")
        if tn is not None and (isinstance(tn, bool) or not isinstance(tn, int) or not 1 <= tn <= 100):
            v.append({"code": "invalid_top_n", "detail": tn})
        if st.get("grain") not in (None, "auto", "day", "week", "month", "quarter"):
            v.append({"code": "invalid_grain", "detail": st.get("grain")})
        return v

    def check_actions(self, actions, state):
        v = []
        for a in actions:
            if isinstance(a, dsl.Navigate) and a.page_id not in self.pages:
                v.append({"code": "unknown_page", "detail": a.page_id, "action": a.type})
            if isinstance(a, dsl.SetFilter):
                page = self.pages.get(state["page_id"], {})
                fmap = {f["field"]: f["options"] for f in page.get("filters", [])}
                if a.field not in fmap:
                    v.append({"code": "unknown_filter_field", "detail": a.field, "action": a.type})
                elif any(x not in fmap[a.field] for x in a.values):
                    v.append({"code": "invalid_filter_value", "detail": a.values, "action": a.type})
        return v

    def repair_state(self, st):
        """Drop anything invalid (never invent): returns (state, notes)."""
        notes = []
        page = self.pages[st["page_id"]]
        fields = {f["field"]: f["options"] for f in page["filters"]}
        clean = {}
        for f, vals in (st.get("filters") or {}).items():
            if f not in fields:
                notes.append(f"Removed filter “{f}”: not available on {page['title']}.")
                continue
            ok = [x for x in vals if x in fields[f]]
            if len(ok) != len(vals):
                notes.append(f"Removed invalid value(s) for {f}: {[x for x in vals if x not in fields[f]]}.")
            if ok:
                clean[f] = ok
        st["filters"] = clean
        srt = st.get("sort")
        if srt and srt.get("field") not in {o["field"] for o in page["sort_options"]}:
            st["sort"] = page["default_state"].get("sort")
            notes.append("Reset sort to the page default (requested field isn't sortable here).")
        if st.get("top_n") is not None:
            st["top_n"] = max(1, min(100, int(st["top_n"])))
        return st, notes
