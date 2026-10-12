"""Browser checks for the three Olist destinations and existing dataset preservation."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from time import perf_counter
from playwright.sync_api import sync_playwright
from eval.provenance import source_hash
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--url',default='http://localhost:8002');a=ap.parse_args();rows=[]
 with sync_playwright() as pw:
  browser=pw.chromium.launch(channel='chromium')
  for width,height in [(1440,1000),(390,844)]:
   ctx=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce');page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(a.url);page.wait_for_function('window.Lumen && document.querySelector("#board .widget")')
   if width<760:page.click('#menuBtn')
   page.select_option('#datasetMode','olist');page.wait_for_function('Lumen.getState().page_id==="olist.sales.overview" && document.querySelector("#board").getAttribute("aria-busy")==="false"')
   if width<760:page.click('#navClose');page.click('#cpBtn')
   assert 'BRL' in page.locator('#board').inner_text()
   assert page.locator('#datasetMode').input_value()=='olist'
   assert page.evaluate('[...document.querySelectorAll("#tree a[data-pid]")].filter(a=>a.style.display!=="none").length')==3
   def ask(q):
    n=page.evaluate('window.__lumenTurns||0');start=perf_counter()
    with page.expect_response(lambda r:r.url.endswith('/api/chat') and r.request.method=='POST',timeout=120000):
     page.fill('#input',q);page.press('#input','Enter')
    page.wait_for_function(f'(window.__lumenTurns||0)>{n}',timeout=120000)
    last=page.evaluate('window.__lumenLast');state=page.evaluate('Lumen.getState()')
    rows.append({'viewport':width,'question':q,'destination':state['page_id'],'controls':state,'verification':last['verify'],'latency_ms':round((perf_counter()-start)*1000)})
    assert last['verify'].startswith('Checked');return state
   s=ask('Show monthly sales value for 2017');assert s['page_id']=='olist.sales.overview' and s['grain']=='month'
   s=ask('Top 5 states by late delivery rate in 2017');assert s['page_id']=='olist.delivery.overview' and s['top_n']==5
   s=ask('Compare review scores for late and on-time deliveries in 2017');assert s['page_id']=='olist.reviews.overview' and s['filters']['olist_delivery_status']==['Late','On time'] and s['compare']=='none'
   s=ask('What about SP?');assert s['filters']['br_state']==['SP']
   page.locator('[data-cite]').last.click();page.wait_for_function('document.querySelector("#board").getAttribute("aria-busy")==="false"');assert page.evaluate('Lumen.getState()')==s
   if width==1440:
    n=page.evaluate('window.__lumenTurns||0')
    with page.expect_response(lambda r:r.url.endswith('/api/chat') and r.request.method=='POST',timeout=120000):
     page.fill('#input','Save this view');page.press('#input','Enter')
    page.wait_for_function(f'(window.__lumenTurns||0)>{n}',timeout=120000)
    page.locator('[data-ok="1"]').last.click();page.wait_for_function('document.querySelector("#savedViews button")')
    assert page.evaluate('JSON.parse(localStorage.getItem("lumen_bookmarks"))[0].state')==s
    page.click('#resetBtn');page.wait_for_function('Lumen.getState().date_range.start!=="2017-01-01" && document.querySelector("#board").getAttribute("aria-busy")==="false"')
    page.locator('.saved-box > summary').click();page.locator('#savedViews button').first.click()
    page.wait_for_function('document.querySelector("#board").getAttribute("aria-busy")==="false"');assert page.evaluate('Lumen.getState()')==s
   page.screenshot(path=str(ROOT/f'eval/reports/olist_browser_{width}.png'),animations='disabled')
   if width<760:page.click('#cpClose');page.click('#menuBtn')
   page.select_option('#datasetMode','retail');page.wait_for_function('Lumen.getState().page_id==="uci.sales.overview" && document.querySelector("#board").getAttribute("aria-busy")==="false"');assert 'GBP' in page.locator('#board').inner_text()
   page.select_option('#datasetMode','synthetic');page.wait_for_function('Lumen.getState().page_id==="exec.dashboards.summary" && document.querySelector("#board").getAttribute("aria-busy")==="false"')
   assert not page.evaluate('document.documentElement.scrollWidth>innerWidth') and not errors
   ctx.close()
  browser.close()
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'source_hash':source_hash(),'scope':'Actual Chromium desktop and mobile; rules-mode server, real Olist import','cases':rows,'passed':len(rows),'dataset_switching':True,'evidence_links':True,'saved_view_reopen':True,'javascript_errors':[]}
 (ROOT/'eval/reports/olist_browser.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(f"Olist browser checks passed: {len(rows)} requests, 3 destinations, filters, evidence, dataset switching and no JS errors/overflow.")
if __name__=='__main__':main()
