"""Independent original-workbook checks for newly exposed retail analyses."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import time
from eval.run_retail_checks import source_oracle
from eval.provenance import source_hash
ROOT=Path(__file__).resolve().parents[1]

def main():
 ap=argparse.ArgumentParser();ap.add_argument('files',nargs='+');args=ap.parse_args();started=time.perf_counter()
 oracle=source_oracle(args.files)
 from backend.semantic import engine
 from backend.semantic.layer import QuerySpec
 from backend.agent.analytics import FactBook,retail_contributors
 checks=[]
 def check(label,actual,expected,tolerance=.005):
  ok=(abs(actual-expected)<=tolerance) if isinstance(expected,(int,float)) and actual is not None else actual==expected
  checks.append({'check':label,'actual':actual,'independent_expected':expected,'ok':ok,'tolerance':tolerance})
 for year,qty in oracle['quantity_year'].items():
  start=max(year+'-01-01',oracle['date_start']);end=min(year+'-12-31',oracle['date_end'])
  revenue=sum(v for month,v in oracle['monthly'].items() if month.startswith(year))
  orders=oracle['orders_year'][year]
  for metric,expected in [('retail_orders',orders),('retail_quantity',qty),('retail_aov',revenue/orders)]:
   value,_=engine.scalar('retail',metric,start,end);check(year+' '+metric,value,expected)
  expected=sorted(oracle['customer_year'][year].items(),key=lambda x:(-x[1],x[0]))[:10]
  rows,_=engine.run_records(QuerySpec('retail',['revenue'],start,end,group_by=['customer_id'],sort='revenue',limit=10))
  check(year+' customer rank',[r['customer_id'] for r in rows],[r[0] for r in expected])
  for row,(member,amount) in zip(rows,expected):check(year+' customer '+member,row['revenue'],amount)
 def period(month):return {'start':month+'-01','end':month+('-30' if month.endswith('11') else '-31'),'label':month}
 current,previous='2011-11','2011-10';fb=FactBook()
 rows=retail_contributors(fb,{},period(current),period(previous),dim='retail_product')
 union=set(oracle['month_product'][current])|set(oracle['month_product'][previous])
 expected={member:oracle['month_product'][current].get(member,0)-oracle['month_product'][previous].get(member,0) for member in union}
 top=sorted(expected,key=lambda x:(-abs(expected[x]),x))[:5]
 check('product contributor order',[r['member'] for r in rows[:5]],top)
 for row in rows[:5]:check('product contribution '+row['member'],row['delta'],expected[row['member']])
 check('all product deltas reconcile',sum(r['delta'] for r in rows),oracle['monthly'][current]-oracle['monthly'][previous])
 check('displayed contributions plus remainder reconcile',sum(f['value'] for f in fb.facts),oracle['monthly'][current]-oracle['monthly'][previous])
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'source_hash':source_hash(),'source_files':oracle['sources'],
         'method':oracle['method'],'duration_seconds':round(time.perf_counter()-started,2),'checks':checks,'passed':sum(c['ok'] for c in checks),'total':len(checks)}
 (ROOT/'eval/reports/retail_extensions_independent.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(f"Independent retail extension checks: {report['passed']}/{report['total']}");print('Failures:',[c for c in checks if not c['ok']])
 raise SystemExit(0 if all(c['ok'] for c in checks) else 1)
if __name__=='__main__':main()
