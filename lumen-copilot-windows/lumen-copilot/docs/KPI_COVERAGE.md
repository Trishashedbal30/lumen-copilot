# Hackathon expectations and demonstration coverage - 11 October 2026

Latest: [11 October data-question audit](DATA_QUESTION_AUDIT.md). Current checks: 73 tests, 68 separate data probes, 323/323 reused destinations/states, 94 independent UCI checks, 80/80 browser states/destinations and live Groq/browser evidence. Earlier snapshots below retain their historical scope. Current configured Windows URL: http://localhost:8004.

Open **/readiness** directly in the browser; diagnostic links are kept outside the normal dashboard interface. In this workspace `.env` currently selects port **8004**, so use http://localhost:8004/readiness. The launcher respects that choice. The page distinguishes current runtime state from recorded evidence and labels source-stamped reports that no longer match code.

| Expectation | Implemented path | What to demonstrate / remaining scope |
|---|---|---|
| Understand the whole application | Exported local metadata catalog, navigation hierarchy, view/widget/filter schemas, graph and search | 210 pages including one real UCI page; inspect /graph and /api/meta. This is a local no-code-style application, not metadata exported from a supplied external platform. |
| Intent and retrieval | Local Ollama slots, deterministic exact controls, BM25 + character TF-IDF vector retrieval, graph reranking | Visible understanding source, model request status and candidate trace. Dense neural embeddings are optional, not claimed active. FAISS/Milvus is not required for this scale. |
| Act on the application | Typed navigate/filter/date/compare/sort/top-N/grain actions, validator barrier, browser action runtime | Correct page and highlighted matching grid/chart; applied-state check after actions. |
| Data queries | Metadata/semantic QuerySpec compiler and separate synthetic/UCI DuckDB connections | Open query evidence: definition, dataset, actual dates/filters and SQL. No arbitrary LLM SQL is executed. |
| Analytical reasoning | Trends, period comparisons, additive country contributors, synthetic cross-view signal investigations | UCI month-to-month country deltas reconcile numerically. External causal explanations require supporting evidence. Synthetic anomalies are planted, not historical UCI events. |
| Context and recovery | Follow-ups, undo, clarification/refusal, explicit model fallback, confirmation for saved views | France follow-up; undo; unsupported profit; save/confirm/reopen. No platform database mutations. |
| External no-code data | Baserow read-only table/field-schema connector, paginated snapshot, provenance, existing validated UCI import | Ten API contract tests pass. Live platform not executed: no account/table/token. No external dashboard/widget/navigation control or write-back. See NO_CODE_INTEGRATION.md. |
| UX and persistence | Embedded conversational companion, charts, KPI cards, evidence links, local bookmarks | Browser verification and refresh/reopen tested. No formal user usefulness survey, durable chat, authentication or role enforcement. |

## Measured KPIs

These are measured cases, not a promise of arbitrary-request accuracy. The reused benchmark comprises 350 requests across 209 synthetic pages. 323 have destination/state labels. The UCI workflow is evaluated separately using original-source numerical references and browser tasks.

| KPI | Current evidence | Interpretation |
|---|---|---|
| Intent | 350/350 reused requests | Broad intent categories; development reused these cases. |
| Destination | 323/323 acceptable-destination labels (100%); strict preferred-page labels remain separate in latest.json | The previous Electronics/Hyderabad mismatch is fixed; expected labels were preserved. |
| Backend UI state | 323/323 applicable requests | Filters/dates/sort/compare/top-N; distinct denominators appear in latest.json. This alone is not browser proof. |
| Final broad browser | 80/80 destination and applied state; 6/6 dialogues | Selected existing corpus, not all 350 requests. |
| Multi-turn task success | 6/6 reused dialogues, 20/20 turns | Measured dialogue tasks; average 1.93 state-changing actions/request in broader benchmark. |
| Retrieval | Graph-reranked MRR 0.9954; precision@1 0.9907; precision@5 0.2421; relevant-page recall@5 0.9712; first-hit rate@5 1.0 | Precision counts acceptable pages among all five returned; most questions have only one or a few labelled acceptable pages. Relevant-page recall counts all acceptable labels. Historical recall@k is retained as first-hit rate; new definitions distinguish them. n=323. |
| Analytical correctness | 94/94 original-workbook independent calculations previously passed | Decimal aggregation and independent workbook/CSV parsing, totals/months/country and product rankings/comparison/contributor reconciliation. Original workbook and runtime calculations remain unchanged in this audit. |
| Explanation traceability | 1,216/1,216 reused numerical statements trace to facts | Traceability does not independently prove every explanation or external cause. |
| Reliability | 0 invalid final states and 0 uncaught errors in measured reused rules corpus | Guardrails validate metadata controls; this is not a claim that all LLM proposals or user intents are correct. Earlier model failures remain documented. |
| Rules latency | p50 14.7 ms; p95 38.3 ms | Backend rules execution on this laptop; not model/browser timing. |
| Browser latency | p50 1,273 ms; p95 1,597 ms | UI action delays included; focused 20-case run. |
| Actual local inference | A new 11 October UCI top-countries turn succeeded in 4,491.4 ms | `oct11_live_llm.json`, current source, no model error, correct country ranks, backend consistency verified. One sample, not a latency percentile or general model benchmark. |
| Human task requirements | 3/3 browser cases rerun; previous separate backend 3/3 | Human questions from the user's task, visible during implementation. Genuine unseen holdout and UX ratings still need human input. |
| Tests | 35/35 passed in 28.57 seconds | Original 24 tests preserved, ten connector checks and one independent retrieval-metric check added. |
| Judge evidence page | Browser smoke passed | Ten KPI rows, current catalog, refresh and no JavaScript errors; screenshot/report in eval/reports/judge_checklist.*. |

Reports live in `eval/reports/`. The prior broad 80-case browser run remains archived with 79/80 destinations and 80/80 applied states. Do not mix its scope or source version with today's focused run. `/api/readiness` exposes the evidence provenance alongside current runtime health. The current model-request counters reset at server startup; a diagnostic/in-process model call has its own report and does not increment the running server's counters.

## Five-minute route

1. 0:00-0:35: show UCI/Synthetic labels and catalog/graph; state the complete agent loop.
2. 0:35-1:20: UCI `Show monthly revenue for 2011`; show monthly control and partial December.
3. 1:20-2:00: `Top 5 countries by revenue in 2011`; show destination, top-N, descending sort and evidence SQL.
4. 2:00-3:00: `Compare revenue in two available months`; show October/November and country contributions; `what about France?` then `undo`.
5. 3:00-3:40: evidence deep link; `save this view`; confirm and reopen after refresh.
6. 3:40-4:20: `Show profit in 2011` clarifies; show prepared actual Ollama trace. Hybrid legitimately chooses rules for grounded requests.
7. 4:20-5:00: /readiness, measured scopes and limits; invite one human challenge.

Before presenting, run `doctor.py --llm`, rehearse in the presentation browser and collect unseen classmate questions. Another dataset/database is optional; complete and traceable sales execution is the strongest available demonstration. Winning depends on judging and presentation as well as implementation, and is not guaranteed by benchmark scores.

Latest monthly-average regression: 40/40 tests passed (25.40 seconds). Current focused browser rerun passed 20/20 destination/state plus six dialogues; p50 1,251 ms / p95 1,557 ms. Additional targeted browser checks passed the user average question on both datasets, SQL/evidence links, independent UCI mean, France follow-up and undo. Latest reused rules latency p50 14.7 ms / p95 24.2 ms; same existing destination mismatch. See VERIFICATION_REPORT.md for the monthly-average definition and results.
