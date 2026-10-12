# Verification report — 10 October 2026 (Windows)

Latest: [11 October data-question audit](DATA_QUESTION_AUDIT.md). Current checks: 73 tests, 68 separate data probes, 323/323 reused destinations/states, 94 independent UCI checks, 80/80 browser states/destinations and live Groq/browser evidence. Earlier snapshots below retain their historical scope. Current configured Windows URL: http://localhost:8004.

Environment: Windows AMD64, project .venv Python 3.12.7, LangGraph active, local Ollama, bundled synthetic DuckDB and separately imported official UCI Online Retail II. App has 209 synthetic pages plus one UCI sales page. The configured app is running at http://localhost:8000 in hybrid mode. Successful inference is shown by actual traces; configuration alone is not a model-call result.

## Executed checks

| Check | Result | Evidence / scope |
|---|---|---|
| Existing baseline tests | 17/17 passed | Executed before real-data implementation |
| Final tests | 24/24 passed | `python -m pytest -q`; last run 23.31 seconds |
| Windows diagnostics | Passed | All dependencies, data bounds and LangGraph; `doctor.py` |
| Actual Ollama diagnostic | Passed | `doctor.py --llm` returned grounded revenue, South and date slots |
| setup.bat | Passed through startup | Existing venv, pinned install, diagnostics, application startup; `setup.bat --no-browser` |
| start.bat | Passed through startup | Existing venv and diagnostics; `start.bat --no-browser`; hybrid server at port 8000 |
| Occupied-port error | Correctly exited 1 | start.bat exposed the port error and preserved failure status |
| Reused rules benchmark | 322/323 applicable destinations; 323/323 backend states | 350 requests (252 template, 49 dev, 49 reused blind), `latest.json`; rules p50 15.5 ms, p95 25.9 ms |
| Reused strict blind destination labels | 36/44 | Wider acceptable-destination score: 43/44; not a fresh holdout |
| Reused dialogue and analytical checks | 6/6 dialogues, 20/20 turns, 11/11 analytical driver questions | Synthetic planted scenarios; not real-world cause validation |
| Broad Windows browser run | 79/80 destinations, 80/80 applied states, 6/6 dialogues | `windows_priority1_e2e.json`; before final highlight/layout polish; browser p50 1,270 ms, p95 1,597 ms |
| Final focused Windows browser run | 20/20 destinations and applied states, 6/6 dialogues, no failures | `e2e.json`; p50 1,263 ms, p95 1,577 ms |
| Synthetic browser smoke | Passed | Navigation, filters, dates, comparison, top-N, follow-up, undo, evidence, persistent/reopened saved view; `windows_smoke.json` |
| Genuine retail browser smoke | Passed | Eight turns, applied controls, evidence, follow-up, undo, save/refresh/reopen; no JavaScript errors; `retail_browser.json` |
| Independent genuine-data calculations | 94/94 checks passed | Independent workbook parsing and Decimal arithmetic, not importer/semantic SQL reused for expected results; `retail_independent.json` |
| Human-written task cases, backend | 3/3 passed | Separate destination, controls, numeric oracle, backend consistency and latency; `fresh_human_backend.json` |
| Human-written task cases, final browser | 3/3 passed | Real browser applied state plus independent calculation checks; `fresh_human_browser.json` |
| Individual actual model agent turns | Passed | Synthetic 3,626.8 ms; UCI country ranking 4,401.9 ms; UCI monthly revenue 3,875.4 ms. Separate live-model reports |
| Actual model plus browser | Passed | UCI top countries, 4,955.2 ms agent latency; visible LLM source/status and all controls verified; `retail_live_browser.json` |

The final focused browser report covers 20 selected existing cases; do not describe it as the full 350-case corpus. The earlier broad browser report covers 80 cases. Browser timings include UI action delays; backend rules timings do not. Individual model timings do not establish model latency percentiles or general accuracy.

## Real import and numerical findings

Official source workbook: data/uci_source/online_retail_II.xlsx. SHA-256: `bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980`.

Both original sheets were inspected: Year 2009-2010 (525,461 rows), Year 2010-2011 (541,910 rows). Actual columns: Invoice, StockCode, Description, Quantity, InvoiceDate, Price, Customer ID, Country. Alternate InvoiceNo/UnitPrice/CustomerID aliases were tested with workbook/CSV fixtures.

