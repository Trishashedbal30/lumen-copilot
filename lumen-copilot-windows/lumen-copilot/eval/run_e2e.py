"""
End-to-end browser evaluation with Playwright: the agent's actions are executed by the real UI
(clicking through the app runtime), then the state actually on screen is compared with the labels.
This measures UI-state correctness as the user sees it, not just what the planner intended.

Needs the server running (python run.py) and: pip install playwright && playwright install chromium
Run: python -m eval.run_e2e [--limit 60] [--url http://localhost:8000]
"""
import argparse
import json
import os
import time

from eval.run_eval import check, load, rate
from eval.provenance import source_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    meta = json.load(open(os.path.join(ROOT, "data", "app_metadata.json"), encoding="utf-8"))
    cases = [c for c in load("dev") + load("blind") if c["expected"].get("pages")][: a.limit]
    dialogues = load("dialogues")
    rows, times = [], []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=not a.headed, channel="chromium")
        pg = None

        def fresh():
            # a new browser context per case: no session or conversation carries over
            nonlocal pg
            if pg is not None:
                pg.context.close()
            pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
            pg.goto(a.url + "/")
            pg.wait_for_function("window.Lumen && document.querySelector('#board .widget')", timeout=20000)

        def ask(text):
            n0 = pg.evaluate("window.__lumenTurns || 0")
            t0 = time.time()
            pg.fill("#input", text)
            pg.press("#input", "Enter")
            pg.wait_for_function(f"(window.__lumenTurns || 0) > {n0}", timeout=30000)
            times.append((time.time() - t0) * 1000)
            last = pg.evaluate("window.__lumenLast")
            applied = pg.evaluate("Lumen.getState()")
            return last, applied

        for c in cases:
            fresh()
            last, applied = ask(c["utterance"])
            resp = {"kind": last["kind"], "intent": last["intent"], "target_state": applied if last.get("target_state") else None}
            r = check(c, resp, meta)
            r.update({"id": c["id"], "utterance": c["utterance"], "verified": last.get("verify", "")})
            rows.append(r)
        dl_ok = []
        for d in dialogues:
            fresh()
            oks = []
            for t in d["turns"]:
                last, applied = ask(t["utterance"])
                resp = {"kind": last["kind"], "intent": last["intent"], "target_state": applied if last.get("target_state") else None}
                r = check(t, resp, meta)
                oks.append(all(r.get(k) is not False for k in ("kind_ok", "intent_ok", "dest_ok", "state_ok")))
            dl_ok.append(all(oks))
        b.close()
    ts = sorted(times)
    out = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "source_hash": source_hash(), "n": len(rows),
           "destination_accuracy": rate(rows, "dest_ok"), "ui_state_correctness": rate(rows, "state_ok"),
           "dialogue_task_success": round(sum(dl_ok) / len(dl_ok), 4) if dl_ok else None,
           "verified_on_screen": sum(1 for r in rows if r["verified"].startswith("Checked")),
           "e2e_latency_p50_ms": round(ts[len(ts) // 2]) if ts else None,
           "e2e_latency_p95_ms": round(ts[int(len(ts) * .95) - 1]) if ts else None,
           "failures": [r for r in rows if r.get("dest_ok") is False or r.get("state_ok") is False]}
    os.makedirs(os.path.join(ROOT, "eval", "reports"), exist_ok=True)
    with open(os.path.join(ROOT, "eval", "reports", "e2e.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "failures"}, indent=1))
    print("failures:", [(r["id"], r["utterance"]) for r in out["failures"]])


if __name__ == "__main__":
    main()
