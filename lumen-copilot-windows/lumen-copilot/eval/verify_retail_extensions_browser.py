"""Actual Chromium verification of new retail controls, choices and evidence."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from time import perf_counter
from playwright.sync_api import sync_playwright
from eval.provenance import source_hash
ROOT=Path(__file__).resolve().parents[1]

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--url',default='http://localhost:8002');a=ap.parse_args();checks=[]
 with sync_playwright() as pw:
  browser=pw.chromium.launch(channel='chromium');ctx=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce');page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(a.url);page.wait_for_function('window.Lumen && document.querySelector("#board .widget")')
  page.select_option('#datasetMode','retail');page.wait_for_function('Lumen.getState().page_id==="uci.sales.overview" && document.querySelector("#board").getAttribute("aria-busy")==="false"')
  assert page.locator('.data-warning').is_visible()
  def request(text=None,choice=None):
   n=page.evaluate('window.__lumenTurns||0');t=perf_counter()
   with page.expect_response(lambda r:r.url.endswith('/api/chat') and r.request.method=='POST',timeout=120000) as observed:
    if choice:page.locator('.sugg button').filter(has_text=choice).last.click()
    else:page.fill('#input',text);page.press('#input','Enter')
   r=observed.value.json();page.wait_for_function(f'(window.__lumenTurns||0)>{n}',timeout=120000)
   checks.append({'question':text or choice,'kind':r['kind'],'destination':(r.get('target_state') or {}).get('page_id'),
                 'controls':r.get('target_state'),'verified_on_screen':page.evaluate('window.__lumenLast.verify') if r['kind']=='act' else 'no actions',
                 'latency_ms':round((perf_counter()-t)*1000),'calculation_evidence':bool(r['facts'])})
   if r['kind']=='act':assert page.evaluate('window.__lumenLast.verify').startswith('Checked')
   return r
  r=request('Show the best products in 2011');assert r['kind']=='clarify' and len(r['suggestions'])==3
  r=request(choice='Quantity sold');assert r['facts'][0]['metric']=='retail_quantity'
  for question,metric in [('How many orders in November 2011?','retail_orders'),('What was average order value in November 2011?','retail_aov')]:
   r=request(question);assert r['facts'][0]['metric']==metric
  r=request('Who are the top 10 customers by revenue in 2011?');assert r['target_state']['page_id']=='uci.sales.customers' and r['target_state']['top_n']==10
  state=page.evaluate('Lumen.getState()');page.locator('[data-cite]').last.click();page.wait_for_function('document.querySelector("#board").getAttribute("aria-busy")==="false"');assert page.evaluate('Lumen.getState()')==state
  r=request('Show revenue for customer 14646 in 2011');assert r['target_state']['filters']['customer_id']==['14646']
  r=request('Compare revenue in November 2011 and December 2011');assert 'Incomplete month' in r['reply']
  r=request(choice='Compare first 9 days');assert r['target_state']['date_range']['end'].endswith('-09') and r['target_state']['compare_range']['end'].endswith('-09')
  r=request('Compare revenue in October 2011 and November 2011')
  r=request('Which products contributed most to the change?');assert r['analysis']['dimension']=='retail_product' and r['cards'][-1]['type']=='bar'
  assert all(x['sql'] and x['metric_definition'] for x in r['facts'])
  page.locator('.source-details > summary').last.click();assert page.locator('.facts').last.is_visible()
  page.screenshot(path=str(ROOT/'eval/reports/retail_extensions_browser.png'),animations='disabled')
  assert not errors;assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
  browser.close()
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'source_hash':source_hash(),'scope':'Actual Chromium, rules-mode server; does not prove live model inference','checks':checks,'passed':len(checks),'javascript_errors':errors}
 (ROOT/'eval/reports/retail_extensions_browser.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(f"Retail browser checks passed: {len(checks)} requests, choices, customer filter, evidence and partial-period controls.")
if __name__=='__main__':main()
