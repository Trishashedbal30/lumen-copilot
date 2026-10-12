"""
Evaluation harness: measures every KPI in the problem statement on labelled data.

  intent-to-destination accuracy      % routed to an acceptable page (strict = preferred page)
  UI-state correctness                filters / date range / comparison / sort / top-N exactly as labelled
  task success (multi-turn)           every turn of a dialogue lands correctly
  analytical quality                  planted-anomaly questions: direction, driver, cause (ground truth)
  explanation faithfulness            % of figures in replies traceable to an executed query
  retrieval quality                   MRR / Recall@k over 209 pages, with ablations
  reliability & safety                action hallucination after guardrails vs an unguarded baseline,
                                      refusals, clarifications, error rate, latency p50/p95, steps
Run:  python -m eval.run_eval            (writes eval/reports/latest.json, served at /eval)
      python -m eval.run_eval --splits blind
"""
import argparse
import json
import os
import statistics
import time
import uuid

from backend.agent.controller import Agent
from backend.agent.validator import Validator
from backend.agent import dsl, llm
from eval.provenance import source_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "eval", "corpus")
REPORTS = os.path.join(ROOT, "eval", "reports")

COARSE = {"show": "lookup", "query": "lookup", "navigate": "lookup", "configure": "lookup", "reset": "lookup",
          "compare": "compare", "trend": "trend", "why": "why", "help": "help", "greeting": "greeting"}


def coarse(resp):
    k = resp.get("kind")
    if k == "refuse":
        return "refuse"
    if k == "clarify":
        return "clarify"
    if k == "greet":
        return "greeting"
    if k == "help":
        return "help"
    return COARSE.get(resp.get("intent"), resp.get("intent"))


def load(name):
    p = os.path.join(CORPUS, f"{name}.jsonl")
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def check(case, resp, meta):
    e = case["expected"]
    out = {"kind_ok": None, "intent_ok": None, "dest_ok": None, "dest_strict": None, "filters_ok": None, "date_ok": None,
           "compare_ok": None, "sort_ok": None, "topn_ok": None, "state_ok": None}
    exp_kind = e.get("kind", "act")
    out["kind_ok"] = (resp.get("kind") in (exp_kind, "multi_step")) or (exp_kind == "refuse" and resp.get("kind") == "refuse")
    intents = e["intent"] if isinstance(e["intent"], list) else [e["intent"]]
    out["intent_ok"] = coarse(resp) in intents
    ts = resp.get("target_state")
    if e.get("pages") and exp_kind == "act":
        pid = ts.get("page_id") if ts else None
        out["dest_ok"] = pid in e["pages"]
        out["dest_strict"] = pid == e["pages"][0]
        if ts:
            presets = meta["pages"].get(pid, {}).get("presets", {})
            af = {k: sorted(v) for k, v in (ts.get("filters") or {}).items() if v}
            ok = all(sorted(v) == af.get(k) for k, v in e.get("filters", {}).items())
            for k, v in af.items():
                if k not in e.get("filters", {}) and presets.get(k) != (v[0] if len(v) == 1 else None):
                    ok = False
            out["filters_ok"] = ok
            if e.get("date_range"):
                dr = ts.get("date_range") or {}
                out["date_ok"] = (dr.get("start"), dr.get("end")) == (e["date_range"]["start"], e["date_range"]["end"])
            if e.get("compare"):
                out["compare_ok"] = ts.get("compare") == e["compare"]
            if e.get("sort"):
                out["sort_ok"] = (ts.get("sort") or {}) == e["sort"]
            if e.get("top_n"):
                out["topn_ok"] = ts.get("top_n") == e["top_n"]
        else:
            out["filters_ok"] = False
        parts = [out[k] for k in ("filters_ok", "date_ok", "compare_ok", "sort_ok", "topn_ok") if out[k] is not None]
        out["state_ok"] = all(parts) if parts else True
    return out


