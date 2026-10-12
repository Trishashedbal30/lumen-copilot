# No-code integration: optional Baserow sales-table adapter

The hackathon problem requires application metadata and business data. Its dataset guidance explicitly permits synthetic/sample tenants. Lumen already demonstrates metadata-driven navigation, widgets, filters and actions in its local application, backed by synthetic DuckDB and genuine UCI sales. Another database is not required for the local demonstration.

For an external no-code data source, Baserow is the first supported adapter. Its official [database API documentation](https://baserow.io/user-docs/database-api) describes field schemas, named-field row retrieval, database tokens and pagination (up to 200 rows/page). [NocoDB's API documentation](https://nocodb.com/docs/product-docs/developer-resources/rest-apis) is another option; a NocoDB connector is not implemented in this workspace. Do not claim arbitrary database or external application control.

## What is implemented and tested

`backend/connectors/baserow.py` reads field metadata and every paginated row from a supplied Baserow table containing actual UCI transactions. It validates required column aliases before downloading rows, checks total counts and unique platform row IDs, rejects incomplete/mutating responses, and exports a CSV plus a timestamped provenance report. Optional import uses the existing validated UCI cleaning and dedicated DuckDB tables. Platform row IDs are excluded from business duplicate detection. Tokens are read from an environment variable, never saved in CSV/provenance, and API operations are GET-only. Remote connections require HTTPS; localhost HTTP is supported. Schema/permission/pagination errors preserve an existing CSV.

Ten tests exercise the connector against a local HTTP API fixture, including authentication failures, repeated IDs, incomplete pages, changing row counts, unsupported configuration, independently known revenue, and persisted provenance. These are contract tests with artificial temporary fixtures, not a live Baserow deployment.

No live platform account/API token was supplied. Docker CLI is installed on this laptop, but its engine did not respond during the audit. A live Baserow instance, external UI navigation, dashboard/widget metadata discovery, external browser control, platform write-back, and arbitrary business metrics remain unverified/unsupported. Lumen's own app UI is browser-verified separately.

## Optional live connection steps

1. Use a Baserow account or an existing self-hosted instance. Follow its official installation/account instructions. Do not spend the presentation setup period provisioning another database if the local demo is ready.
2. Import a CSV exported from the actual UCI workbook into a Baserow table. A subset is acceptable for integration rehearsal if it is labelled as a subset; it does not inherit the full-workbook benchmark totals. Preserve Invoice/InvoiceNo, StockCode, Quantity, InvoiceDate, Price/UnitPrice, Country; Description and Customer ID/CustomerID are optional. Use scalar text/date/number fields. Dates should be unambiguous ISO timestamps. Linked/select objects require an explicit mapping and are rejected by this adapter.
3. In Baserow, open the table's API Docs, note its table ID, and create a database token with only read permission for that table. Cloud API base is `https://api.baserow.io`; self-hosted base is the instance URL. Never paste the token into chat or commit it.
4. In PowerShell, from this project, run the following. Enter the token interactively so it is not placed in command history:

```powershell
$secureBaserowToken = Read-Host 'Baserow read-only token' -AsSecureString
$env:BASEROW_TOKEN = [System.Net.NetworkCredential]::new('', $secureBaserowToken).Password
# Replace 12345 with the actual UCI table ID. This only writes a new snapshot:
.\.venv\Scripts\python.exe -m backend.connectors.baserow --url https://api.baserow.io --table 12345 --source-uci --output .\data\connectors\baserow_uci.csv
Remove-Item Env:BASEROW_TOKEN
```

5. Inspect the CSV and `.provenance.json` sidecar. The adapter never follows the returned `next` URL with credentials; it constructs pages on the selected server. Pause table edits while snapshotting: count/unique-ID checks cannot detect same-count content edits and the API does not provide transaction isolation.
6. To activate the fetched table, stop Lumen first. Repeat the connector command with `--import-db .\data\uci_retail.duckdb`, keeping the environment token set until it finishes. The original workbook and synthetic DB stay available. Restart with `.\start.bat`; `/api/datasets` exposes connector provenance, actual coverage and cleaning exclusions. Treat the active data as a dated snapshot, not a live query/write-through connection.
7. Run source-based independent checks on the fetched CSV and re-run the separate browser challenges, adjusting frozen expected dates/months to the subset when necessary. Old full-workbook numerical reports do not certify changed data.

To restore the original full dataset, stop Lumen and run:

```powershell
.\.venv\Scripts\python.exe -m backend.data.import_retail .\data\uci_source\online_retail_II.xlsx
.\start.bat
```

The no-code connection is optional for tomorrow. The reliable demonstration uses the already-imported original workbook. A live external connection needs a real endpoint/table/token before it can be honestly marked verified.
