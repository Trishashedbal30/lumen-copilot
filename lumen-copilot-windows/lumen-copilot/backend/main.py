"""
Lumen Copilot API server.

  uvicorn backend.main:app --port 8000      (or: python run.py)

Serves the metadata-driven no-code app (frontend/) and the agent API.
"""
import json
import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import catalog as C
from backend.agent import llm as LLM
from backend.agent.controller import Agent
from backend.render import grid_csv, render_page, resolve_state

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META_PATH = os.path.join(ROOT, "data", "app_metadata.json")
FRONT = os.path.join(ROOT, "frontend")
REPORTS = os.path.join(ROOT, "eval", "reports")

if not os.path.exists(META_PATH):
    raise SystemExit("data/app_metadata.json missing. Run: python -m backend.data.generate_metadata")
with open(META_PATH, encoding="utf-8") as f:
    META = json.load(f)

from backend.datasets import augment_metadata
META = augment_metadata(META)
from backend.olist import augment_metadata as augment_olist
META = augment_olist(META)
AGENT = Agent(META)
app = FastAPI(title="Lumen Copilot", version="1.0")


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    session_id: str | None = Field(default=None, max_length=100)
    state: dict | None = None


class StateIn(BaseModel):
    state: dict


class VerifyIn(BaseModel):
    session_id: str
    turn_id: str
    applied_state: dict


class ConfirmIn(BaseModel):
    session_id: str
    confirmation_id: str
    approve: bool


@app.get("/api/health")
def health():
    return {"ok": True, "pages": len(META["pages"]), "langgraph": AGENT.app is not None, "mode": LLM.mode(),
            "llm_configured": LLM.configured(), "provider": os.environ.get("LUMEN_LLM_PROVIDER") or None,
            "data_end": C.DATA_END.isoformat(), "model_configuration": LLM.configuration(),
            "llm_requests": AGENT.llm.stats}


@app.get("/api/readiness")
def readiness():
    from backend.readiness import build
    return build(META, AGENT)


@app.get("/api/datasets")
def datasets_status():
    return META.get("datasets", {})


@app.get("/api/meta")
def meta():
    return META


def checked_state(state):
    if state.get("page_id") not in META["pages"]:
        raise HTTPException(404, "unknown page")
    try:
        resolved = resolve_state(AGENT.planner, state)
        errors = AGENT.validator.check_state(resolved)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise HTTPException(422, "invalid view state") from exc
    if errors:
        raise HTTPException(422, detail=errors)
    return resolved


@app.post("/api/render")
def render(body: StateIn):
    st = checked_state(body.state)
    t0 = time.time()
    out = render_page(AGENT.planner, st)
    out["ms"] = round((time.time() - t0) * 1000, 1)
    return out


@app.post("/api/resolve")
def resolve(body: StateIn):
    return checked_state(body.state)


@app.post("/api/chat")
def chat(body: ChatIn):
    if not body.message.strip():
        raise HTTPException(400, "empty message")
    state = checked_state(body.state) if body.state is not None else None
    try:
        with AGENT.lock:
            return AGENT.handle(body.session_id, body.message, state)
    except Exception as e:  # keep the demo alive and honest
        import traceback
        traceback.print_exc()
        return {"reply": f"Sorry, I hit an internal error and made no changes ({type(e).__name__}). Try rephrasing?",
                "cards": [], "citations": [], "suggestions": [], "actions": [], "target_state": None,
                "kind": "error", "intent": "error", "trace": [], "faithfulness": {"score": 1.0}, "session_id": body.session_id}


@app.post("/api/verify")
def verify(body: VerifyIn):
    with AGENT.lock:
        return AGENT.verify(body.session_id, body.turn_id, checked_state(body.applied_state))


@app.post("/api/confirm")
def confirm(body: ConfirmIn):
    with AGENT.lock:
        return AGENT.confirm(body.session_id, body.confirmation_id, body.approve)


@app.post("/api/export")
def export(body: StateIn):
    csv = grid_csv(AGENT.planner, checked_state(body.state))
    name = body.state.get("page_id", "export").replace(".", "_") + ".csv"
    return Response(csv, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/search")
def search(q: str, mode: str = "hybrid", k: int = 10):
    pr = AGENT.parser.parse(q)
    hits = AGENT.index.search(q[:500], k=max(1, min(k, 50)), mode=mode)
    return {"query": q, "parsed": {"intent": pr.intent, "metrics": pr.metrics, "filters": pr.filters, "group_by": pr.group_by},
            "results": [{"page_id": pid, "title": META["pages"][pid]["title"], "score": round(s, 3), "components": c} for pid, s, c in hits]}


@app.get("/api/graph")
def graph(widgets: bool = False):
    return AGENT.graph.export(max_widgets=widgets)


@app.get("/api/kpis/live")
def live():
    return AGENT.live_kpis()


@app.get("/api/eval/latest")
def eval_latest():
    p = os.path.join(REPORTS, "latest.json")
    if not os.path.exists(p):
        return JSONResponse({"error": "No eval report yet. Run: python -m eval.run_eval"}, status_code=404)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/ground_truth")
def ground_truth():
    with open(os.path.join(ROOT, "data", "ground_truth.json"), encoding="utf-8") as f:
        return json.load(f)


@app.get("/")
def index():
    return FileResponse(os.path.join(FRONT, "index.html"))


@app.get("/eval")
def eval_page():
    return FileResponse(os.path.join(FRONT, "eval.html"))


@app.get("/readiness")
def readiness_page():
    return FileResponse(os.path.join(FRONT, "readiness.html"))


@app.get("/graph")
def graph_page():
    return FileResponse(os.path.join(FRONT, "graph.html"))


app.mount("/static", StaticFiles(directory=FRONT), name="static")
