"""Product-layout browser checks: responsiveness, meaningful labels and real interactions."""
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
  for width,height in [(1440,1000),(1280,900),(1024,900),(390,844)]:
   ctx=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce');page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(a.url);page.wait_for_function('window.Lumen && document.querySelector("#board .widget") && document.querySelector("#board").getAttribute("aria-busy")==="false"')
   assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
   assert not page.locator('#officialSource').is_visible()
   page.screenshot(path=str(ROOT/f'eval/reports/ui_synthetic_{width}.png'),animations='disabled')
   if width<=760:page.click('#menuBtn')
   page.select_option('#datasetMode','retail');page.wait_for_function('Lumen.getState().page_id==="uci.sales.overview" && document.querySelector("#board").getAttribute("aria-busy")==="false"')
   if width<=760:page.click('#navClose')
   assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
   assert page.locator('#board').inner_text().find('GBP')>=0
   assert 'On-Time Delivery' not in page.locator('#board').inner_text()
   assert page.evaluate('[...document.querySelectorAll("#tree a")].filter(a=>a.style.display!=="none").length')==2
   visible=page.locator('body').inner_text()
   assert all(word not in visible for word in ['LangGraph','DuckDB','Judge checklist','App graph','configuration_only'])
   page.screenshot(path=str(ROOT/f'eval/reports/ui_retail_{width}.png'),animations='disabled')
   if width<=1100:page.click('#cpBtn')
   page.wait_for_function('document.querySelector("#log .starter")')
   assert '2011' in page.locator('.starter-list').inner_text()
   count=page.evaluate('window.__lumenTurns||0')
   with page.expect_response(lambda r:r.url.endswith('/api/chat') and r.request.method=='POST',timeout=120000) as observed:
    page.fill('#input','Which months had revenue more than avg in 2011?');page.press('#input','Enter')
   response=observed.value.json();page.wait_for_function(f'(window.__lumenTurns||0)>{count}',timeout=120000)
   assert page.evaluate('window.__lumenLast.verify').startswith('Checked')
   assert page.locator('.answer-status').last.is_visible()
   assert not page.locator('.action-details').last.get_attribute('open')
   assert 'LangGraph' not in page.locator('#log').inner_text()
   target=page.evaluate('Lumen.getState()')
   page.locator('[data-cite]').last.click();page.wait_for_function('document.querySelector("#board").getAttribute("aria-busy")==="false"')
   assert page.evaluate('Lumen.getState()')==target
   page.locator('.source-details > summary').last.click();assert page.locator('.facts').last.is_visible()
   page.screenshot(path=str(ROOT/f'eval/reports/ui_answer_{width}.png'),animations='disabled')
   page.click('#newChat');assert page.locator('.starter-list').is_visible()
   if width>1100:
    page.click('#cpClose');assert not page.locator('#copilot').is_visible();page.click('#cpBtn');assert page.locator('#copilot').is_visible()
   else:
    page.click('#cpClose');assert not page.locator('#copilot').is_visible()
    page.click('#cpBtn');assert page.locator('#copilot').is_visible()
    page.keyboard.press('Escape');assert not page.locator('#copilot').is_visible()
   assert not errors
   rows.append({'viewport':[width,height],'datasets_checked':['synthetic','retail'],'horizontal_overflow':False,'active_dataset_navigation':True,'technical_clutter_removed':True,'answer_verified':True,'evidence_link':True,'source_details':True,'new_chat':True,'panel_controls':True,'javascript_errors':errors})
   ctx.close()
  browser.close()
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'source_hash':source_hash(),'passed':len(rows),'scope':'Actual Chromium at desktop/laptop/tablet/mobile widths, dataset labels, requests, evidence and panel interactions','cases':rows}
 (ROOT/'eval/reports/ui_layout.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('UI checks passed at all four widths: both datasets, chat, evidence, panels and no horizontal overflow or JS errors.')
if __name__=='__main__':main()
