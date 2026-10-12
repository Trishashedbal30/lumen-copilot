"""Run python doctor.py; add --llm to check the configured model, not just configuration."""
import importlib
import json
from pathlib import Path
import platform
import sys
import struct

from run import ROOT, load_env

def main():
    load_env()
    failures = []
    if not (3,11) <= sys.version_info[:2] < (3,14) or struct.calcsize("P") != 8:
        failures.append("Use a 64-bit Python 3.11-3.13 virtual environment; rerun setup.bat with Python 3.12.")
    print("Python:", platform.python_version(), platform.system(), platform.machine())
    for mod in ("fastapi", "uvicorn", "pydantic", "duckdb", "numpy", "pandas", "sklearn", "rapidfuzz", "httpx", "langgraph"):
        try:
            importlib.import_module(mod)
            print("OK", mod)
        except ImportError:
            failures.append(mod)
            print("MISSING", mod)
    for name in ("lumen.duckdb", "app_metadata.json", "ground_truth.json"):
        if not (Path(ROOT)/"data"/name).is_file():
            failures.append(name)
            print("MISSING", name)
    if not failures:
        from backend.semantic import engine
        from backend import catalog as C
        for view in engine.VIEWS:
            print("DATA", view, engine.data_bounds(view))
        from backend.main import AGENT, health
        print(json.dumps(health(), indent=2))
        if AGENT.app is None:
            failures.append("LangGraph not active")
        if "--llm" in sys.argv:
            from backend.agent import llm
            if not llm.configured():
                failures.append("LLM is not configured; copy .env.ollama.example to .env")
            else:
                try:
                    pr = AGENT.llm.parse("Show South revenue for August 2026")
                    if not (pr.metric and pr.metric["metric"] == "revenue" and pr.filters.get("region") == ["South"] and not pr.llm_blocked):
                        raise ValueError(f"Inference returned unsupported or incorrect slots: metrics={pr.metrics}, filters={pr.filters}, blocked={pr.llm_blocked}")
                    print("OK live model returned grounded revenue and South slots")
                except Exception as exc:
                    failures.append("LLM failed: " + str(exc))
    for failure in failures:
        print("FAIL:", failure)
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