def rate(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return (round(sum(1 for v in vals if v) / len(vals), 4), len(vals)) if vals else (None, 0)


def first_rank(ranked_ids, accept):
    for i, pid in enumerate(ranked_ids, 1):
        if pid in accept:
            return i
    return None


def retrieval_metrics(ranks, n):
    rr = [1.0 / r if r else 0.0 for r in ranks]
    return {"mrr": round(sum(rr) / n, 4) if n else None,
            "recall@1": round(sum(1 for r in ranks if r and r <= 1) / n, 4) if n else None,
            "recall@5": round(sum(1 for r in ranks if r and r <= 5) / n, 4) if n else None,
            "recall@10": round(sum(1 for r in ranks if r and r <= 10) / n, 4) if n else None, "n": n}


def relevance_metrics(ranked_ids, acceptable, ks=(1, 5, 10)):
    """Set-based precision/recall; existing first-hit recall@k is a hit rate."""
    relevant = set(acceptable)
    out = {}
    for k in ks:
        selected = set(ranked_ids[:k])
        hits = len(selected & relevant)
        out[f"precision@{k}"] = hits / min(k, len(ranked_ids)) if ranked_ids else 0.0
        out[f"relevant_page_recall@{k}"] = hits / len(relevant) if relevant else 0.0
        out[f"hit_rate@{k}"] = float(hits > 0)
    return out


def naive_violation(agent, case):
    """Unguarded baseline: top-1 text retrieval + raw parsed slots, no structure, no validator."""
    pr = agent.parser.parse(case["utterance"])
    hits = agent.index.search(case["utterance"], k=1)
    if not hits:
        return True
    pid = hits[0][0]
    st = agent.planner.default_state(pid)
    for f, v in pr.filters.items():
        st["filters"][f] = v
    if pr.sort and pr.sort.get("field"):
        st["sort"] = {"field": pr.sort["field"], "dir": pr.sort["dir"]}
    return bool(agent.validator.check_state(st))


def run(splits, with_retrieval=True):
    meta = json.load(open(os.path.join(ROOT, "data", "app_metadata.json"), encoding="utf-8"))
    agent = Agent(meta)
    home = agent.planner.default_state("exec.dashboards.summary")  # the UI always has a page open
    report = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "pages": len(meta["pages"]),
              "engine": {"langgraph": agent.app is not None}, "splits": {}, "failures": []}
    all_rows, lat, steps, faith_n, faith_t, final_viol, naive_viol, act_cases, errors = [], [], [], 0, 0, 0, 0, 0, 0
    retr = {"bm25": [], "tfidf": [], "hybrid": [], "hybrid+structure (agent)": [], "structure only": []}
    relevance = {name: [] for name in retr}
    for split in splits:
        cases = load(split)
        rows = []
        for case in cases:
            t0 = time.time()
            try:
                resp = agent.handle(uuid.uuid4().hex, case["utterance"], home)
            except Exception as ex:  # an exception is a failure, never a crash of the harness
                errors += 1
                resp = {"kind": "error", "intent": "error", "target_state": None, "actions": [], "faithfulness": {"numbers": 0, "traced": 0}}
            lat.append((time.time() - t0) * 1000)
            r = check(case, resp, meta)
            r.update({"id": case["id"], "split": split, "utterance": case["utterance"]})
            rows.append(r)
            steps.append(sum(1 for a in resp.get("actions", []) if a.get("type") in dsl.STATE_CHANGING))
            faith_n += resp.get("faithfulness", {}).get("numbers", 0)
            faith_t += resp.get("faithfulness", {}).get("traced", 0)
            if resp.get("target_state"):
                act_cases += 1
                if agent.validator.check_state(resp["target_state"]):
                    final_viol += 1
                if naive_violation(agent, case):
                    naive_viol += 1
            bad = [k for k in ("kind_ok", "intent_ok", "dest_ok", "state_ok") if r.get(k) is False]
            if bad:
                ts = resp.get("target_state") or {}
                report["failures"].append({"split": split, "id": case["id"], "utterance": case["utterance"], "failed": bad,
                                           "expected": case["expected"], "got": {"kind": resp.get("kind"), "intent": resp.get("intent"),
                                           "page": ts.get("page_id"), "filters": ts.get("filters"), "date_range": ts.get("date_range"),
                                           "compare": ts.get("compare"), "sort": ts.get("sort"), "top_n": ts.get("top_n")}})
            # retrieval quality (cases with a destination label)
            if with_retrieval and case["expected"].get("pages") and case["expected"].get("kind", "act") == "act":
                acc = case["expected"]["pages"]
                for mode in ("bm25", "tfidf", "hybrid"):
                    ids = [pid for pid, _, _ in agent.index.search(case["utterance"], k=len(meta["pages"]), mode=mode)]
                    retr[mode].append(first_rank(ids, acc))
                    relevance[mode].append(relevance_metrics(ids, acc))
                pr = agent.parser.parse(case["utterance"])
                plan = agent.planner.plan(pr, {}, None)
                if plan.view:
                    for name, abl in (("hybrid+structure (agent)", None), ("structure only", {"retrieval", "mentions"})):
                        ids = [pid for pid, _ in agent.planner.rank_pages(plan.view, plan.metrics[0], plan.filters, plan.group_by, pr.masked, pr, abl)]
                        retr[name].append(first_rank(ids, acc))
                        relevance[name].append(relevance_metrics(ids, acc))
                else:
                    retr["hybrid+structure (agent)"].append(None)
                    retr["structure only"].append(None)
                    for name in ("hybrid+structure (agent)", "structure only"):
                        relevance[name].append(relevance_metrics([], acc))
        summary = {k: rate(rows, k) for k in ("kind_ok", "intent_ok", "dest_ok", "dest_strict", "state_ok", "filters_ok", "date_ok", "compare_ok", "sort_ok", "topn_ok")}
        summary["n"] = len(rows)
        report["splits"][split] = summary
        all_rows += rows

    # ---- analytical quality on planted anomalies ----
    gt = json.load(open(os.path.join(ROOT, "data", "ground_truth.json"), encoding="utf-8"))
    anal = []
    for a in gt:
        for q in a["question_examples"]:
            resp = agent.handle(uuid.uuid4().hex, q, home)
            an = resp.get("analysis") or {}
            drv = (an.get("driver") or {}).get("member")
            causes = [(c["view"], c["metric"]) for c in an.get("causes", [])]
            exp_c = a.get("expected_cause")
            row = {"id": a["id"], "question": q, "intent_ok": resp.get("intent") == "why",
                   "direction_ok": an.get("direction") == a["expected_direction"],
                   "driver_ok": drv in a["expected_driver"]["accept"], "driver": drv,
                   "cause_top1": None if not exp_c else (bool(causes) and causes[0] == (exp_c["view"], exp_c["metric"])),
                   "cause_top3": None if not exp_c else ((exp_c["view"], exp_c["metric"]) in causes),
                   "faithfulness": resp.get("faithfulness", {}).get("score"), "causes": causes}
            anal.append(row)
    report["analytical"] = {
        "n": len(anal),
        "direction_accuracy": rate(anal, "direction_ok"), "driver_accuracy": rate(anal, "driver_ok"),
        "cause_top1": rate(anal, "cause_top1"), "cause_top3": rate(anal, "cause_top3"),
        "faithfulness_mean": round(statistics.mean(r["faithfulness"] or 0 for r in anal), 4) if anal else None,
        "rows": anal,
    }

    # ---- multi-turn dialogues ----
    dl_rows = []
    for d in load("dialogues"):
        sid = uuid.uuid4().hex
        state = home
        turn_ok = []
        for i, t in enumerate(d["turns"]):
            resp = agent.handle(sid, t["utterance"], state)
            if resp.get("target_state"):
                state = resp["target_state"]
            r = check(t, resp, meta)
            ok = all(r.get(k) is not False for k in ("kind_ok", "intent_ok", "dest_ok", "state_ok"))
            turn_ok.append(ok)
            if not ok:
                ts = resp.get("target_state") or {}
                report["failures"].append({"split": "dialogue", "id": f"{d['id']}.{i+1}", "utterance": t["utterance"], "failed": [k for k in ("kind_ok", "intent_ok", "dest_ok", "state_ok") if r.get(k) is False],
                                           "expected": t["expected"], "got": {"kind": resp.get("kind"), "intent": resp.get("intent"), "page": ts.get("page_id"),
                                           "filters": ts.get("filters"), "date_range": ts.get("date_range"), "compare": ts.get("compare"), "sort": ts.get("sort")}})
        dl_rows.append({"id": d["id"], "turns": len(turn_ok), "turns_ok": sum(turn_ok), "success": all(turn_ok)})
    report["dialogues"] = {"n": len(dl_rows), "task_success": round(sum(r["success"] for r in dl_rows) / len(dl_rows), 4) if dl_rows else None,
                           "turn_accuracy": round(sum(r["turns_ok"] for r in dl_rows) / sum(r["turns"] for r in dl_rows), 4) if dl_rows else None,
                           "rows": dl_rows}

    # ---- overall ----
    lat_sorted = sorted(lat)
    report["overall"] = {
        "requests": len(all_rows),
        "intent_accuracy": rate(all_rows, "intent_ok"),
        "destination_accuracy": rate(all_rows, "dest_ok"),
        "destination_accuracy_strict": rate(all_rows, "dest_strict"),
        "ui_state_correctness": rate(all_rows, "state_ok"),
        "filter_correctness": rate(all_rows, "filters_ok"), "date_correctness": rate(all_rows, "date_ok"),
        "compare_correctness": rate(all_rows, "compare_ok"), "sort_correctness": rate(all_rows, "sort_ok"),
        "topn_correctness": rate(all_rows, "topn_ok"),
        "faithfulness": round(faith_t / faith_n, 4) if faith_n else None, "faithfulness_numbers": faith_n,
        "action_hallucination_rate": round(final_viol / act_cases, 4) if act_cases else None,
        "unguarded_baseline_hallucination_rate": round(naive_viol / act_cases, 4) if act_cases else None,
        "error_rate": round(errors / max(1, len(all_rows)), 4),
        "latency_p50_ms": round(lat_sorted[len(lat_sorted) // 2], 1) if lat else None,
        "latency_p95_ms": round(lat_sorted[int(len(lat_sorted) * 0.95) - 1], 1) if lat else None,
        "avg_state_actions_per_request": round(statistics.mean(steps), 2) if steps else None,
    }
    report["retrieval"] = {k: retrieval_metrics(v, len(v)) for k, v in retr.items() if v}
    for name, samples in relevance.items():
        if samples:
            report["retrieval"][name].update({key: round(sum(sample[key] for sample in samples) / len(samples), 4) for key in samples[0]})
    report["retrieval_metric_definitions"] = {"recall@k": "Historical first-relevant-page hit rate, retained for compatibility.", "hit_rate@k": "Fraction of requests with any acceptable page in top k.", "precision@k": "Macro average of acceptable pages retrieved divided by number of retrieved top-k pages.", "relevant_page_recall@k": "Macro average of acceptable pages retrieved divided by all labelled acceptable pages."}

    frozen = os.path.join(REPORTS, "blind_first_run.json")
    if os.path.exists(frozen):
        fr = json.load(open(frozen, encoding="utf-8"))
        if "blind" in fr.get("splits", {}):
            report["blind_first_run"] = {"generated_at": fr["generated_at"], **fr["splits"]["blind"],
                                         "note": "Historical first-run report supplied in the original ZIP; not independently reproduced here. Fixes made after this run are reflected in 'blind' above."}
    e2e = os.path.join(REPORTS, "e2e.json")
    if os.path.exists(e2e):
        browser_report = json.load(open(e2e, encoding="utf-8"))
        if browser_report.get("source_hash") == source_hash():
            report["e2e_browser"] = browser_report
        else:
            report["e2e_note"] = "Browser report does not match this source. Rerun eval.run_e2e."
    report["source_hash"] = source_hash()
    report["engine"].update(mode=llm.mode(), llm_configured=llm.configured())
    os.makedirs(REPORTS, exist_ok=True)
    with open(os.path.join(REPORTS, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, default=str)
    return report


def pct(x):
    return "–" if x is None or x[0] is None else f"{100*x[0]:.1f}% (n={x[1]})"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", nargs="+", default=["template", "dev", "blind"])
    a = ap.parse_args()
    rep = run(a.splits)
    print("\n=== Lumen Copilot evaluation ===")
    for s, v in rep["splits"].items():
        print(f"[{s:8}] n={v['n']:4}  intent {pct(v['intent_ok'])}  destination {pct(v['dest_ok'])}  strict {pct(v['dest_strict'])}  ui-state {pct(v['state_ok'])}")
    o = rep["overall"]
    print(f"faithfulness {o['faithfulness']}  hallucination {o['action_hallucination_rate']} (unguarded baseline {o['unguarded_baseline_hallucination_rate']})  "
          f"latency p50 {o['latency_p50_ms']}ms p95 {o['latency_p95_ms']}ms  errors {o['error_rate']}")
    an = rep["analytical"]
    print(f"analytical: direction {pct(an['direction_accuracy'])} driver {pct(an['driver_accuracy'])} cause@1 {pct(an['cause_top1'])} cause@3 {pct(an['cause_top3'])}")
    print(f"dialogues: task success {rep['dialogues']['task_success']} turn acc {rep['dialogues']['turn_accuracy']}")
    for k, v in rep["retrieval"].items():
        print(f"retrieval {k:26} MRR {v['mrr']}  R@1 {v['recall@1']}  R@5 {v['recall@5']}  R@10 {v['recall@10']}")
    print(f"failures: {len(rep['failures'])}")