Input: 1,067,371 rows. Retained eligible sales: 1,007,913. Exclusive exclusions: cancellations 19,104; negative returns 3,393; duplicates 34,335; nonpositive quantity/price 2,626. Optional missing customer IDs retained: 228,488. No eligible descriptions were missing in this workbook. Eligible coverage: 2009-12-01 to 2011-12-09.

Independent all-time positive invoice-line sales value: **GBP 20,476,260.448** (displayed to two decimal places). This policy excludes returns/cancellations and retains positive source fee/adjustment StockCodes; it is not net revenue or audited accounting revenue. The Decimal reference and runtime floating-point values agree within GBP 0.005.

2011 eligible sales revenue: GBP 9,820,676.07 (through 9 December). Top countries: United Kingdom 8,255,661.87; Netherlands 276,661.86; EIRE 273,107.26; Germany 213,472.66; France 200,027.06.

Two latest complete months: November 2011 GBP 1,503,866.78 versus October GBP 1,151,263.73; change GBP 352,603.05. Biggest numerical country contribution: United Kingdom +GBP 384,529.93, with offsets from other countries. Country contributions reconcile to the total change. December is explicitly partial; external business causes are not inferred.

Source and cleaning policy: [REAL_DATA.md](REAL_DATA.md) and `/api/datasets`. Attribution: Chen, D. (2012), [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii), DOI:10.24432/C5CG6D, CC BY 4.0.

## Failures, limitations and remaining human work

One reused destination-label mismatch remains: “revenue for the electronics category in hyderabad last month” selects the Electronics page with Hyderabad applied. Its numerical scope and applied state are correct; the expected destination labels favor other pages. It remains reported as a destination failure.

Initial large-context Ollama requests timed out. Subsequent unconstrained model proposals included an invalid year filter, a placeholder metric and unrequested alphabetical country filters. Failed attempts are preserved in `retail_live_llm_initial_blocked.json`, `retail_live_llm_second_blocked.json` and `retail_live_llm_unrequested_filters.json`. JSON schema constraints now restrict valid metric/control names and filters to request/context entities; revised live checks passed. Exact top-N/sort/grain controls remain grounded by deterministic parsing. This does not prove correctness on all language variants.

The three initial human questions are from the project user's requirements and were visible during implementation. They are not a fresh independent holdout. Additional unseen human questions still need classmates/user input and frozen labels. The separate file and runner are ready at `eval/fresh_human_challenges.jsonl` and `eval/run_fresh_challenges.py`. No AI-written questions are labelled as independent human evidence.

A completely fresh Windows install in an empty virtual environment was not executed; setup was exercised with this workspace's existing venv and installed dependencies. A second laptop's RAM/GPU, cold-load behavior, browser storage restrictions and presentation environment still require rehearsal. No model download or dataset import action is currently required on this workspace.

Unsupported: external no-code platform control, authentication/roles, durable conversation storage, UCI margin/churn/inventory/operational causes, description-based product filters and arbitrary geography groupings. Bookmarks are local to the same browser/origin/port. Voice may use online browser services; typed input is the reliable local path.

## Reproduce

```powershell
.\.venv\Scripts\python.exe doctor.py --llm
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m eval.run_eval
# App running at port 8000:
.\.venv\Scripts\python.exe -m eval.run_e2e --url http://localhost:8000
.\.venv\Scripts\python.exe -m eval.run_retail_checks .\data\uci_source\online_retail_II.xlsx
.\.venv\Scripts\python.exe -m eval.run_fresh_challenges
.\.venv\Scripts\python.exe -m eval.run_fresh_challenges --browser --url http://localhost:8000
```

## Follow-up audit - 11 October 2026

See [KPI_COVERAGE.md](KPI_COVERAGE.md). Final 35/35 tests passed in 28.57 seconds; original 24 remain passing. Added ten read-only Baserow HTTP API/configuration tests and a set-based retrieval arithmetic check. Live external Baserow was not executed. The new judge checklist passed browser inspection and refresh without JavaScript errors.

