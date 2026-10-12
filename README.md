# Lumen Copilot

A context-aware application assistant for navigating business dashboards and analyzing data through natural language.

Lumen uses application metadata to choose a page, configure supported controls, calculate results and present evidence. It checks the applied page, filters, dates and sorting before completing an answer.

## Capabilities

- Navigate pages and reports using natural-language requests.
- Apply filters, date ranges, sorting, time grain and top-N controls.
- Analyze trends, period comparisons, rankings and numerical contributors.
- Ask clarification questions for ambiguous or unsupported requests.
- Follow up on an analysis, undo actions and save views in the browser.
- Inspect metric definitions, dataset scope, filters, dates and SQL evidence.
- See whether rules or an LLM understood a request, including model errors and fallback status.

## Datasets

| Workspace | Data | Supported analysis | Currency |
| --- | --- | --- | --- |
| Sahyadri Retail | Synthetic business demonstration with 209 metadata-defined pages | Sales and operational dashboards, navigation, filtering and comparisons | INR |
| UCI Online Retail II | Historical retail invoice lines | Revenue, orders, quantity, average order value, country/product/customer rankings and comparisons | GBP |
| Olist Brazil | Historical Brazilian e-commerce records | Sales, delivery performance and review-score comparisons | BRL |

Each workspace is visibly labelled and uses a separate DuckDB database. Real datasets require an import; generated demonstration records are kept separate.

UCI revenue is positive invoice-line quantity multiplied by unit price, excluding cancellations, returns, invalid required values and exact duplicates. It is not net revenue after returns. Olist sales exclude freight and non-delivered orders. Delivery and review calculations use their documented eligible order cohorts.

Partial months are identified in the interface. Above-average monthly revenue uses complete calendar-month totals, including zero-activity months. Explanations identify numerical contributors; external causes require supporting evidence.

Dataset sources and definitions: [UCI Online Retail II](docs/REAL_DATA.md) and [Olist Brazil](docs/OLIST_DATA.md).

## Run on Windows

Install 64-bit Python 3.12, then run:

```powershell
git clone https://github.com/HackFest-2026/Team-5A.7.git
cd Team-5A.7
.\setup.bat
.\start.bat
```

Open the URL printed by the launcher. Stop the server with `Ctrl+C`.

Setup installs dependencies into the project virtual environment and creates the synthetic demo data before running diagnostics. API keys, virtual environments, imported databases and downloaded datasets are excluded from Git.

See [Windows setup and troubleshooting](WINDOWS_START_HERE.md) for details.

## Model configuration

Lumen supports rules-only understanding, hybrid rules/LLM understanding and LLM mode. Local inference uses Ollama; an optional Groq configuration is also supported.

For Ollama, install Ollama and prepare the model:

```powershell
ollama pull qwen2.5:3b
ollama create lumen-qwen -f Modelfile
```

Use `.env.ollama.example` as your local `.env` configuration template. Keep API keys only in `.env`; `.env.example` documents the other configuration options.

```powershell
.\.venv\Scripts\python.exe doctor.py --llm
.\start.bat
```

The interface reports actual model request status separately from configuration. `/api/health` exposes request, response and error counts. Rules fallback is shown when a model request fails.

## Import real datasets

Download the official files using the [UCI instructions](docs/REAL_DATA.md) and [Olist instructions](docs/OLIST_DATA.md). Stop Lumen before importing:

```powershell
.\.venv\Scripts\python.exe -m backend.data.import_retail .\data\uci_source\online_retail_II.xlsx
.\.venv\Scripts\python.exe -m backend.data.import_olist .\data\olist_source.zip
.\start.bat
```

The UCI importer accepts the original Excel workbook or CSV exports. Import reports record row counts, date coverage, cleaning exclusions and source attribution. Select an imported dataset from the workspace selector.

## Example requests

**Synthetic retail**

- Show South revenue for August.
- Top 5 cities by revenue last quarter.
- What about North?

**UCI Online Retail II**

- Show monthly revenue for 2011.
- Which months had revenue above average in 2011?
- Who are the top 10 customers by revenue in 2011?
- Compare revenue in October 2011 and November 2011.

**Olist Brazil**

- Show monthly sales value for 2017.
- Top 5 states by late delivery rate in 2017.
- Compare review scores for late and on-time deliveries in 2017.

Follow an analysis with `undo` or `save this view`. Relative dates use the active dataset's reference date.

## Architecture

| Component | Purpose |
| --- | --- |
| FastAPI and Python | Backend endpoints and application services |
| LangGraph | Stateful understanding, planning, validation, execution and response workflow |
| Application metadata graph | Page hierarchy, widgets, controls and relationships |
| BM25 and TF-IDF retrieval | Find relevant pages and components |
| DuckDB | Dataset storage and analytical SQL execution |
| Ollama / optional Groq | Model-based intent and slot understanding |
| HTML, CSS, JavaScript and Chart.js | Dashboard, charts and embedded copilot |
| Pytest and Playwright | Backend tests and browser verification |

An optional read-only Baserow adapter imports table/schema snapshots. Connection instructions are in [No-code integration](docs/NO_CODE_INTEGRATION.md).

## Validation

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m eval.run_eval
.\.venv\Scripts\python.exe -m playwright install chromium
# Run the app first; use the URL printed by the launcher.
.\.venv\Scripts\python.exe -m eval.run_e2e --url http://localhost:8000
```

Dataset checks and browser checks require their corresponding data and runtime. Evaluation reports distinguish backend correctness, model inference and browser verification. Recorded results include source snapshots and evaluation scope; regression cases are not an independent unseen benchmark. See [verification details](docs/VERIFICATION_REPORT.md) and [evaluation protocol](eval/FRESH_CHALLENGES.md).

## Scope

Lumen is a single-tenant local application. Chat and undo state live in server memory; saved views persist in the same browser and origin. Authentication, role-based access, external-platform UI control and write-back are outside the current scope. The Baserow adapter requires a configured endpoint and credentials for live use.

## Acknowledgements

See [external projects, datasets and development assistance](ACKNOWLEDGEMENTS.md) for source attribution and licence details. Bundled library and font licence texts are included in [third-party notices](frontend/vendor/licenses/).
