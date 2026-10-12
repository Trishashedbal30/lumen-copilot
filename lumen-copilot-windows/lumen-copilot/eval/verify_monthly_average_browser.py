"""Browser regression for above-average monthly totals and contextual follow-ups."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import time
from playwright.sync_api import sync_playwright
from eval.provenance import source_hash
ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--url',default='http://localhost:8001');ap.add_argument('--typos',action='store_true');a=ap.parse_args()
    oracle=json.loads((ROOT/'eval/reports/retail_oracle.json').read_text(encoding='utf-8'))
    results=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chromium')
        questions=[('synthetic','which moths revenue is more than avegare'),('retail','which moths revenue is more than avegare in 2011')] if a.typos else [('synthetic','in which month was the revenue more than average'),('retail','which months had revenue above average in 2011')]
        for dataset,text in questions:
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(a.url);page.wait_for_function('window.Lumen && document.querySelector("#board .widget")')
            if dataset=='retail':
                page.select_option('#datasetMode','retail');page.wait_for_function('Lumen.getState().page_id==="uci.sales.overview"')
            else:
                page.evaluate('async()=>{let s=Lumen.defaultState("sales.channels.mix");s.date_range={start:"2026-07-03",end:"2026-09-30",label:"Last 90 days"};await Lumen.setState(s)}')
            def ask(question):
                before=page.evaluate('window.__lumenTurns||0');started=time.perf_counter()
                with page.expect_response(lambda r:r.url.endswith('/api/chat') and r.request.method=='POST',timeout=120000) as observed:
                    page.fill('#input',question);page.press('#input','Enter')
                response=observed.value.json();page.wait_for_function(f'(window.__lumenTurns||0)>{before}',timeout=120000)
                last=page.evaluate('window.__lumenLast');state=page.evaluate('Lumen.getState()')
                assert last['verify'].startswith('Checked'),last
                return response,state,round((time.perf_counter()-started)*1000,1)
            r,state,latency=ask(text)
            assert state['grain']=='month' and state['compare']=='none'
            assert 'Months strictly above this average:' in r['reply']
            assert len(r['cards'][0]['series'])==2
            understanding=next(t for t in r['trace'] if t['node']=='understand')
            if a.typos:
                fixes=dict(understanding['slots']['typos_fixed']);assert fixes.get('moths')=='months' and fixes.get('avegare')=='average'
            mean=next(f for f in r['facts'] if f['kind']=='monthly_average')
            assert 'AVG(monthly_value)' in mean['sql']
            page.locator('[data-cite]').last.click();page.wait_for_function('Lumen.getState().grain==="month"')
            assert page.evaluate('Lumen.getState()')==state
            record={'understanding':understanding,'dataset':dataset,'question':text,'latency_ms':latency,'reply':r['reply'],'browser_state':state,'mean':mean,'verification':'browser applied state checked','evidence_link':True}
            if dataset=='retail':
                months=[f'2011-{i:02}' for i in range(1,12)]
                expected=sum(oracle['monthly'][m] for m in months)/11
                assert abs(mean['value']-expected)<.0001
                assert state['date_range']['end']=='2011-11-30'
                follow,follow_state,_=ask('what about France?')
                assert follow_state['filters']['country']==['France']
                fact=next(f for f in follow['facts'] if f['kind']=='monthly_average')
                expected=sum(oracle['month_country'].get(m,{}).get('France',0) for m in months)/11
                assert abs(fact['value']-expected)<.0001
                _,restored,_=ask('undo');assert restored==state
                record.update(independent_calculation=True,followup=True,undo=True)
            assert not errors
            page.screenshot(path=str(ROOT/'eval/reports'/('monthly_average_'+('typos_' if a.typos else '')+dataset+'.png')))
            results.append(record);page.close()
        browser.close()
    out={'generated_at':datetime.now(timezone.utc).isoformat(),'source_hash':source_hash(),'cases':results,'passed':len(results)}
    (ROOT/'eval/reports'/('monthly_average_typos_browser.json' if a.typos else 'monthly_average_browser.json')).write_text(json.dumps(out,indent=2),encoding='utf-8')
    print('Monthly-average browser checks passed: both datasets, evidence links, independent UCI numbers, France follow-up and undo.')
if __name__=='__main__':main()
