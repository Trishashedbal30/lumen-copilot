# Data-question audit - 11 October 2026

This audit checks supported operations; it does not establish that every possible wording, language or statistical question is understood. The new 68 cases are **agent-authored regression probes**, separate from the reused benchmark and the human challenge file.

## Changes from this audit

- Explicit monthly/weekly/quarterly data requests produce a time series. Named pages such as Monthly Business Review remain page lookups.
- `avg`, nearby analytical misspellings, above/below-average months, and month/week/quarter peak or trough requests are grounded before planning. The monthly mean uses complete calendar months, includes zero-activity months, and uses strict above/below comparison.
- The model receives corrected analytical wording. Valid deterministic dates and fully specified comparison periods survive model proposals and unnecessary clarification. `group_by:month` is normalized to time grain.
- Every provider's filter proposals are checked against request entities, aliases and applicable context. A valid but unrequested filter is blocked and shown honestly.
- Unknown UCI country/StockCode values and unavailable calculations clarify. The app does not substitute gross sales for net sales, revenue for counts, or totals for medians/forecasts.
- City/category requests prefer the more specific city destination. The previously recorded Hyderabad/Electronics destination mismatch is fixed without changing benchmark labels.
- Saved views persist exactly the UI controls; derived render comparison fields are excluded.
- HTTP 429 reports a readable model rate-limit error and explicit rules fallback.

## Measured results

| Check | Result | Scope |
|---|---|---|
| Unit/integration regressions | 73 passed | All project tests, including imports, connector contracts, unavailable operations and model-proposal regressions |
| Reused question corpus | 350/350 intents, 323/323 scored destinations and states | Existing labels unchanged; not an unseen holdout; strict preferred-page results are separate |
| Separate data audit | 68/68 passed | All 34 synthetic metrics across six domains, filters, ranks, trends, periods, averages and unsupported-operation cases |
| Independent real-data reference | 94/94 passed | Official workbook parsed independently with Decimal arithmetic; totals, ranks and period contributors |
| Broad browser | 80/80 destinations and applied states; 6/6 dialogues | Real Chromium action execution; this is 80 selected corpus cases, not all 350 |
| Human-written retail tasks | 3/3 browser | Separate existing human task requirements; not an unseen holdout |
| Monthly-average browser | Both datasets passed | SQL evidence, independent UCI mean, France follow-up and undo |
| Saved-view browser | Both datasets passed | Decline, confirmation, refresh, reopen, exact controls and no JS errors |
| Actual Groq plus browser | Passed | Average question, grounded revenue calculation, correct controls, evidence link and applied-state verification; latest individual latency in groq_live_browser.json |

The raw-table reference audit uses handwritten aggregation expressions rather than the QuerySpec compiler or analytical helper as its expected calculation. Rankings check membership, order and amounts. Monthly means independently aggregate calendar totals. This complements the separate workbook oracle; it does not independently validate the synthetic generator itself.

## Model failures and recovery remain visible

The first 60-case live Groq run had 11 successful inferences, 44 HTTP-429 rules fallbacks and 5 requests requiring no model. It recorded 58 passing tasks; ambiguous `churn` legitimately clarified, and a misspelled mean question unnecessarily clarified. Initial reports are preserved.

A paced eight-case run exposed an unnecessary available-month clarification and a `group_by:month` proposal. Both received regression fixes. The subsequent six-case run answered all six correctly: **five successful Groq inferences and one HTTP-429 rules fallback**. A separate final browser request subsequently completed actual Groq inference and passed independent calculation and applied-state verification.

Do not describe fallback answers as successful LLM calls. Request pacing cannot guarantee an account's API quota. Use local Ollama for a network-independent backup; its configuration is saved in `.env.ollama.local`. Source-stamped reports from earlier runs remain historical evidence if they differ from current code.

## Supported boundary

Synthetic data provides the metrics listed in the application metadata for sales, delivery, inventory, marketing, support and customers. UCI provides **positive-sales revenue in GBP** with country/StockCode filters, revenue rankings, trends, period comparisons and numerical country contributions.

Update: UCI now exposes distinct eligible invoice count (order count), quantity sold, average order value and customer-ID revenue rankings. Customer counts, unit prices, tax, profit and net returns remain unsupported. See RETAIL_IMPROVEMENTS.md for the latest measured checks. Median/percentile/variance/correlation, predictions, and yearly UI chart buckets are unavailable and clarify. Totals for a specified year are supported. Row-level invoice/customer lookup, arbitrary SQL, external causal claims and external-platform UI control are not implemented. English is tested; universal multilingual understanding is not measured.

## Windows replay

From the project folder:

```powershell
.\start.bat
# App: http://localhost:8004 (or the URL printed by your configured launcher)
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m eval.run_data_audit --mode rules
.\.venv\Scripts\python.exe -m eval.run_data_audit --mode llm --ids sales.avg sales.typo retail.top retail.monthly retail.period retail.mean --delay 25 --output data_audit_llm_replay.json
.\.venv\Scripts\python.exe -m eval.verify_live_model_browser --url http://localhost:8004
.\.venv\Scripts\python.exe -m eval.verify_saved_views_browser --url http://localhost:8004
```

The last browser commands use the running server's mode. Live audit requires the configured API key and model availability. A live provider rate limit is reported separately from backend/browser correctness. For a rules-only broad browser benchmark, start an isolated server with `LUMEN_AGENT_MODE=rules` on a different free port; never call its latency model latency.
