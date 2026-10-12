"""Registry for the optional official Olist import and three metadata-backed views."""
from datetime import date
import json
import os
from pathlib import Path
import duckdb
from backend import catalog as C
DB=Path(os.environ.get('LUMEN_OLIST_DB',Path(__file__).resolve().parents[1]/'data/olist.duckdb'))
REPORT=None
VIEWSPEC={
 'olist_sales':('Sales','olist.sales.overview',['olist_revenue','olist_orders','olist_aov'],['br_state','br_city'],"order_status='delivered' AND sales_value IS NOT NULL"),
 'olist_delivery':('Delivery','olist.delivery.overview',['olist_late_rate','olist_delivery_days','olist_orders'],['br_state','olist_delivery_status'],'late_flag IS NOT NULL'),
 'olist_reviews':('Reviews','olist.reviews.overview',['olist_review_score','olist_reviewed_orders','olist_low_review_rate'],['olist_delivery_status','br_state'],"order_status='delivered' AND late_flag IS NOT NULL AND review_score IS NOT NULL"),
}
METRICS={
 'olist_revenue':('Sales value (BRL)','SUM(sales_value)','brl',True,'up','Delivered-order item prices summed, excluding freight, payments and cancelled orders. This is merchandise sales value, not profit.',['olist sales value','olist revenue']),
 'olist_orders':('Eligible orders','COUNT(DISTINCT order_id)','retail_int',False,'up','Distinct orders eligible for this view and purchase-date cohort.',['olist orders']),
 'olist_aov':('Average order value (BRL)','SUM(sales_value)/NULLIF(COUNT(DISTINCT order_id),0)','brl',False,'up','Delivered merchandise sales value divided by distinct eligible orders; freight excluded.',['olist average order value']),
 'olist_late_rate':('Late delivery rate','100*AVG(late_flag)','pct',False,'down','Percentage of comparable delivered orders delivered after the promised calendar date. Missing delivery dates and non-delivered orders excluded.',['olist late delivery rate']),
 'olist_delivery_days':('Average delivery time','AVG(delivery_days)','days',False,'down','Mean purchase-to-customer-delivery elapsed days among comparable delivered orders with nonnegative durations.',['olist delivery time']),
 'olist_review_score':('Average review score','AVG(review_score)','rating',False,'up','Mean per-order review score among comparable delivered and reviewed orders. Multiple valid review rows first averaged within order.',['olist review score']),
 'olist_reviewed_orders':('Reviewed orders','COUNT(DISTINCT order_id)','retail_int',False,'up','Distinct comparable delivered orders with at least one valid review score.',['olist reviewed orders']),
 'olist_low_review_rate':('Low review rate','100*AVG(CASE WHEN review_score<=2 THEN 1.0 ELSE 0.0 END)','pct',False,'down','Percentage of eligible reviewed orders with mean review score at most 2.',['olist low review rate']),
}

def register(views):
 global REPORT
 if not DB.is_file():return
 with duckdb.connect(str(DB),read_only=True) as con:
  REPORT=json.loads(con.execute('SELECT report FROM olist_import_manifest').fetchone()[0])
  for field in ('br_state','br_city','olist_delivery_status','order_status'):
   C.DIMENSION_VALUES[field]=[r[0] for r in con.execute(f'SELECT DISTINCT "{field}" FROM olist_order_facts WHERE "{field}" IS NOT NULL ORDER BY 1').fetchall()]
 C.DIMENSION_LABELS.update(br_state='Brazilian state',br_city='Brazilian city',olist_delivery_status='Delivery status',order_status='Order status')
 C.DIMENSION_SYNONYMS.update(br_state=['brazilian state','brazilian states'],br_city=['brazilian city','brazilian cities'],olist_delivery_status=['delivery status'])
 for view,(label,pid,metrics,dims,predicate) in VIEWSPEC.items():
  views[view]={'label':'Olist '+label,'table':'olist_order_facts','min_grain':'day','dataset':REPORT['dataset'],
      'description':REPORT['cleaning_policy'],'dims':['br_state','br_city','olist_delivery_status','order_status'],
      'default_metric':metrics[0],'currency':'BRL','base_predicate':predicate,
      'metrics':{m:dict(zip(['label','sql','fmt','additive','good','definition','synonyms'],METRICS[m])) for m in metrics}}

def bounds(view):
 coverage=REPORT['coverage'][view]
 return date.fromisoformat(coverage['date_start']),date.fromisoformat(coverage['date_end'])

def augment_metadata(meta):
 meta.setdefault('datasets',{})['olist']={'available':bool(REPORT),**(REPORT or {'source_url':'https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce','instructions':'python -m backend.data.import_olist data/olist_source.zip'})}
 if not REPORT:return meta
 from backend.data.generate_metadata import Builder
 from backend.semantic.layer import VIEWS
 b=Builder();d=b.directory('olist','Olist Brazil / real','shopping-cart','Brazilian e-commerce orders, delivery and reviews')
 for view,(label,pid,metrics,dims,predicate) in VIEWSPEC.items():
  sub=b.subdir(d,label.lower(),label)
  p=b.page(d,sub,'overview','Olist '+label,view,REPORT['cleaning_policy'],metrics,dims,
           synonyms=['olist '+label.lower(),'brazil '+label.lower()],date_preset='all_time')
  if view!='olist_sales':
   for widget in p['widgets']:
    if widget['type']=='donut':
     widget['type']='bar';widget['title']=VIEWS[view]['metrics'][widget['metric']]['label']+' by '+C.DIMENSION_LABELS[widget['dimension']]
  p['default_state']['compare']='none';lo,hi=bounds(view)
  p['data_bounds']={'start':lo.isoformat(),'end':hi.isoformat()};p['dataset']=REPORT['dataset']
  meta['data_views'][view]={'label':VIEWS[view]['label'],'description':REPORT['cleaning_policy'],
     'dimensions':[{'field':f,'label':C.DIMENSION_LABELS[f],'values':C.DIMENSION_VALUES[f]} for f in VIEWS[view]['dims']],
     'metrics':[{'name':m,'label':VIEWS[view]['metrics'][m]['label'],'format':VIEWS[view]['metrics'][m]['fmt'],'additive':VIEWS[view]['metrics'][m]['additive'],'good_direction':VIEWS[view]['metrics'][m]['good']} for m in metrics],
     'default_metric':metrics[0],'min_grain':'day'}
 meta['pages'].update(b.pages);meta['directories'].extend(b.dirs);meta['routes'].update({p['route']:p['id'] for p in b.pages.values()})
 return meta
