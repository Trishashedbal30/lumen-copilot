"""Agent-authored supported-data audit; separate from human challenges and reused corpus.
Run with --mode rules or --mode llm (loads .env without displaying secrets).
References use handwritten SQL against raw tables, never the QuerySpec compiler.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import time
ROOT=Path(__file__).resolve().parents[1]
# Frozen reference expressions; deliberately independent of compile_query and analytics.
REFERENCES={
 'sales': {'revenue':'SUM(revenue)','orders':'SUM(orders)','units':'SUM(units)','aov':'SUM(revenue)/NULLIF(SUM(orders),0)','gross_margin':'SUM(revenue-cost)','margin_pct':'100*SUM(revenue-cost)/NULLIF(SUM(revenue),0)','discount':'SUM(discount)','discount_pct':'100*SUM(discount)/NULLIF(SUM(revenue+discount),0)','returns':'SUM(returns)','return_rate':'100*SUM(returns)/NULLIF(SUM(orders),0)'},
 'delivery':{'shipments':'SUM(shipments)','on_time_pct':'100*SUM(on_time)/NULLIF(SUM(shipments),0)','late_shipments':'SUM(late)','avg_delay_mins':'SUM(delay_mins)/NULLIF(SUM(late),0)'},
 'inventory':{'stockout_days':'SUM(stockout)','in_stock_rate':'100*(1-SUM(stockout)/NULLIF(COUNT(*),0))','avg_stock_units':'SUM(stock_units)/NULLIF(COUNT(DISTINCT date),0)','inbound_units':'SUM(inbound_units)'},
 'marketing':{'spend':'SUM(spend)','impressions':'SUM(impressions)','clicks':'SUM(clicks)','conversions':'SUM(conversions)','ctr':'100*SUM(clicks)/NULLIF(SUM(impressions),0)','cpa':'SUM(spend)/NULLIF(SUM(conversions),0)','roas':'SUM(attributed_revenue)/NULLIF(SUM(spend),0)','attributed_revenue':'SUM(attributed_revenue)'},
 'support':{'tickets':'SUM(tickets)','csat':'SUM(csat_sum)/NULLIF(SUM(csat_responses),0)','avg_resolution_hrs':'SUM(resolution_hrs)/NULLIF(SUM(tickets),0)'},
 'customers':{'active_customers':'SUM(active_customers)/NULLIF(COUNT(DISTINCT date),0)','new_customers':'SUM(new_customers)','churned_customers':'SUM(churned_customers)','churn_rate':'100*SUM(churned_customers)/NULLIF(SUM(active_customers),0)','retention_rate':'100-100*SUM(churned_customers)/NULLIF(SUM(active_customers),0)'},
 'retail':{'revenue':'SUM(revenue)'}}
TABLES={'sales':'sales_daily','delivery':'delivery_daily','inventory':'inventory_daily','marketing':'marketing_daily','support':'support_daily','customers':'customers_monthly','retail':'uci_sales'}

def cases(meta):
 from backend.semantic.layer import VIEWS
 rows=[]
 for view,metrics in REFERENCES.items():
  if view=='retail':continue
  for metric in metrics:
   phrase=VIEWS[view]['metrics'][metric]['synonyms'][0]
   if metric=='returns':phrase='number of returns'
   if metric=='churn_rate':phrase='churn rate'
   rows.append(dict(id=view+'.'+metric,question=f'What is {phrase} in August 2026?',view=view,metric=metric,dates=['2026-08-01','2026-08-31'],analysis='kpi'))
 def add(id,q,view='sales',**expected):rows.append(dict(id=id,question=q,view=view,metric='revenue',**expected))
 add('sales.top','Top 5 cities by revenue in August 2026',dates=['2026-08-01','2026-08-31'],analysis='rank',top_n=5,sort={'field':'revenue','dir':'desc'},group='city')
 add('sales.bottom','Bottom 3 products by revenue in August 2026',dates=['2026-08-01','2026-08-31'],analysis='rank',top_n=3,sort={'field':'revenue','dir':'asc'},group='product')
 add('sales.filter','Show South revenue in August 2026',dates=['2026-08-01','2026-08-31'],filters={'region':['South']})
 add('sales.multi','Show South online Electronics revenue in August 2026',dates=['2026-08-01','2026-08-31'],filters={'region':['South'],'channel':['Online Store'],'category':['Electronics']})
 add('sales.period','Compare revenue in August 2026 versus July 2026',analysis='compare_periods',dates=['2026-08-01','2026-08-31'],comparison=['2026-07-01','2026-07-31'])
 add('sales.entities','Compare North versus South revenue in August 2026',analysis='compare_entities',dates=['2026-08-01','2026-08-31'])
 add('sales.trend','Show monthly revenue in 2026',analysis='trend',grain='month',dates=['2026-01-01','2026-09-30'])
 add('sales.peak','Which month had the highest revenue in 2026',analysis='trend',grain='month',dates=['2026-01-01','2026-09-30'])
 add('sales.median','What is median revenue in August 2026?',kind='clarify')
 add('sales.forecast','Predict revenue for next month',kind='clarify')
 add('sales.avg','Which month revenue is more than avg revenue in total',analysis='monthly_average',grain='month')
 add('sales.typo','which moths revenue is more than avegare in 2026',analysis='monthly_average',grain='month',dates=['2026-01-01','2026-09-30'])
 if 'retail' in VIEWS:
  kw=dict(view='retail')
  add('retail.peak','Which month had highest revenue in 2011?',**kw,analysis='trend',grain='month',dates=['2011-01-01','2011-12-09'])
  add('retail.total','What is total revenue in 2011?',**kw,dates=['2011-01-01','2011-12-09'],analysis='kpi')
  add('retail.monthly','Show monthly revenue for 2011',**kw,dates=['2011-01-01','2011-12-09'],analysis='trend',grain='month')
  add('retail.top','Top 5 countries by revenue in 2011',**kw,dates=['2011-01-01','2011-12-09'],analysis='rank',top_n=5,group='country',sort={'field':'revenue','dir':'desc'})
  add('retail.products','Top 5 products by revenue in 2011',**kw,dates=['2011-01-01','2011-12-09'],analysis='rank',top_n=5,group='retail_product')
  add('retail.bottom','Bottom 3 countries by revenue in 2011',**kw,dates=['2011-01-01','2011-12-09'],analysis='rank',top_n=3,group='country',sort={'field':'revenue','dir':'asc'})
  add('retail.uk','Show revenue for UK in 2011',**kw,dates=['2011-01-01','2011-12-09'],filters={'country':['United Kingdom']})
  add('retail.period','Compare revenue in two available months',**kw,analysis='compare_periods',dates=['2011-11-01','2011-11-30'],comparison=['2011-10-01','2011-10-31'])
  add('retail.explicit','Compare revenue in November 2011 versus October 2011',**kw,analysis='compare_periods',dates=['2011-11-01','2011-11-30'],comparison=['2011-10-01','2011-10-31'])
  add('retail.mean','Which months had revenue more than avg in 2011?',**kw,analysis='monthly_average',grain='month',dates=['2011-01-01','2011-11-30'])
  add('retail.below','Which months had revenue below average in 2011?',**kw,analysis='monthly_average',grain='month',dates=['2011-01-01','2011-11-30'])
  add('retail.why','Why did revenue change in November 2011 compared with October 2011?',**kw,analysis='drivers',dates=['2011-11-01','2011-11-30'],comparison=['2011-10-01','2011-10-31'])
  for id,q in [('count','How many countries in 2011?'),('net','What is net revenue in 2011?'),('median','What is median revenue in 2011?'),('price','What was unit price in 2011?'),('profit','What was profit in 2011?'),('orders','How many orders in 2011?'),('future','Show revenue in 2026'),('unknown','Show revenue for Atlantis in 2011'),('stock','Show revenue for StockCode NOTREAL in 2011')]:
   add('retail.'+id,q,**kw,kind='clarify')
 rows.append(dict(id='guard.write',question='Delete the sales table',view='sales',kind='refuse'))
 return rows

def numeric_checks(resp):
 from backend.semantic import engine
 checks=[]
 for f in resp.get('facts',[]):
  if f.get('kind')!='value' or f.get('value') is None:continue
  if 'date_trunc' in f.get('sql','').lower() and not f.get('period_start'):continue
  view,metric=f['view'],f['metric']
  if view not in REFERENCES or metric not in REFERENCES[view]:continue
  rng=f['range'];params=[rng['start'],rng['end']];where='date BETWEEN ? AND ?'
  for key,values in f['filters'].items():
   where+=' AND "'+key+'" IN ('+','.join('?' for _ in values)+')';params.extend(values)
  # Trend facts describe a single bucket while recording the overall selected range.
  if f.get('period_start'):
   import pandas as pd
   start=f['period_start'];grain=resp['target_state']['grain']
   end=(pd.Timestamp(start)+({'day':pd.DateOffset(days=1),'week':pd.DateOffset(weeks=1),'month':pd.DateOffset(months=1),'quarter':pd.DateOffset(months=3),'year':pd.DateOffset(years=1)}[grain])-pd.Timedelta(days=1)).date().isoformat()
   params[0]=max(params[0],start);params[1]=min(params[1],end)
  sql=f'SELECT {REFERENCES[view][metric]} FROM {TABLES[view]} WHERE {where}'
  expected=engine.connection(view).execute(sql,params).fetchone()[0]
  ok=expected is not None and abs(expected-f['value'])<=max(.005,abs(expected)*1e-9)
  checks.append(dict(fact=f['id'],ok=ok,actual=f['value'],expected=expected,sql=sql,parameters=params))
 return checks

def evaluate(case,r,meta,verification,mode):
 target=r.get('target_state') or {};view=meta['pages'].get(target.get('page_id'),{}).get('view')
 checks={'kind':r['kind']==case.get('kind','act')}
 if case.get('kind','act')=='act':
  checks['destination_view']=view==case['view']
  if case.get('metric'):checks['metric']=any(f.get('metric')==case['metric'] and f.get('view')==case['view'] for f in r.get('facts',[]))
  analysis=next((t.get('analysis') for t in r['trace'] if t['node']=='retrieve+plan'),None)
  if case.get('analysis'):checks['analysis']=analysis==case['analysis']
  for key in ('top_n','grain','sort','filters'):
   if key in case:checks[key]=target.get(key)==case[key]
  for key,label in [('date_range','dates'),('compare_range','comparison')]:
   if case.get(label):checks[label]=[target.get(key,{}).get(k) for k in ('start','end')]==case[label]
  if case.get('group'):checks['dimension']=any(case['group'] in f.get('filters',{}) for f in r.get('facts',[]))
  checks['verification']=verification['ok']
  numeric=numeric_checks(r)
  if analysis=='trend' and not numeric:
   from backend.semantic import engine
   card=next(c for c in r['cards'] if c['type']=='line')
   dr=target['date_range'];grain=target['grain']
   expected=engine.connection(view).execute(f"SELECT date_trunc('{grain}',date),{REFERENCES[view][case['metric']]} FROM {TABLES[view]} WHERE date BETWEEN ? AND ? GROUP BY 1 ORDER BY 1",[dr['start'],dr['end']]).fetchall()
   actual=card['series'][0]['values']
   numeric=[dict(ok=len(actual)==len(expected) and all(abs(a-e[1])<.005 for a,e in zip(actual,expected)),expected=[v for _,v in expected],actual=actual)]
  if analysis=='rank':
   from backend.semantic import engine
   dim=case['group'];dr=target['date_range'];direction=(target.get('sort') or {}).get('dir','desc')
   expected=engine.connection(view).execute(f'SELECT "{dim}",{REFERENCES[view][case["metric"]]} FROM {TABLES[view]} WHERE date BETWEEN ? AND ? GROUP BY 1 ORDER BY 2 {direction},1 ASC LIMIT ?',[dr['start'],dr['end'],case['top_n']]).fetchall()
   card=next(c for c in r['cards'] if c['type']=='bar')
   numeric.append(dict(check='ranking membership, order and values',ok=card['labels']==[m for m,v in expected] and len(card['series'][0]['values'])==len(expected) and all(abs(a-v)<.005 for a,(_,v) in zip(card['series'][0]['values'],expected)),expected=expected,actual=card['labels']))
  if analysis=='monthly_average':
   from backend.semantic import engine
   import pandas as pd
   dr=target['date_range'];params=[dr['start'],dr['end']];where='date BETWEEN ? AND ?'
   for key,values in target['filters'].items():
    where+=' AND "'+key+'" IN ('+','.join('?' for _ in values)+')';params.extend(values)
   values=engine.connection(view).execute(f"SELECT strftime(date,'%Y-%m'),{REFERENCES[view][case['metric']]} FROM {TABLES[view]} WHERE {where} GROUP BY 1",params).fetchall()
   periods=pd.period_range(dr['start'],dr['end'],freq='M');expected=sum(v for _,v in values)/len(periods)
   fact=next(f for f in r['facts'] if f['kind']=='monthly_average')
   numeric.append(dict(check='monthly arithmetic mean including zero months',ok=abs(fact['value']-expected)<.005,actual=fact['value'],expected=expected))
  checks['calculation']=bool(numeric) and all(c['ok'] for c in numeric)
  checks['evidence']=bool(r.get('facts')) and all(f.get('sql') and f.get('metric_definition') and f.get('dataset') for f in r['facts'])
 else:numeric=[]
 understanding=next((t for t in r['trace'] if t['node']=='understand'),{})
 return dict(id=case['id'],question=case['question'],expected=case,passed=all(checks.values()),checks=checks,
  understanding=understanding,model_success=understanding.get('model_request_status')=='succeeded',
  target_state=target,reply=r['reply'],numeric=numeric,verification=verification,latency_ms=r.get('latency_ms'))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['rules','llm'],default='rules');ap.add_argument('--ids',nargs='+');ap.add_argument('--delay',type=float,default=1);ap.add_argument('--output');a=ap.parse_args()
 from run import load_env
 load_env();os.environ['LUMEN_AGENT_MODE']=a.mode
 from backend.main import AGENT
 from backend.agent.controller import Agent
 from backend.agent import llm
 from eval.provenance import source_hash
 if a.mode=='llm' and not llm.configured():raise SystemExit('Model API key/configuration missing; no live requests made.')
 rows=[]
 for case in cases(AGENT.meta):
  if a.ids and case['id'] not in a.ids:continue
  agent=Agent(AGENT.meta)
  page=next(pid for pid,p in agent.meta['pages'].items() if p['view']==case['view'] and not p.get('presets'))
  state=agent.planner.default_state(page)
  try:
   r=agent.handle(None,case['question'],state)
   v=agent.verify(r['session_id'],r['turn_id'],r.get('target_state') or state) if r.get('target_state') else {'ok':True,'scope':'no action expected'}
   row=evaluate(case,r,agent.meta,{**v,'scope':'backend consistency; browser not run'},a.mode)
  except Exception as exc:row=dict(id=case['id'],question=case['question'],passed=False,error=str(exc)[:200])
  rows.append(row);print(case['id'], 'PASS' if row['passed'] else 'FAIL', [k for k,v in row.get('checks',{}).items() if not v],row.get('understanding',{}).get('model_request_status','error'),flush=True)
  if a.mode=='llm':time.sleep(a.delay)
 report=dict(generated_at=datetime.now(timezone.utc).isoformat(),source_hash=source_hash(),author='Agent-authored regression audit; not fresh human holdout',mode=a.mode,configuration=llm.configuration(),n=len(rows),passed=sum(r['passed'] for r in rows),successful_model_requests=sum(r.get('model_success',False) for r in rows),cases=rows)
 (ROOT/'eval/reports'/(a.output or f'data_audit_{a.mode}.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
 print('RESULT',report['passed'],'/',report['n'],'live model successes',report['successful_model_requests'],flush=True)
 raise SystemExit(0 if report['passed']==report['n'] else 1)
if __name__=='__main__':main()
