"""Actual configured-model Olist samples, separate from deterministic browser checks."""
from run import load_env
load_env()
import os
os.environ['LUMEN_AGENT_MODE']='llm'
from datetime import datetime,timezone
import json
from pathlib import Path
from backend.main import AGENT
from backend.agent.controller import Agent
from eval.provenance import source_hash
ROOT=Path(__file__).resolve().parents[1]
def main():
 agent=Agent(AGENT.meta);rows=[]
 for question,pid in [('Show monthly sales value for 2017','olist.sales.overview'),('Top 5 states by late delivery rate in 2017','olist.delivery.overview'),('Compare review scores for late and on-time deliveries in 2017','olist.reviews.overview')]:
  r=agent.handle(None,question,agent.planner.default_state('olist.sales.overview'))
  u=next(t for t in r['trace'] if t['node']=='understand');s=r.get('target_state')
  row={'question':question,'kind':r['kind'],'expected_destination':pid,'destination':s.get('page_id') if s else None,
       'source':u['source'],'model_request_status':u['model_request_status'],'model_error':u.get('model_error'),
       'backend_verified':bool(s) and agent.verify(r['session_id'],r['turn_id'],s)['ok'],'browser_verified':False,
       'latency_ms':r.get('latency_ms'),'reply':r['reply']}
  rows.append(row);print(json.dumps({k:v for k,v in row.items() if k not in ('reply','model_error')}),flush=True)
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'source_hash':source_hash(),'scope':'Three live configured-model samples with backend state verification. Separate from rules-mode browser checks.','cases':rows}
 (ROOT/'eval/reports/olist_live.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 raise SystemExit(0 if all(r['backend_verified'] and r['destination']==r['expected_destination'] for r in rows) else 1)
if __name__=='__main__':main()
