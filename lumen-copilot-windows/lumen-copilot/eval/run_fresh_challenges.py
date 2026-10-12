"""Fresh human task runner; never merges results into the reused benchmark."""
import argparse
from contextlib import ExitStack
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import time
ROOT=Path(__file__).resolve().parents[1]

def calculation_check(response,expected,oracle):
    kind=expected.get('calculation')
    if not kind: return None,'No independent numeric expectation frozen for this case.'
    year=expected.get('year','2011')
    if kind=='monthly':
        wanted={m:v for m,v in oracle['monthly'].items() if m.startswith(year+'-')}
        actual={f['period_start'][:7]:f['value'] for f in response.get('facts',[]) if f.get('period_start')}
        return set(actual)==set(wanted) and all(abs(actual[m]-v)<.005 for m,v in wanted.items()),{'expected':wanted,'actual':actual}
    if kind in ('country_rank','product_rank'):
        dim='country_year' if kind=='country_rank' else 'product_year'
        wanted=sorted(oracle[dim][year].items(),key=lambda x:(-x[1],x[0]))[:expected.get('top_n',5)]
        card=next((c for c in response.get('cards',[]) if c.get('type')=='bar'),{})
        labels=card.get('labels',[]);values=(card.get('series') or [{}])[0].get('values',[])
        return labels==[m for m,v in wanted] and len(values)==len(wanted) and all(abs(a-b)<.005 for a,(_,b) in zip(values,wanted)),{'expected':wanted,'actual':list(zip(labels,values))}
    if kind=='last_two_complete_months':
        import pandas as pd
        months=[m for m in oracle['monthly'] if m+'-01'>=oracle['date_start'] and pd.Period(m).end_time.date().isoformat()<=oracle['date_end']]
        latest=months[-2:]
        wanted={m:oracle['monthly'][m] for m in latest}
        actual={f['range']['start'][:7]:f['value'] for f in response.get('facts',[]) if f.get('kind')=='value' and not f.get('filters')}
        return all(m in actual and abs(actual[m]-v)<.005 for m,v in wanted.items()),{'expected':wanted,'actual':actual,'expected_delta':wanted[latest[-1]]-wanted[latest[-2]]}
    return None,'Unsupported frozen calculation label; add an independent reference check.'

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--questions',default=str(ROOT/'eval'/'fresh_human_challenges.jsonl'))
    ap.add_argument('--browser',action='store_true');ap.add_argument('--url',default='http://localhost:8001')
    a=ap.parse_args()
    cases=[json.loads(line) for line in Path(a.questions).read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    oracle_path=ROOT/'eval'/'reports'/'retail_oracle.json'
    if not oracle_path.is_file(): ap.exit(1,'Run eval.run_retail_checks on the source workbook first.\n')
    oracle=json.loads(oracle_path.read_text(encoding='utf-8'))
    rows=[]
    with ExitStack() as stack:
        if a.browser:
            from playwright.sync_api import sync_playwright
            pw=stack.enter_context(sync_playwright());browser=pw.chromium.launch(channel='chromium');stack.callback(browser.close)
        else:
            from run import load_env
            load_env()
            from backend.main import AGENT
        for case in cases:
            if not case.get('author'): raise ValueError('Human challenge must name its author/source.')
            started=time.perf_counter();expected=case.get('expected',{})
            if a.browser:
                ctx=browser.new_context(viewport={'width':1440,'height':900});page=ctx.new_page()
                page.goto(a.url);page.wait_for_function('window.Lumen && document.querySelector("#board .widget")')
                page.select_option('#datasetMode','retail');page.wait_for_function('Lumen.getState().page_id==="uci.sales.overview" && Lumen.getState().date_range.start')
                with page.expect_response(lambda r:r.url.endswith('/api/chat') and r.request.method=='POST',timeout=120000) as observed:
                    page.fill('#input',case['question']);page.press('#input','Enter')
                response=observed.value.json();page.wait_for_function('(window.__lumenTurns || 0)>0',timeout=120000)
                applied=page.evaluate('Lumen.getState()');last=page.evaluate('window.__lumenLast')
                verification={'scope':'browser applied state, independently exercised by Playwright','ok':last['verify'].startswith('Checked'),'detail':last['verify']}
                page.screenshot(path=str(ROOT/'eval'/'reports'/('fresh_'+case['id']+'.png')))
                ctx.close()
            else:
                state=AGENT.planner.default_state('uci.sales.overview')
                response=AGENT.handle(None,case['question'],state);applied=response.get('target_state') or {}
                result=AGENT.verify(response['session_id'],response['turn_id'],applied)
                verification={'scope':'backend consistency with intended state; browser not executed','ok':result['ok'],'detail':result['diff']}
            destination={'expected':expected.get('page_id'),'actual':applied.get('page_id'),'ok':applied.get('page_id')==expected.get('page_id')}
            controls={k:{'expected':v,'actual':applied.get(k),'ok':applied.get(k)==v} for k,v in expected.items() if k in ('grain','top_n','sort','compare','filters','date_range','compare_range')}
            if expected.get('year'):
                year=expected['year'];want={'start':max(year+'-01-01',oracle['date_start']),'end':min(year+'-12-31',oracle['date_end'])}
                actual=applied.get('date_range',{});controls['dates']={'expected':want,'actual':actual,'ok':all(actual.get(k)==v for k,v in want.items())}
            if expected.get('calculation')=='last_two_complete_months':
                import pandas as pd
                complete=[m for m in oracle['monthly'] if m+'-01'>=oracle['date_start'] and pd.Period(m).end_time.date().isoformat()<=oracle['date_end']]
                current,previous=complete[-1],complete[-2]
                for key,month in [('date_range',current),('compare_range',previous)]:
                    want={'start':month+'-01','end':pd.Period(month).end_time.date().isoformat()};actual=applied.get(key) or {}
                    controls[key]={'expected':want,'actual':actual,'ok':all(actual.get(k)==v for k,v in want.items())}
            numeric_ok,details=calculation_check(response,expected,oracle)
            rows.append({'id':case['id'],'author':case['author'],'origin':case.get('origin'),'question':case['question'],
                'kind':response['kind'],'destination':destination,'controls':controls,'calculation':{'ok':numeric_ok,'details':details,'method':oracle['method']},
                'verification':verification,'latency':{'agent_ms':response.get('latency_ms'),'total_ms':round((time.perf_counter()-started)*1000,1),'browser':a.browser},
                'understanding':[t for t in response.get('trace',[]) if t['node']=='understand'],'evidence':response.get('facts',[]),'reply':response['reply']})
    passed=lambda r:r['destination']['ok'] and all(c['ok'] for c in r['controls'].values()) and r['calculation']['ok'] is True and r['verification']['ok'] is True
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'corpus':'Human authored task requirements / additional submitted challenges, separate from reused benchmark',
            'independent_holdout':False,'n':len(rows),'passed':sum(passed(r) for r in rows),'browser':a.browser,'cases':rows}
    out=ROOT/'eval'/'reports'/('fresh_human_browser.json' if a.browser else 'fresh_human_backend.json')
    out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'},indent=2))
    print('Failures:',[r['id'] for r in rows if not passed(r)])
    raise SystemExit(0 if all(passed(r) for r in rows) else 1)
if __name__=='__main__':main()
