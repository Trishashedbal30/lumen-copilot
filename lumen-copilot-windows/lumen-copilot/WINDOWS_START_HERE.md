# Start on Windows

Latest: [11 October data-question audit](docs/DATA_QUESTION_AUDIT.md). Current checks: 73 tests, 68 separate data probes, 323/323 reused destinations/states, 94 independent UCI checks, 80/80 browser states/destinations and live Groq/browser evidence. Earlier snapshots below retain their historical scope. Current configured Windows URL: http://localhost:8004.

Use 64-bit Python 3.12. Run commands in the folder containing run.py, setup.bat, backend, frontend and data. The existing .venv here is Python 3.12.7 on Windows AMD64 and has been exercised in this session.

```powershell
cd 'C:\Users\ASUS\Downloads\lumen-copilot-windows\lumen-copilot'
.\setup.bat                  # installs dependencies, checks environment, starts app
# Later:
.\start.bat
```

Open http://localhost:8000. Keep the terminal open; stop with Ctrl+C. Both launchers use the project virtual environment directly and report nonzero failures. No activation-policy change is required. Port errors tell you to stop the other app or set PORT=8001 in .env.

## Ollama

[Official Windows installer](https://ollama.com/download/windows). Ollama is already installed/running here and qwen2.5:3b was present. lumen-qwen was created from those weights during this session.

On another laptop, after installation:

```powershell
ollama pull qwen2.5:3b
ollama create lumen-qwen -f Modelfile
Copy-Item .env.ollama.example .env
.\.venv\Scripts\python.exe doctor.py --llm
.\start.bat
```

Only run `ollama serve` if the installed Ollama app is not serving already. `ollama list` should include lumen-qwen. Configured endpoint: http://localhost:11434/v1; timeout: 60 seconds. The retrieved-page prompt and 8192-token model context reduce memory pressure. Initial cold large-context calls timed out; revised live checks succeeded. Warm the model before the presentation using doctor.py --llm.

Hybrid mode uses rules for known requests. Each turn reports **Understanding: rules/llm** and **Model request: not_requested/succeeded/failed_fallback_to_rules**, plus errors. The badge and `/api/health` model details describe configuration; only actual response counters/traces demonstrate inference. For model demonstration on each ordinary question:

```powershell
# Stop existing Lumen first.
$env:LUMEN_AGENT_MODE='llm'
.\start.bat
# In a later terminal or after stopping, remove the override:
Remove-Item Env:LUMEN_AGENT_MODE
```

Safety, unsupported requests and local controls remain deterministic. Set LUMEN_AGENT_MODE=rules in .env for a completely deterministic demo. Do not present rules latency as model latency.

## Real UCI data

The official workbook is already downloaded at data/uci_source/online_retail_II.xlsx and imported into data/uci_retail.duckdb. Select **UCI Online Retail II** above page search. Import report, row counts, coverage, exclusions and source links are visible in the sidebar.

If importing on another laptop, download the ZIP from [UCI's official page](https://archive.ics.uci.edu/dataset/502/online+retail+ii), extract the workbook, then stop Lumen and run:

```powershell
.\.venv\Scripts\python.exe -m backend.data.import_retail .\data\uci_source\online_retail_II.xlsx
# Or export both sheets as CSV:
.\.venv\Scripts\python.exe -m backend.data.import_retail .\year1.csv .\year2.csv
.\start.bat
```

Imports take several minutes for the million-row Excel file. Dates in ambiguous CSV numeric format default to UK day/month order; use --date-order monthfirst for US exports. ISO dates are preferred. Original Invoice/Price/Customer ID and InvoiceNo/UnitPrice/CustomerID aliases are supported. [Policy and scope](docs/REAL_DATA.md).

## Verify and rehearse

```powershell
.\.venv\Scripts\python.exe doctor.py --llm
.\.venv\Scripts\python.exe -m pytest -q
# Independent source-workbook check (several minutes):
.\.venv\Scripts\python.exe -m eval.run_retail_checks .\data\uci_source\online_retail_II.xlsx
# App must be running:
.\.venv\Scripts\python.exe -m eval.run_fresh_challenges --browser --url http://localhost:8000
```

Ask monthly revenue for 2011 → top 5 countries → compare two available months → France follow-up → evidence link and Sources → undo → save, confirm, refresh and reopen. December 2011 covers only nine days; it is explicitly partial. All amounts in this mode are GBP.

Troubleshooting: missing Python → install Python 3.12 with PATH and reopen terminal; invalid/broken .venv → stop the app, rename it to .venv_old and rerun setup; pip error → keep error text and retry after checking connection; missing model → run the pull/create commands above; blocked browser storage → saved views report failure and cannot persist; browser not opening → type the local URL manually. No paid API is required.
