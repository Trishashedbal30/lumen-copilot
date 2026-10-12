import copy
import json
import os
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.main import app, AGENT
from backend.agent.controller import Agent
from backend.agent.dsl import UIState

CLIENT = TestClient(app)
HOME = AGENT.planner.default_state("exec.dashboards.summary")

def test_render_resolve_export_reject_unknown_page():
    for route in ("render", "resolve", "export"):
        assert CLIENT.post("/api/" + route, json={"state": {"page_id": "not.real"}}).status_code == 404

def test_bad_states_rejected_without_queries():
    for field, value in (("top_n", "bad"), ("top_n", 999), ("filters", {"city": "Atlantis"}),
                         ("sort", {"field": "made_up", "dir": "desc"}),
                         ("date_range", {"start": "2026-08-31", "end": "2026-08-01"}),
                         ("compare_range", {"start": "invalid", "end": "invalid"})):
        state = copy.deepcopy(HOME); state[field] = value
        if field == "compare_range": state["compare"] = "custom"
        assert CLIENT.post("/api/render", json={"state": state}).status_code == 422
        assert CLIENT.post("/api/chat", json={"message": "show revenue", "state": state}).status_code == 422

def test_chat_normal_and_input_limit():
    assert CLIENT.post("/api/chat", json={"message": "a" * 501}).status_code == 422
    assert CLIENT.post("/api/chat", json={"message": " "}).status_code == 400
    response = CLIENT.post("/api/chat", json={"message": "show south revenue for august", "state": HOME}).json()
    assert response["kind"] == "act"
    assert response["engine"]["langgraph"] is True
    assert response["target_state"]["filters"]["region"] == ["South"]

def test_verify_checks_all_controls():
    agent = Agent(AGENT.meta)
    response = agent.handle("verifytest", "top 5 cities by revenue last quarter", HOME)
    target = response["target_state"]
    assert agent.verify("verifytest", response["turn_id"], target)["ok"]
    for field, value in (("top_n", 99), ("grain", "quarter"), ("sort", None)):
        altered = copy.deepcopy(target); altered[field] = value
        result = agent.verify("verifytest", response["turn_id"], altered)
        assert not result["ok"] and any(d["field"] == field for d in result["diff"])
    target = copy.deepcopy(target); target.update(compare="custom", compare_range={"start": "2026-07-01", "end": "2026-07-31"})
    agent.sessions["verifytest"].turns[response["turn_id"]] = target
    altered = copy.deepcopy(target); altered["compare_range"]["end"] = "2026-07-30"
    assert not agent.verify("verifytest", response["turn_id"], altered)["ok"]

def test_llm_cannot_override_destructive_request_or_ambiguity():
    agent = Agent(AGENT.meta)
    with patch.dict(os.environ, {"LUMEN_AGENT_MODE": "llm", "LUMEN_LLM_PROVIDER": "ollama"}):
        with patch.object(agent.llm, "parse", side_effect=AssertionError("must not call the model")):
            assert agent.handle(None, "delete all revenue data", HOME)["kind"] == "refuse"
            assert agent.handle(None, "show mobile sales", HOME)["kind"] == "clarify"

def test_llm_error_falls_back_and_records_error():
    agent = Agent(AGENT.meta)
    with patch.dict(os.environ, {"LUMEN_AGENT_MODE": "llm", "LUMEN_LLM_PROVIDER": "ollama"}):
        with patch.object(agent.llm, "parse", side_effect=RuntimeError("model offline")):
            response = agent.handle(None, "show south revenue for august", HOME)
    assert response["kind"] == "act"
    assert any(t["node"] == "llm_error" for t in response["trace"])

def test_llm_clarification_and_blocked_slots_do_not_execute():
    agent = Agent(AGENT.meta)
    for js in ({"intent": "show", "metric": "sales.revenue", "clarification_needed": "Which region?"},
               {"intent": "show", "metric": "sales.revenue", "filters": {"city": ["Atlantis"]}}):
        pr = agent.llm.parse("show revenue", call_fn=lambda s, u: js)
        plan = agent.planner.plan(pr, {}, HOME)
        assert plan.kind == "clarify" and not plan.actions

def test_validation_is_execution_barrier():
    agent = Agent(AGENT.meta)
    state = {"session": agent.session("barrier"), "text": "show revenue", "current_state": HOME, "trace": []}
    state.update(agent.n_understand(state)); state.update(agent.n_plan(state))
    state["plan"].target_state["date_range"] = {"start": "invalid", "end": "invalid"}
    state.update(agent.n_validate(state))
    assert state["plan"].kind == "refuse"
    assert state["plan"].target_state is None and state["plan"].actions == []

def test_utf8_bom_env_loading(tmp_path):
    import run
    (tmp_path / ".env").write_text('PORT=8999\nLUMEN_AGENT_MODE="rules"\n', encoding="utf-8-sig")
    with patch.object(run, "ROOT", str(tmp_path)), patch.dict(os.environ, {}, clear=True):
        run.load_env()
        assert os.environ["PORT"] == "8999" and os.environ["LUMEN_AGENT_MODE"] == "rules"


def test_all_metadata_pages_render_without_widget_errors():
    from backend.render import render_page
    for page_id in AGENT.meta["pages"]:
        result = render_page(AGENT.planner, AGENT.planner.default_state(page_id))
        assert result["widgets"], page_id
        assert not [w for w in result["widgets"] if w.get("error")], page_id


def test_local_model_bypasses_environment_proxy():
    from backend.agent.llm import _post
    with patch("httpx.Client") as client:
        client.return_value.__enter__.return_value.post.return_value.json.return_value = {"ok": True}
        assert _post("http://localhost:11434/v1/chat/completions", {}, {}) == {"ok": True}
        assert client.call_args.kwargs["trust_env"] is False


def test_save_view_preserves_manually_applied_controls_without_context():
    agent=Agent(AGENT.meta)
    manual=copy.deepcopy(HOME)
    manual["filters"]={"region":["South"]}
    manual["date_range"]={"start":"2026-08-01","end":"2026-08-31","label":"August"}
    manual["top_n"]=5
    r=agent.handle(None,"save this view",manual)
    assert r["kind"]=="confirm"
    confirmation=agent.confirm(r["session_id"],r["needs_confirmation"]["id"],True)
    assert confirmation["saved_view"]["state"]==manual


def test_ollama_schema_grounding_prevents_unrequested_filters_and_placeholder_metrics():
    from backend.agent.llm import slot_schema
    schema=slot_schema(text="Top 5 cities by revenue last quarter")
    assert schema["properties"]["filters"]["additionalProperties"] is False
    assert "year" not in schema["properties"]["filters"]["properties"]
    assert schema["properties"]["filters"]["properties"]["region"]["maxItems"]==0
    assert "view.metric" not in schema["properties"]["metric"]["enum"]
    grounded=slot_schema(text="Show South revenue")
    assert grounded["properties"]["filters"]["properties"]["region"]["items"]["enum"]==["South"]
