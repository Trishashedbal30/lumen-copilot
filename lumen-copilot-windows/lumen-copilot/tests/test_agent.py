"""Smoke tests: python -m pytest -q   (or: python tests/test_agent.py)"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.agent.controller import Agent  # noqa: E402

META = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "app_metadata.json"), encoding="utf-8"))
AG = Agent(META)
HOME = AG.planner.default_state("exec.dashboards.summary")


def ask(text, sid="t", state=HOME):
    return AG.handle(sid, text, state)


def test_navigation_and_filters():
    r = ask("show south revenue for august", sid="a")
    assert r["target_state"]["page_id"] == "sales.regional.south"
    assert r["target_state"]["date_range"]["start"] == "2026-08-01"


def test_root_cause_finds_planted_anomaly():
    r = ask("Why did South revenue drop in August?", sid="b")
    assert r["analysis"]["driver"]["member"] == "Electronics"
    assert (r["analysis"]["causes"][0]["view"], r["analysis"]["causes"][0]["metric"]) == ("inventory", "stockout_days")
    assert r["faithfulness"]["score"] == 1.0


def test_guardrails():
    assert ask("delete all revenue data")["kind"] == "refuse"
    assert ask("sales in surat")["kind"] == "clarify"
    assert ask("show mobile sales")["kind"] == "clarify"


def test_followup_and_undo():
    r1 = ask("show south revenue for august", sid="c")
    r2 = ask("what about north?", sid="c", state=r1["target_state"])
    assert r2["target_state"]["page_id"] == "sales.regional.north"
    r3 = ask("undo", sid="c", state=r2["target_state"])
    assert r3["target_state"]["page_id"] == "sales.regional.south"


def test_every_action_is_valid():
    for u in ["top 5 cities by revenue last quarter", "open the stockout monitor for chennai", "compare north and south revenue this year"]:
        r = ask(u)
        assert not AG.validator.check_state(r["target_state"]), u


def test_llm_slots_are_grounded():
    """The LLM path must drop invented metrics/values/pages instead of acting on them."""
    fake = {"intent": "show", "metric": "sales.revenue", "extra_metrics": ["sales.profitability_index"],
            "filters": {"region": ["south"], "city": ["Atlantis"], "planet": ["Mars"]}, "group_by": ["city"],
            "time_expression": "last month", "page_id": "sales.made_up_page"}
    pr = AG.llm.parse("show South revenue", call_fn=lambda s, u: fake)
    assert pr.metrics[0]["metric"] == "revenue" and len(pr.metrics) == 1
    assert pr.filters == {"region": ["South"]}
    assert pr.page_mentions == []
    assert len(pr.llm_blocked) == 4
    assert pr.time.main.start.isoformat() == "2026-08-01"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
