# Lumen Copilot — Windows hackathon demo

New: [retail reliability and analysis improvements](docs/RETAIL_IMPROVEMENTS.md): clarification choices, partial-period warnings, order count, quantity sold, average order value, customer-ID rankings and product contributors. Restart the app to load them.

Earlier audit: [11 October data-question audit](docs/DATA_QUESTION_AUDIT.md). Current checks: 73 tests, 68 separate data probes, 323/323 reused destinations/states, 94 independent UCI checks, 80/80 browser states/destinations and live Groq/browser evidence. Earlier snapshots below retain their historical scope. Current configured Windows URL: http://localhost:8004.

Lumen is a local, context-aware application agent: understand a request → retrieve a metadata-backed page → plan typed controls → validate → query DuckDB → show calculation evidence → apply UI actions → verify the applied state.

Read [WINDOWS_START_HERE.md](WINDOWS_START_HERE.md), [real-data policy](docs/REAL_DATA.md), and [hackathon review](docs/HACKATHON_REVIEW.md).

## Run on Windows

Python 3.12, 64-bit recommended (3.11–3.13 supported). From this folder:

```powershell
.\setup.bat                       # first installation; Internet needed for dependencies
.\start.bat                       # subsequent starts; uses .venv\Scripts\python.exe
# Open http://localhost:8000; stop with Ctrl+C.
```

This workspace already has its Windows virtual environment, Ollama configuration and imported official UCI workbook. No paid API is needed. Runtime data, charts, fonts and model weights are local. The launchers do not require PowerShell activation or an execution-policy change. They preserve failed exit codes and show diagnostic/port errors.

## Existing and new capabilities

The preserved synthetic Sahyadri Retail demo has 209 metadata-defined pages spanning sales, inventory, delivery, marketing, support and customers. It supports navigation, filters, dates, comparisons, top-N, sorting, time grain, follow-ups, undo, SQL evidence and confirmed browser-local saved views.

A separate **UCI Online Retail II** mode adds sales overview and customer-ranking pages using genuinely imported historical data. It has monthly revenue, country revenue, product StockCode rankings, period comparisons, numerical contributors and the same copilot/action/verification loop. Use the dataset selector above page search. Synthetic pages and real-data pages are visibly labelled; synthetic records never enter the UCI tables.

The official workbook has 1,067,371 source rows across two sheets. Under the documented positive-sales cleaning policy, 1,007,913 sales rows are retained and 59,458 excluded. Eligible coverage: 2009-12-01 to 2011-12-09. Revenue is positive invoice-line Quantity × Price in **GBP**, excluding cancellations, returns, invalid required values and exact duplicate rows. Missing customer IDs are retained. It is not net revenue after returns. December 2011 is partial and is labelled accordingly.

Source: Chen, D. (2012), [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii), DOI:10.24432/C5CG6D, CC BY 4.0. The report includes actual source columns, aliases, hashes, cleaning policy, exclusions and date coverage at `/api/datasets`.

## Local model

`.env` selects hybrid mode, Ollama at `http://localhost:11434/v1`, model `lumen-qwen`. The supplied Modelfile uses installed Qwen2.5 3B with an 8192-token context; the prompt includes retrieved page candidates to reduce memory and latency.

```powershell
ollama pull qwen2.5:3b             # only if not already installed
ollama create lumen-qwen -f Modelfile
.\.venv\Scripts\python.exe doctor.py --llm
.\start.bat
```

Configuration is not proof of inference. `/api/health` reports configuration and model request/response/error counts. Every answer shows understanding source and actual model request status. Model errors and rules fallback are visible. Hybrid uses rules for grounded requests and selectively requests the model. Force ordinary business questions through Ollama for a rehearsal:

```powershell
$env:LUMEN_AGENT_MODE='llm'
.\start.bat
# Later, clear the override to return to .env's hybrid mode:
Remove-Item Env:LUMEN_AGENT_MODE
```

