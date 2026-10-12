"""One live-model browser task with a source-workbook numerical reference."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from eval.provenance import source_hash
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--url',default='http://localhost:8003');a=ap.parse_args()
 oracle=json.loads((ROOT/'eval/reports/retail_oracle.json').read_text(encoding='utf-8'))
 with sync_playwright() as pw:
  browser=pw.chromium.launch(channel='chromium');page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(a.url);page.wait_for_function('window.Lumen && document.querySelector("#board .widget")')
  page.select_option('#datasetMode','retail');page.wait_for_function('Lumen.getState().page_id==="uci.sales.overview"')
  question='Which month revenue is more than avg revenue in total in 2011'
  with page.expect_response(lambda r:r.url.endswith('/api/chat') and r.request.method=='POST',timeout=120000) as observed:
   page.fill('#input',question);page.press('#input','Enter')
  r=observed.value.json();page.wait_for_function('(window.__lumenTurns||0)>0',timeout=120000)
  understanding=next(t for t in r['trace'] if t['node']=='understand')
  state=page.evaluate('Lumen.getState()');verified=page.evaluate('window.__lumenLast.verify')
  expected=sum(oracle['monthly'][f'2011-{i:02}'] for i in range(1,12))/11
  fact=next((f for f in r.get('facts',[]) if f.get('kind')=='monthly_average'),{})
  checks={'actual_inference':understanding['model_request_status']=='succeeded' and understanding['source']=='llm','destination':state['page_id']=='uci.sales.overview','controls':state['grain']=='month' and state['compare']=='none' and state['date_range']['end']=='2011-11-30','independent_calculation':abs(fact.get('value',-1)-expected)<.005,'browser_verification':verified.startswith('Checked'),'javascript':not errors}
  if page.locator('[data-cite]').count():
   page.locator('[data-cite]').last.click();page.wait_for_function('(wanted)=>{const s=Lumen.getState();return s.page_id===wanted.page_id && s.top_n===wanted.top_n && s.date_range.start===wanted.date_range.start}',arg=state);assert page.evaluate('Lumen.getState()')==state;checks['evidence_link']=True
  else:checks['evidence_link']=False
  page.screenshot(path=str(ROOT/'eval/reports/groq_live_browser.png'))
  report={'generated_at':datetime.now(timezone.utc).isoformat(),'source_hash':source_hash(),'question':question,'checks':checks,'passed':all(checks.values()),'understanding':understanding,'browser_state':state,'verification':verified,'expected_average_gbp':expected,'actual_average_gbp':fact.get('value'),'latency_ms':r.get('latency_ms'),'reply':r['reply'],'javascript_errors':errors}
  (ROOT/'eval/reports/groq_live_browser.json').write_text(json.dumps(report,indent=2),encoding='utf-8');browser.close()
 print(json.dumps({'passed':report['passed'],'checks':checks,'model_status':understanding['model_request_status'],'latency_ms':report['latency_ms']},indent=2))
 raise SystemExit(0 if report['passed'] else 1)
if __name__=='__main__':main()
