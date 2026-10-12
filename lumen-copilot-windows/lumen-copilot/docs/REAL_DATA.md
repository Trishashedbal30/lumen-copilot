# UCI Online Retail II import and sales workflow

Source: [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii).
Chen, D. (2012), DOI:10.24432/C5CG6D, CC BY 4.0. Original coverage is December 2009 to December 2011. Prices are sterling.

Download the ZIP using the Download button on the official page; extract online_retail_II.xlsx. The importer reads every workbook sheet. Alternatively export each worksheet to a UTF-8 CSV and supply both files. This app cannot authenticate that arbitrary user-supplied files originated at UCI: the report identifies the exact supplied file, columns, row count, sheets and SHA-256. The official workbook downloaded here has recorded hashes.

```powershell
# Stop Lumen before importing/replacing a dataset.
.\.venv\Scripts\python.exe -m backend.data.import_retail .\data\uci_source\online_retail_II.xlsx
# CSVs can use InvoiceNo, UnitPrice, CustomerID or original aliases:
.\.venv\Scripts\python.exe -m backend.data.import_retail .\year1.csv .\year2.csv
# UK day/month order is default; choose this for US-format CSV dates:
.\.venv\Scripts\python.exe -m backend.data.import_retail .\export.csv --date-order monthfirst
.\start.bat
```

The separate data/uci_retail.duckdb contains uci_import_rows (canonical input, including exclusion reason), uci_sales (eligible sales) and uci_import_manifest (report). Import stages a new database and atomically replaces it only after success; stop the app before replacement. Original synthetic data/lumen.duckdb is preserved. Restart refreshes metadata and dimension/date bounds.

Revenue = SUM(Quantity * UnitPrice), GBP gross positive invoice-line sales. It is not net revenue after returns, accounting revenue or profit. Exclusion reasons are exclusive, applied in this order: invalid date, invalid/nonfinite number or product, missing invoice/stock code/country, exact duplicate of the eight canonical columns, C-prefixed cancellation, negative-quantity return, nonpositive quantity/price. Duplicate lines across sheets/files are removed. Customer IDs may be missing and are retained; missing descriptions fall back to StockCode. Product identities use StockCode, avoiding splits when descriptions change. The report lists counts, missing optional values and eligible date coverage. Positive fees/adjustment StockCodes in the source remain in positive invoice-line sales. Taxes, exchange rates and inferred shipping are not calculated. CSV dates should be ISO-8601 where possible; ambiguous numeric dates follow the explicit date-order setting.

Select **UCI Online Retail II** above page search. The one metadata-backed sales page has revenue trend, country revenue, product StockCode ranking and period comparison. The same copilot operates its existing typed actions, validator, query compiler, numerical FactBook, evidence links, verification, undo and browser-local bookmarks. Explicit "UCI" also selects it from a synthetic page. Active UCI requests use imported historical date bounds and country/StockCode options. Relative dates use the last imported sales date; full-year requests are limited to actual coverage with a visible note. Complete comparison periods outside coverage clarify. Empty selections produce no-data responses.

Try: Show monthly revenue for 2011; Top 5 countries by revenue in 2011; Top 5 products by revenue in 2011; Compare revenue in two available months; then "what about France?", "undo", "save this view". Use "product 85123A" for an exact product filter. Product descriptions are not a supported free-text filter. Questions requiring margin, inventory, operational causes or customer churn are unsupported in UCI mode. Use a synthetic page for those demonstration scenarios. Explanations describe numerical country/product contributors; external causes require separate supporting evidence and are not inferred from these transactions.

Run the independent source-data checks after importing:

```powershell
.\.venv\Scripts\python.exe -m eval.run_retail_checks .\data\uci_source\online_retail_II.xlsx
```

Fresh human challenge questions belong in eval/fresh_human_challenges.jsonl. This file is separate from the reused benchmark. Its initial three questions are the human-written questions from this task, not an independent holdout; collect classmates' new questions and freeze expected labels before running. AI-authored importer fixtures and browser smoke requests are not human holdout evidence.


## Retail analysis additions

See [retail improvements and checks](RETAIL_IMPROVEMENTS.md). Order count is distinct eligible Invoice/InvoiceNo; quantity sold is summed eligible Quantity; average order value is eligible revenue divided by distinct eligible invoices in the selected scope. Returns and cancellations stay excluded. With product filters, order value describes the selected product revenue per participating invoice rather than the full baskets. Counts across products can overlap and must not be summed as if disjoint.

Customer rankings use original Customer ID values and exclude missing IDs. No names or invented identities are supplied. Summary cards retain all eligible sales unless a customer filter is selected; ranking revenue shares use this same overall scope including unidentified sales. Customer counts and customer churn remain unavailable.

The final available month, December 2011, ends on 9 December. Queries show coverage warnings; unequal single-month comparisons offer a button to compare the same initial number of days. Selecting that option changes the dates explicitly. Product contribution analysis uses the union of products in both periods and treats absent members as zero. Five displayed contributors plus all remaining products reconcile to the total revenue change. These are numerical contributions, not proof of external causes.
