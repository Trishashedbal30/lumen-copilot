"""Independent CSV/Decimal Olist oracle; does not use importer or SQL for expectations."""
from collections import defaultdict
import csv
from datetime import datetime,timezone
from decimal import Decimal
from io import TextIOWrapper
import json
from pathlib import Path
import zipfile
from eval.provenance import source_hash
ROOT=Path(__file__).resolve().parents[1]
def main():
 with zipfile.ZipFile(ROOT/'data/olist_source.zip') as z:
  def read(name):return list(csv.DictReader(TextIOWrapper(z.open(name),encoding='utf-8-sig')))
  orders=read('olist_orders_dataset.csv');customers={r['customer_id']:r for r in read('olist_customers_dataset.csv')}
  items=read('olist_order_items_dataset.csv');payments=read('olist_order_payments_dataset.csv');reviews=read('olist_order_reviews_dataset.csv')
 price=defaultdict(Decimal);payment=defaultdict(Decimal);scores=defaultdict(list)
 for r in items:price[r['order_id']]+=Decimal(r['price'])
 for r in payments:payment[r['order_id']]+=Decimal(r['payment_value'])
 for r in reviews:scores[r['order_id']].append(float(r['review_score']))
 sales=[];delivery=[];reviewed=[]
 for r in orders:
  dt=datetime.fromisoformat(r['order_purchase_timestamp']);oid=r['order_id'];state=customers[r['customer_id']]['customer_state']
  row={'id':oid,'date':dt.date().isoformat(),'year':str(dt.year),'state':state,'sales':float(price[oid])}
  if r['order_status']=='delivered' and oid in price:sales.append(row.copy())
  if r['order_status']=='delivered' and r['order_delivered_customer_date'] and r['order_estimated_delivery_date']:
   actual=datetime.fromisoformat(r['order_delivered_customer_date']);estimated=datetime.fromisoformat(r['order_estimated_delivery_date'])
   if actual>=dt:
    row.update(late=float(actual.date()>estimated.date()),days=(actual-dt).total_seconds()/86400)
    delivery.append(row.copy())
    if scores[oid]:row['score']=sum(scores[oid])/len(scores[oid]);reviewed.append(row.copy())
 from backend.semantic import engine
 from backend.olist import REPORT
 from backend.semantic.layer import QuerySpec
 checks=[]
 def check(name,actual,expected,tol=.0002):
  ok=abs(actual-expected)<=tol if isinstance(expected,(float,int)) and actual is not None else actual==expected
  checks.append({'check':name,'actual':actual,'independent_expected':expected,'ok':ok,'tolerance':tol})
 check('source order count',REPORT['imported_orders'],len(orders),0)
 for view,rows in [('olist_sales',sales),('olist_delivery',delivery),('olist_reviews',reviewed)]:
  check(view+' eligible orders',REPORT['coverage'][view]['eligible_orders'],len(rows),0)
  check(view+' coverage start',REPORT['coverage'][view]['date_start'],min(r['date'] for r in rows))
  check(view+' coverage end',REPORT['coverage'][view]['date_end'],max(r['date'] for r in rows))
  for year in ['2017','2018']:
   selected=[r for r in rows if r['year']==year]
   if view=='olist_sales':metrics={'olist_revenue':sum(r['sales'] for r in selected),'olist_orders':len(selected),'olist_aov':sum(r['sales'] for r in selected)/len(selected)}
   elif view=='olist_delivery':metrics={'olist_orders':len(selected),'olist_late_rate':100*sum(r['late'] for r in selected)/len(selected),'olist_delivery_days':sum(r['days'] for r in selected)/len(selected)}
   else:metrics={'olist_reviewed_orders':len(selected),'olist_review_score':sum(r['score'] for r in selected)/len(selected),'olist_low_review_rate':100*sum(r['score']<=2 for r in selected)/len(selected)}
   for metric,value in metrics.items():
    actual,_=engine.scalar(view,metric,year+'-01-01',year+'-12-31');check(year+' '+metric,actual,value,.005 if metric=='olist_revenue' else .0002)
 grouped=defaultdict(list)
 for r in delivery:
  if r['year']=='2017':grouped[r['state']].append(r['late'])
 ranking=sorted([(s,100*sum(v)/len(v)) for s,v in grouped.items()],key=lambda x:(-x[1],x[0]))[:5]
 rows,_=engine.run_records(QuerySpec('olist_delivery',['olist_late_rate'],'2017-01-01','2017-12-31',group_by=['br_state'],sort='olist_late_rate',limit=5))
 check('late-delivery state ranking',[r['br_state'] for r in rows],[r[0] for r in ranking])
 for row,(state,value) in zip(rows,ranking):check('late rate '+state,row['olist_late_rate'],value)
 for late,label in [(1,'Late'),(0,'On time')]:
  subset=[r['score'] for r in reviewed if r['year']=='2017' and r['late']==late]
  actual,_=engine.scalar('olist_reviews','olist_review_score','2017-01-01','2017-12-31',{'olist_delivery_status':[label]})
  check(label+' review association',actual,sum(subset)/len(subset))
 current=sum(r['sales'] for r in sales if r['date'].startswith('2017-11'));previous=sum(r['sales'] for r in sales if r['date'].startswith('2017-10'))
 a,_=engine.scalar('olist_sales','olist_revenue','2017-11-01','2017-11-30');b,_=engine.scalar('olist_sales','olist_revenue','2017-10-01','2017-10-31');check('November-October sales delta',a-b,current-previous,.005)
 with engine.connection('olist_sales').cursor() as cur:
  count,distinct,payments_total,review_count=cur.execute('SELECT COUNT(*),COUNT(DISTINCT order_id),SUM(payment_value),SUM(review_count) FROM olist_order_facts').fetchone()
 check('one fact per order',count,distinct,0);check('payment aggregate not multiplied',payments_total,float(sum(payment.values())),.005);check('review rows not multiplied',review_count,len(reviews),0)
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'source_hash':source_hash(),'method':'Original official ZIP, csv.DictReader, Decimal price aggregation and independent order iteration. No importer or SQL for expected values.','checks':checks,'passed':sum(c['ok'] for c in checks),'total':len(checks)}
 (ROOT/'eval/reports/olist_independent.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(f"Olist independent checks: {report['passed']}/{report['total']}");print('Failures:',[c for c in checks if not c['ok']]);raise SystemExit(0 if all(c['ok'] for c in checks) else 1)
if __name__=='__main__':main()
