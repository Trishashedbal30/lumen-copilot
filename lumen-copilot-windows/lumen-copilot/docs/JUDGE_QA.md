# Likely judge questions

**What makes this more than a chatbot?** It chooses a metadata-backed page, builds typed actions, validates available controls and dimension values, calculates named metrics in DuckDB, applies actions in the browser and compares the actual applied state with the intended state. Answers expose metric definitions, dataset, filters, date coverage and SQL.

**Is it using a real LLM?** Current .env selects Groq with openai/gpt-oss-20b; actual inference plus browser verification passed. Local Ollama with Qwen2.5 3B via lumen-qwen remains the network-independent backup. Configuration and successful inference are separate. Per-turn understanding source and request status identify actual inference, failures and rules fallback. Hybrid uses deterministic rules where grounded. Individual measured calls are in separate live-model reports; rules-mode latency is not model latency.

**Is the data real?** UCI Online Retail II was downloaded from the official source, both workbook sheets were inspected and imported into dedicated DuckDB tables. The source hash, columns, row counts and cleaning exclusions are reported. Synthetic Sahyadri Retail remains separate and labelled. Imported arbitrary CSVs are identified by filename/hash; the app cannot prove a user's file provenance independently.

**What does revenue mean?** Sum of positive Quantity × UnitPrice invoice lines in GBP, excluding C-prefixed cancellations, negative returns, invalid required values, zero/negative quantity or price, and exact duplicates. Missing customer IDs remain. Positive fees/adjustment StockCodes remain as source invoice lines. It is gross positive sales value, not net revenue after returns, profit or audited accounting revenue. No currency conversion or inferred taxes.

**Why is December revenue low?** The source ends on 9 December 2011. December is a partial month and is labelled. The “two available months” comparison selects the last two complete months; do not compare partial December with full November as if both were complete.

**Can it explain why sales changed?** It calculates numerical country contributions over the union of members in both periods, including members absent from one period. Those contributions reconcile to the total change. The invoice dataset alone does not support external causal claims about campaigns, stockouts, weather or churn. Such claims need supporting evidence.

**How accurate is it?** Quote only current denominators in docs/VERIFICATION_REPORT.md. The existing benchmark has been reused during development and is not a fresh holdout. Human task cases are separate. Independent source-workbook Decimal checks validate numbers; browser checks validate application state. These measurements do not establish arbitrary-request accuracy or production readiness.

**Where is the fresh human test set?** eval/fresh_human_challenges.jsonl. The first three questions are the project user's written requirements, already known during development. Additional unseen classmate questions must be collected, labelled and frozen before execution. AI-generated tests are not human holdout evidence.

**Can it operate any no-code platform?** This is a metadata-driven local application prototype. A read-only Baserow sales-table/field-schema adapter is implemented and tested against a local HTTP API fixture. A live platform was not supplied. External page/widget/navigation control and write-back are unsupported; a complete action adapter must export valid controls/navigation and implement the platform action runtime. See NO_CODE_INTEGRATION.md.

**What persists?** Imported databases and browser-local saved views persist. Chat sessions and undo are in server memory; no authentication, roles or durable conversation store. Local typed demo needs no paid API; voice is browser-dependent and may use an online service.

**What happens on failure?** Invalid controls are blocked or clarified; model failures are shown and fall back to rules; unsupported UCI metrics clarify; failed import leaves the previous database intact; browser storage and verification errors are visible. Initial cold model timeouts occurred and are documented.

**Do we need another database or dataset?** No. The problem permits synthetic/sample tenants; the verified local app already has synthetic business views and genuine UCI sales. Baserow is an optional external data integration, not a prerequisite for the existing demonstration. We do not claim arbitrary PostgreSQL/MySQL/SQLite schemas are understood automatically.

**Why is retrieval precision@5 only 0.2421?** Most requests have one or a few labelled acceptable pages. Returning five candidates lowers precision even if a correct one ranks first. We report precision, relevant-page recall, MRR and first-hit rate separately rather than calling all of them accuracy. Destination correctness is measured separately after planning.

**Can it answer any data question?** It supports named metrics and validated operations. The audit tests all synthetic metrics and the UCI revenue workflow, including trends, ranks, comparisons, contextual filters, SQL evidence and applied-state checks. Unavailable fields/statistics clarify. 68 regression probes and a reused 350-question benchmark are measured coverage, not universal natural-language accuracy. Groq quota errors produce visible rules fallback; that is not a successful inference.