Initial large-context calls timed out during this session. The revised prompt and request-grounded JSON schema subsequently passed live grounding checks: a recorded synthetic turn took 3.63 seconds, and retail examples took 3.88 to 4.40 seconds. These are individual measurements, not a model performance benchmark. Cold loading and laptop load can still affect latency; the fallback is explicit.

## Reproduce evidence

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe doctor.py --llm
.\.venv\Scripts\python.exe -m eval.run_eval
# Browser checks need the app running at the supplied URL:
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m eval.run_e2e --url http://localhost:8000
.\.venv\Scripts\python.exe -m eval.run_retail_checks .\data\uci_source\online_retail_II.xlsx
.\.venv\Scripts\python.exe -m eval.run_fresh_challenges
.\.venv\Scripts\python.exe -m eval.run_fresh_challenges --browser --url http://localhost:8000
```

`eval/reports/` contains separate reused-benchmark, Windows browser, live-model, real-data independent and human-task results. The three initial human-task questions came from the project user's requirements; they are not an independent unseen holdout. Collect new questions in `eval/fresh_human_challenges.jsonl`, freeze labels first, and keep their results separate. See [challenge protocol](eval/FRESH_CHALLENGES.md) and [current verification report](docs/VERIFICATION_REPORT.md) for measured results and remaining checks.

## Demo requests

Synthetic: `show south revenue for august`; `Why did South revenue drop in August?`; `top 5 cities by revenue last quarter`; `what about north?`; `undo`; `save this view`.

UCI: `Show monthly revenue for 2011`; `Top 5 countries by revenue in 2011`; `Top 5 products by revenue in 2011`; `Compare revenue in two available months`; `what about France?`; `undo`; `save this view`.

Relative dates follow the active dataset's reference date, not the laptop clock. Unsupported fields or unavailable periods should clarify. UCI transactions cannot establish stockout, flood, delivery, churn or marketing causes. Explanations identify numerical contributors; external causes require supporting evidence.

Scope: one local tenant; no authentication, roles, external platform navigation/write-back, durable chat database, or production-readiness claim. A read-only Baserow UCI table/schema adapter is available; live platform verification requires an actual endpoint/table/token. Chat/undo are server memory; saved views persist in the same browser/origin. Voice support is browser-dependent and may use an online service; typed input is the reliable local demonstration.

## Judge checklist and optional no-code connection

Open `/readiness` directly for capability counts, current model configuration versus actual request counts, KPI evidence, report source stamps and unsupported scopes. Retrieval evaluation now reports set-based precision and relevant-page recall alongside MRR and first-hit rates. See [KPI coverage](docs/KPI_COVERAGE.md) and [Baserow connection instructions](docs/NO_CODE_INTEGRATION.md). Additional databases are optional; keep the complete verified sales workflow as the presentation baseline.

Monthly-average requests: `Which months had revenue above average in 2011?` (UCI) or `in which month was the revenue more than average` (current page scope). Average means the arithmetic mean of complete calendar-month totals, including zero-activity months. Partial edge months are excluded with a note; the chart and SQL evidence use the same aligned dates. Follow-ups preserve this analysis. Add a year/date range when you want to override the selected scope.


## Refined dashboard interface

The dashboard now separates navigation, view controls, charts and the copilot, with responsive drawers on smaller screens. Developer traces and framework names are removed from ordinary answers; understanding status, applied-state checks and calculation evidence remain visible or expandable. Source information and saved views are sidebar disclosures. See [UI verification](docs/UI_REDESIGN.md).


## Olist Brazil real-data workspace

The official Olist ZIP is downloaded and imported into a separate DuckDB database. Select **Olist Brazil / real data** for Sales, Delivery and Reviews pages in BRL. Ask for monthly sales, late-delivery state rankings and review-score comparisons for late versus on-time orders. Existing UCI and synthetic workflows are preserved. See [definitions, source, limitations and checks](docs/OLIST_DATA.md). Restart start.bat and hard-refresh your browser to load this addition.
