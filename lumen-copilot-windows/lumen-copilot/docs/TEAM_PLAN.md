# Two-day plan for a team of six

The build is done. The remaining risk is that the judges see a demo only one person can explain. Give everyone a real job.

| Person | Owns | Day 1 | Day 2 |
|---|---|---|---|
| 1. Demo lead | The 5-minute demo | Run `docs/DEMO_SCRIPT.md` five times on the demo laptop and time it | Two full rehearsals with the team asking hostile questions; record the backup video |
| 2. Pitch deck | 6–8 slides | Problem → architecture (README diagram) → "LLM proposes, metadata disposes" → results table → limitations | Insert screenshots from `/eval` and `/graph`; final pass with person 1 |
| 3. Blind-set author | Credibility of the numbers | Without reading the code, write **50 new requests** a real business user would type, labelled like `eval/handwritten.py` (BLIND list) | Run `python -m eval.run_eval --splits blind` once, record the first-run number honestly, and fix only clear bugs afterwards |
| 4. LLM mode | Optional upgrade | Get a free Groq key; set `.env` to `LUMEN_AGENT_MODE=hybrid`; test 30 odd phrasings and note which ones the rules miss and the LLM rescues | Decide on stage whether to demo LLM mode (only if it is reliable on venue Wi-Fi) |
| 5. Q&A and domain | Judge questions | Learn `docs/JUDGE_QA.md`; read the analytics in `backend/agent/analytics.py` well enough to explain contribution analysis on a whiteboard | Prepare one slide on the five planted anomalies and why ground truth matters |
| 6. QA and polish | Nothing breaks | Click through all 8 directories and run every example prompt; log anything odd | Test on the actual demo laptop and projector resolution; check offline (Wi-Fi off) |

**Rules for the last 24 hours:** no new features. Fix only what the rehearsals or the blind set expose, and re-run `python -m eval.run_eval` after every fix.
