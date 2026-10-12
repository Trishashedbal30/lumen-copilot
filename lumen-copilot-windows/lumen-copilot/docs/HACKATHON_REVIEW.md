# Hackathon review — current workspace

Latest: [11 October data-question audit](DATA_QUESTION_AUDIT.md). Current checks: 73 tests, 68 separate data probes, 323/323 reused destinations/states, 94 independent UCI checks, 80/80 browser states/destinations and live Groq/browser evidence. Earlier snapshots below retain their historical scope. Current configured Windows URL: http://localhost:8004.

The complete agent loop is working on Windows: understand → retrieve destination → plan typed controls → validate → calculate in DuckDB → show evidence → apply browser actions → verify applied state. The original architecture and 209 synthetic pages are preserved. One genuine UCI sales view is added; app metadata now has 210 pages.

Read [measured verification report](VERIFICATION_REPORT.md) for denominators, timings, failures and exact commands. Read [real-data policy](REAL_DATA.md) for source attribution, eligibility rules and supported controls. Read [five-minute demo](DEMO_SCRIPT.md) and [judge answers](JUDGE_QA.md) for rehearsal.

## Implemented in priority order

1. Windows reliability: initial 17 tests passed; launchers use/validate the correct virtual environment, retain exit errors and show diagnostic/port failures. Ollama was found locally, the supplied model created and configured, actual inference measured, and per-turn understanding/request/fallback status made visible. Navigation, filters, dates, comparisons, top-N, follow-ups, undo, evidence and browser-local saved views were exercised in Windows Chromium.
2. Genuine data: official Online Retail II workbook downloaded, both sheets and actual columns inspected, 1,067,371 source rows imported into dedicated tables with 1,007,913 eligible positive sales rows. Original and exported aliases are supported. The separate metadata-backed sales page uses GBP, imported date/dimension bounds, numerical country contributions and the same agent/UI verification pipeline. Synthetic operational scenarios remain labelled and unchanged.
3. Evidence: independent Decimal/Pandas calculations from the original source workbook passed 94 checks. Separate human-authored task cases passed backend and browser evaluation with destination, controls, calculation, verification scope and latency recorded separately. Demo and judge materials now describe actual capabilities and limits.

## Results to quote

Final unit/integration suite: 73/73 passed. Reused synthetic benchmark: 350/350 intents and 323/323 acceptable destinations/states, with original labels unchanged. Separate agent-authored data audit: 68/68. Final broad browser: 80/80 destinations/states, six dialogues. Independent real-data checks: 94/94. Human task browser: 3/3. Actual Groq plus browser and saved-view persistence checks passed; HTTP-429 fallback samples remain documented.

Actual Ollama synthetic and retail turns succeeded; recorded retail examples took about 3.88–4.40 seconds, with one model/browser turn at 4.96 seconds. These are individual samples. Earlier timeouts and invalid/unrequested slots occurred and were documented. Retrieved catalogs and JSON schema/request-entity constraints fixed the observed cases. Never quote rules benchmark latency as model latency or claim arbitrary-request accuracy.

## What remains

Collect genuinely unseen human questions from classmates, freeze expected labels and run the separate challenge runner. Rehearse on the presentation laptop, warm/check Ollama, and keep a backup recording. A completely fresh empty-venv install and second-laptop hardware were not exercised here. No paid API, new model download or additional UCI import is required for this workspace's current demo.

This is a local metadata-driven prototype, with a tested read-only Baserow sales-data adapter; external platform UI control and production deployment are unsupported. UCI transactions provide country/product sales contributors, not evidence for floods, stockouts, campaigns, churn or delivery causes. The synthetic explanations use planted anomalies and correlated signals. No authentication, roles or durable chat database; saved views are browser-local. Typed input is the reliable local demonstration.

## 11 October expectation audit

See [KPI coverage](KPI_COVERAGE.md) and the sidebar Judge checklist (/readiness). Added explicit set-based retrieval precision/recall, a Baserow read-only table/schema snapshot with import provenance, ten HTTP/configuration connector tests and a retrieval-metric arithmetic check. Final audit: 35 tests passed; focused browser 20/20 plus six dialogues; real human task browser 3/3; live Ollama diagnostic passed and a fresh UCI inference succeeded in 4.49 seconds. The active .env port is 8001 and was preserved. Live Baserow needs an endpoint/table/token; Docker engine did not respond. Another database is optional for the local challenge requirements.
