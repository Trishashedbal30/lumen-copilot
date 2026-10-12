# Fresh human challenges

`fresh_human_challenges.jsonl` is a separate corpus. The initial three cases are copied exactly from the project user's current task. They are human authored, but were already visible during implementation and are **not an independent holdout**. Reports are `fresh_human_backend.json` and `fresh_human_browser.json`; they never enter `latest.json` or the reused benchmark scores.

Ask classmates who have not seen the parser to add new cases. Record the author's name, original wording, intended dataset, and expected destination/controls before executing them. Keep disagreements and failures in the report. AI-authored smoke tests do not qualify as new human-written questions. Freeze the file before evaluation, retain its original copy, and label any tuning after evaluation.

Example structure (replace the wording and author with a real submission):

```json
{"id":"classmate-001","author":"Name of human author","origin":"Collected before evaluation","dataset":"retail","question":"Original human wording here","expected":{"page_id":"uci.sales.overview","filters":{"country":["France"]},"date_range":{"start":"2011-10-01","end":"2011-10-31"}}}
```

For unfamiliar calculations, implement an independent expected result before claiming calculation success. The supplied runner reports calculation as unscored when no independent expectation is defined. It supports frozen labels `monthly`, `country_rank`, `product_rank` and `last_two_complete_months` using the independent source-workbook oracle. Do not add them unless they match the submitted task.

```powershell
.\.venv\Scripts\python.exe -m eval.run_retail_checks .\data\uci_source\online_retail_II.xlsx
.\.venv\Scripts\python.exe -m eval.run_fresh_challenges
# Start Lumen on the matching port first:
.\.venv\Scripts\python.exe -m eval.run_fresh_challenges --browser --url http://localhost:8000
```

Each case records destination, controls, independent calculation correctness, verification scope/outcome, agent latency and total browser latency separately, plus understanding source and query evidence. A backend consistency check compares the intended state with supplied state; it is not proof of browser execution. Browser reports use a real Chromium session and the applied state after actions.
