# Dashboard interface refresh

The user interface emphasizes business navigation, view controls, readable metric cards and charts, and an embedded copilot. Framework names, raw execution traces and diagnostic navigation links are removed from ordinary use. Developer diagnostics remain available directly at /readiness, /eval and /graph.

Answers retain a concise indication of AI or built-in understanding, honest fallback notices, applied-state verification, evidence links and expandable calculation details. SQL is a nested optional disclosure. New chat resets conversation context while preserving the active view.

Synthetic and real data are visibly labelled. Navigation and suggested questions follow the selected dataset. Changing pages clears old charts immediately while the next view loads. Saved views and source information are expandable sidebar sections. Country charts scroll when many categories are plotted; product charts plot every returned category with a compact legend preview and an explicit explanation.

The layout supports desktop, laptop, tablet and phone widths. Copilot can be collapsed on desktop, and uses an overlay on smaller screens. Mobile navigation has a separate drawer; Escape and the backdrop close overlays.

## Executed checks

An isolated local server on port 8002 used rules mode so these results describe UI/backend behavior, not successful model inference. The existing environment settings and user server were preserved.

- Actual Chromium layout checks at 1440, 1280, 1024 and 390 pixels: both datasets, dataset-specific navigation, chat requests, applied-state verification, evidence links, source disclosure, new chat, panel controls, no horizontal document overflow and no JavaScript errors. All four sizes passed after final chart polish.
- Broad browser evaluation: 80/80 destinations, 80/80 applied states, all six multi-turn dialogues passed. Recorded median latency 1287 ms and 95th percentile 1612 ms. This run overlapped the final chart-only polish; the four-size layout check subsequently exercised the final frontend.
- Saved-view browser flow: decline, approve, reload and reopen exact state for both datasets passed.
- Separate fresh challenge browser suite: 3/3 passed. These are separate from the reused benchmark and are not an independent blind holdout.

Reports and screenshots are in eval/reports/. ui_layout.json records the final frontend source stamp. Existing backend tests were not rerun for this presentation-only refresh; the browser checks exercised existing API interactions. Live model inference and external platform connections were not retested for this UI change.

## Reproduce

Start the application with start.bat, then open the configured URL. For the current workspace it is http://localhost:8004. Use Ctrl+F5 to load the updated static files.

With a test server running, use:

```powershell
.\.venv\Scripts\python.exe -m eval.verify_ui_layout --url http://localhost:8002
.\.venv\Scripts\python.exe -m eval.verify_saved_views_browser --url http://localhost:8002
.\.venv\Scripts\python.exe -m eval.run_fresh_challenges --browser --url http://localhost:8002
.\.venv\Scripts\python.exe -m eval.run_e2e --url http://localhost:8002 --limit 80
```
