# Retail reliability and analysis improvements

Implemented in the existing application pipeline without replacing the architecture or synthetic demonstration. No reimport, additional database or new dependency is required for the imported workbook in this workspace.

## What users can do

- Ask "Show the best products in 2011" and select Revenue, Quantity sold or Order count. The initial clarification makes no UI changes. Each choice executes a complete request with the original year and dimension.
- Ask "How many orders in 2011?", "Show monthly quantity sold in 2011", or "What was average order value in November 2011?". The overview now has four summary cards and sortable metric columns.
- Ask "Who are the top 10 customers by revenue in 2011?". The agent navigates to the metadata-backed customer sales page, applies dates and top-N, ranks actual Customer IDs and verifies the applied controls. Customer-ID filtering, evidence and existing view actions use the same pipeline.
- Ask "Compare revenue in November 2011 and December 2011". Coverage warnings explain the incomplete December. A clickable "Compare first 9 days" choice applies 1-9 December versus 1-9 November. No claim of a complete December is made.
- Ask "Compare revenue in October 2011 and November 2011", followed by "Which products contributed most to the change?". The answer includes a contribution chart, actual current-minus-comparison changes and a residual for remaining products, with SQL and dataset/date evidence.

## Definitions and limitations

All analyses use eligible positive sales under the existing import policy. Order count is COUNT(DISTINCT invoice). Quantity sold is SUM(quantity). Average order value is SUM(revenue)/COUNT(DISTINCT invoice), with an undefined value if there are no orders. These values are calculated at the selected scope; product-filtered AOV is selected-product revenue per participating invoice. Order counts can overlap across product groups, and AOV is not additive.

Customer rankings exclude missing IDs but retain source IDs without inventing names. Summary totals include unidentified customers unless filtered to known IDs. Revenue shares in customer rankings are shares of that overall eligible-sales total. Country/product/customer filters use imported values and reject unknown values.

Product decomposition currently explains revenue changes only. Displayed contributors are the five largest absolute changes over the union of products in both periods; absent products have zero revenue in that period. The combined residual preserves both positive and negative changes. Invoice data cannot establish campaigns, stockouts or other external causes. Customer counts, churn, profit, taxes and net-return metrics remain unsupported.

## Verification evidence

- 90 unit/integration tests passed, including rules and mocked-model grounding, metric selection, executable clarification choices, incomplete-period/equivalent-day behavior, customer ranks, unknown-ID rejection, follow-ups and reconciled contribution evidence.
- 50 independent checks from the original Excel workbook passed: Decimal/Pandas eligibility and calculations for order count, quantity and AOV across available years; top-ten customer identities and amounts; product contributor ordering, deltas and reconciliation. No runtime importer or SQL is used to derive expected values.
- Chromium: ten new-feature requests passed, including clickable choices, actual customer destination/filter controls, evidence links, applied-state verification and partial-period comparisons. Four responsive viewport checks passed for both datasets; existing saved-view persistence was also verified.
- Unchanged reused synthetic benchmark: 350/350 intents, 323/323 acceptable destinations and states, no failures. This is not a new independent question corpus.
- Three actual configured Groq model requests succeeded, with backend verification, at approximately 1.69-1.74 seconds each. These are individual samples; they were not model-plus-browser tests and do not establish arbitrary-question accuracy. Browser runs used an isolated rules-mode server.

Files: eval/reports/retail_extensions_independent.json, retail_extensions_browser.json, retail_extensions_live.json, ui_layout.json, saved_views_browser.json and latest.json. Reports contain source stamps and separate scopes. The new test questions are agent-authored regressions; no fresh human holdout is claimed.

## Windows

Stop the existing server with Ctrl+C and run:

```powershell
.\start.bat
```

Open http://localhost:8004 and press Ctrl+F5. Select UCI Retail II real data. For repeatable validation:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m eval.run_retail_extensions data/uci_source/online_retail_II.xlsx
.\.venv\Scripts\python.exe -m eval.verify_retail_extensions_browser --url http://localhost:8004
```

The browser runner uses the current server mode. Use rules mode for deterministic UI checks and keep successful live inference claims separate.