Reused benchmark rerun: 322/323 destinations, 323/323 backend states; same single mismatch. Rules latency p50 14.7 ms / p95 38.3 ms. Graph-reranked retrieval MRR 0.9954, precision@5 0.2421, relevant-page recall@5 0.9712 and first-hit rate@5 1.0 across 323 labelled requests. Definitions are stored in latest.json.

Current-source focused browser rerun: 20/20 destination and state, 6/6 dialogues, p50 1,273 ms / p95 1,597 ms. Separate real task browser rerun: 3/3. New actual Ollama retail turn succeeded in 4,491.4 ms with backend consistency verification, saved in oct11_live_llm.json. doctor.py --llm passed. Previous 94/94 original-workbook calculations retain their historical run date; sales calculations and original active workbook did not change.

The current .env selects PORT=8001; it was preserved. start.bat successfully starts the final hybrid app at http://localhost:8001. An attempted start while the test server occupied that configured port correctly exited 1; the test server was stopped before launching the final app. A first ad-hoc report script used the wrong trace key (step instead of node), was corrected, and the model report was recorded successfully; this was a report-script error, not an inference failure.

## Monthly-average request regression - 11 October

The user's exact question, "in which month was the revenue more than average", previously returned a KPI total. It now plans a monthly-average analysis, keeps the selected filters/date scope, aligns to complete calendar months, sets monthly grain, turns off period comparison, calculates an arithmetic mean with parameterized SQL, and lists all monthly totals strictly above/below that mean. Zero-activity complete months count as zero; partial edge months are excluded and explained. Ratio/non-additive metrics clarify. The same operation carries into entity follow-ups and has an evidence deep link.

Final tests: 40/40 passed in 25.40 seconds. Independent fixture checks cover empty months, equal-to-average exclusion, below-average requests, source aggregation, partial-month clarification, model grounding, UCI workbook-oracle agreement and follow-ups. Browser regression passed for synthetic and UCI, both line series (totals/mean), SQL evidence, applied state, evidence link, independently checked France follow-up and undo. Reports/screenshots: monthly_average_browser.json and monthly_average_*.png. An actual Ollama average request succeeded; monthly_average_llm.json records its source/status and result before the final follow-up/evidence addition.

UCI 2011: complete January-November monthly average GBP 834,806.16; above-average September GBP 1,056,435.19, October GBP 1,151,263.73 and November GBP 1,503,866.78. Partial December is excluded. Synthetic selected July 3-September 30 scope: full August/September average INR 40.89 crore; September INR 42.63 crore is above average. These scopes are distinct.

Reused benchmark remains 322/323 acceptable destinations and 323/323 backend states (same known destination mismatch); current rules p50 14.7 ms, p95 24.2 ms. The baseline contains no newly invented human questions. Reproduce the targeted browser check with `python -m eval.verify_monthly_average_browser --url http://localhost:8001` after restarting the app.

Final post-follow-up source browser rerun: 20/20 destinations and UI states, six dialogues passed, p50 1,251 ms / p95 1,557 ms; no failures. Exact matching-source browser results are bundled in latest.json. The original running server on configured port 8001 requires restart to load the new code; temporary verification used port 8002 and was stopped afterward.

## Monthly-average spelling regression - 11 October

The exact user sentence "which moths revenue is more than avegare" previously bypassed the monthly-average branch. A context-limited analytical normalizer now recognizes nearby spellings of month/months/monthly and average when a comparison cue is present. Corrections are visible in the understanding trace (moths -> months, avegare -> average). Known lexical entities and ordinary non-comparison requests are protected; this is targeted spelling tolerance, not arbitrary-language understanding.

45/45 tests passed in 29.94 seconds, including the exact sentence, nearby misspellings, below-average requests and protected-entity/non-comparison behavior. Reused benchmark unchanged: 322/323 destination labels, 323/323 backend states, same existing destination mismatch; rules p50 21.5 ms / p95 33.0 ms in this run. Earlier browser reports keep their own source stamps and dates. Reproduce this browser regression using `python -m eval.verify_monthly_average_browser --url http://localhost:8001 --typos` after restarting the server; its report is monthly_average_typos_browser.json.
Targeted typo browser regression passed on both synthetic and UCI: visible corrections, monthly-average calculation, SQL evidence link, independent UCI values, France follow-up and undo. Temporary verification server used port 8002 and was stopped afterward.
