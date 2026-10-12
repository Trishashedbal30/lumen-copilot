"""Small live-model sample for new retail questions; separate from rules evaluation."""
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
 for question in ['How many orders in 2011?','Who are the top 10 customers by revenue in 2011?','Compare revenue in October 2011 and November 2011 by product']:
  r=agent.handle(None,question,agent.planner.default_state('uci.sales.overview'))
  u=next(t for t in r['trace'] if t['node']=='understand')
  verified=bool(r.get('target_state')) and agent.verify(r['session_id'],r['turn_id'],r['target_state'])['ok']
  row={'question':question,'kind':r['kind'],'source':u['source'],'model_request_status':u['model_request_status'],
       'model_error':u.get('model_error'),'backend_verified':verified,'browser_verified':False,'latency_ms':r.get('latency_ms'),
       'destination':(r.get('target_state') or {}).get('page_id'),'reply':r['reply']}
  rows.append(row);print(json.dumps({k:v for k,v in row.items() if k not in ('reply','model_error')}),flush=True)
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'source_hash':source_hash(),'scope':'Three actual configured-model requests and backend state verification; no browser/model latency benchmark claim','cases':rows}
 (ROOT/'eval/reports/retail_extensions_live.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 raise SystemExit(0 if all(r['backend_verified'] for r in rows) else 1)
if __name__=='__main__':main()
