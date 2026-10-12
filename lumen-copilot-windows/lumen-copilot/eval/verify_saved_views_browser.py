"""Actual save confirmation, persistence and reopening checks in both dataset modes."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from eval.provenance import source_hash
ROOT=Path(__file__).resolve().parents[1]

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--url',default='http://localhost:8002');a=ap.parse_args();rows=[]
 with sync_playwright() as pw:
  browser=pw.chromium.launch(channel='chromium')
  for dataset,question in [('synthetic','Top 5 cities by revenue in August 2026'),('retail','Top 5 countries by revenue in 2011')]:
   ctx=browser.new_context();page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(a.url);page.wait_for_function('window.Lumen && document.querySelector("#board .widget")')
   if dataset=='retail':
    page.select_option('#datasetMode','retail');page.wait_for_function('Lumen.getState().page_id==="uci.sales.overview"')
   def ask(text):
    count=page.evaluate('window.__lumenTurns||0')
    with page.expect_response(lambda r:r.url.endswith('/api/chat') and r.request.method=='POST',timeout=120000) as observed:
     page.fill('#input',text);page.press('#input','Enter')
    response=observed.value.json();page.wait_for_function(f'(window.__lumenTurns||0)>{count}',timeout=120000)
    return response
   r=ask(question);assert page.evaluate('window.__lumenLast.verify').startswith('Checked')
   expected=page.evaluate('Lumen.getState()')
   ask('Save this view');page.locator('[data-ok="0"]').last.click()
   page.wait_for_function('!document.querySelector("[data-ok]")')
   assert page.evaluate('JSON.parse(localStorage.getItem("lumen_bookmarks")||"[]").length')==0
   ask('Save this view');page.locator('[data-ok="1"]').last.click()
   page.wait_for_function('document.querySelector("#savedViews button")')
   saved=page.evaluate('JSON.parse(localStorage.getItem("lumen_bookmarks"))[0].state')
   assert saved==expected, {'expected':expected,'saved':saved}
   page.select_option('#datasetMode','synthetic')
   page.wait_for_function('Lumen.getState().page_id==="exec.dashboards.summary"')
   page.reload();page.wait_for_function('window.Lumen && document.querySelector("#savedViews button")')
   page.locator('.saved-box > summary').click()
   page.locator('#savedViews button').first.click()
   page.wait_for_function('(wanted)=>{const s=Lumen.getState();return s.page_id===wanted.page_id && s.top_n===wanted.top_n && s.date_range.start===wanted.date_range.start}',arg=expected)
   assert page.evaluate('Lumen.getState()')==expected, {'expected':expected,'actual':page.evaluate('Lumen.getState()')}
   assert page.input_value('#datasetMode')==dataset
   assert not errors
   rows.append({'dataset':dataset,'question':question,'decline_saved_nothing':True,'confirmation_saved':True,'persisted_after_reload':True,'restored_state':expected,'javascript_errors':errors,'understanding':next(t for t in r['trace'] if t['node']=='understand')})
   ctx.close()
  browser.close()
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'source_hash':source_hash(),'scope':'Real Chromium save confirmation, storage persistence, dataset selector and applied state','passed':len(rows),'cases':rows}
 (ROOT/'eval/reports/saved_views_browser.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print('Saved-view browser verification passed for both datasets (decline, confirm, reload, reopen, exact state, no JS errors).')
if __name__=='__main__':main()
