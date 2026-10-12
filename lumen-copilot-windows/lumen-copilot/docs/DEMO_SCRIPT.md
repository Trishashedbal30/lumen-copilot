# Five-minute presentation

Before the judges arrive: run doctor.py --llm to check the configured provider (Groq currently; Ollama is the local backup). Start Lumen, select UCI, check date coverage and import report. Keep a backup recording. Use typed input. Put the model turn's actual status in view; configuration alone is not evidence.

**0:00–0:40 — Complete agent loop.** “This agent understands a request, retrieves a valid destination, applies controls, calculates from DuckDB, shows its SQL evidence and checks the actual browser state.” Show the visible UCI label, GBP and source report: official workbook, cleaning counts, historical bounds. Explain that synthetic scenarios remain separately labelled.

**0:40–1:30 — Trend.** Select UCI and ask `Show monthly revenue for 2011`. Point to the page, monthly control, applied-state check and query evidence. December is partial through the ninth; do not describe its lower total as a full-month business collapse.

**1:30–2:15 — Ranking.** Ask `Top 5 countries by revenue in 2011`. Show top-N, sorting and revenue chart. Open Sources to show the metric definition, dataset, dates, filters and SQL. If helpful, ask `Top 5 products by revenue in 2011`; products use original StockCode, including source adjustment codes.

**2:15–3:10 — Compare and explain.** Ask `Compare revenue in two available months`. This picks the last two fully covered months, November versus October 2011. Show totals and country contributions. Ask `what about France?`, then `undo`. “The calculation explains which countries contributed to the change; it does not establish external causes.”

**3:10–3:45 — Evidence and persistence.** Click Evidence to reopen the exact scope. Ask `save this view`, confirm, refresh, reopen Saved views. Show the same controls and date scope. State that bookmarks are local to this browser/origin; chat and undo live in server memory.

**3:45–4:20 — Actual model and guardrails.** For a prepared LLM-mode rehearsal, show a turn with `Understanding: llm` and `Model request: succeeded`, and its measured latency. Hybrid may legitimately use rules for known requests. A model error is displayed with explicit rules fallback. Ask an unsupported question such as `Show profit in 2011` in UCI mode; it should clarify.

**4:20–5:00 — Evidence and judge challenge.** Show docs/VERIFICATION_REPORT.md and the separate report files. Distinguish reused benchmark, independent Decimal calculations, real browser execution and individual Ollama calls. Invite one question. Clarify unsupported fields or unavailable periods; do not infer stockouts, floods or marketing causes from invoice data.

Optional synthetic backup: switch to Synthetic → `Why did South revenue drop in August?` → evidence. Explain that these are planted anomalies on synthetic data and correlated signals, not historical UCI events.

11 October addition: open /readiness for the live catalog/model counters and measured KPI checklist. Current workspace URL is http://localhost:8004 because .env selects PORT=8004. Use docs/KPI_COVERAGE.md for updated figures. Describe Baserow as a tested read-only data adapter, not a live platform/UI connection; no external account was supplied.

Optional analytical challenge: ask `Which months had revenue more than avg in 2011?` in UCI. Mean of January-November: GBP 834,806.16; September, October and November exceed it. December is partial and excluded from this monthly-mean comparison. Point to both chart series and the complete-month explanation. The data-question audit records broad rules coverage, actual Groq inference and rate-limit fallback separately.


## Updated retail demonstration sequence

1. Show monthly revenue for 2011; point to the explicit incomplete-December warning.
2. Ask "Show the best products in 2011"; select Quantity sold to demonstrate clarification before action.
3. Ask "How many orders in November 2011?" and "What was average order value in November 2011?"; expand metric definitions.
4. Ask "Who are the top 10 customers by revenue in 2011?"; show navigation, top-N and verification, then an evidence link.
5. Compare November and December 2011; choose Compare first 9 days.
6. Compare October and November 2011; ask which products contributed most. Show the residual and SQL dates. Describe numerical contributors, not external causes.


## Optional Olist demonstration (one minute)

Switch to Olist Brazil real data. Ask Show monthly sales value for 2017, then Top 5 states by late delivery rate in 2017, then Compare review scores for late and on-time deliveries in 2017. Show automatic navigation across Sales, Delivery and Reviews, matching date/filter controls, applied-state verification and an evidence link. Follow up What about SP? Describe the review difference as an association. Explain that components are aggregated before joining and all dates are purchase-date cohorts. See OLIST_DATA.md for exact metric definitions and tested scope.
