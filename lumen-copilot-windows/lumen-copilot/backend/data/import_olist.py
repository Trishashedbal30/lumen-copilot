"""Import the official Olist ZIP or extracted CSV directory into its own DuckDB."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import zipfile
import numpy as np
import pandas as pd
import duckdb
ROOT=Path(__file__).resolve().parents[2]
SOURCE='https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce'
FILES={'orders':'olist_orders_dataset.csv','customers':'olist_customers_dataset.csv','items':'olist_order_items_dataset.csv',
       'payments':'olist_order_payments_dataset.csv','reviews':'olist_order_reviews_dataset.csv','products':'olist_products_dataset.csv',
       'sellers':'olist_sellers_dataset.csv','geolocation':'olist_geolocation_dataset.csv','category_translation':'product_category_name_translation.csv'}
REQUIRED={'orders':['order_id','customer_id','order_status','order_purchase_timestamp','order_delivered_customer_date','order_estimated_delivery_date'],
 'customers':['customer_id','customer_unique_id','customer_state','customer_city'], 'items':['order_id','order_item_id','price','freight_value'],
 'payments':['order_id','payment_sequential','payment_value'], 'reviews':['order_id','review_id','review_score']}

def load(source):
 source=Path(source);frames={};hashes={}
 archive=zipfile.ZipFile(source) if source.is_file() else None
 try:
  for key,name in FILES.items():
   if archive:
    matches=[n for n in archive.namelist() if Path(n).name==name]
    if not matches:
     if key in REQUIRED:raise ValueError('Missing required CSV: '+name)
     continue
    raw=archive.read(matches[0])
   else:
    path=source/name
    if not path.exists():
     if key in REQUIRED:raise ValueError('Missing required CSV: '+name)
     continue
    raw=path.read_bytes()
   from io import BytesIO
   frames[key]=pd.read_csv(BytesIO(raw),dtype=str)
   missing=set(REQUIRED.get(key,[]))-set(frames[key].columns)
   if missing:raise ValueError(name+' is missing '+', '.join(sorted(missing)))
   hashes[name]=hashlib.sha256(raw).hexdigest()
 finally:
  if archive:archive.close()
 return frames,hashes

def prepare(frames):
 counts={k:len(v) for k,v in frames.items()};exclusions={};clean={}
 for key,frame in frames.items():
  df=frame.copy()
  for col in df:df[col]=df[col].str.strip().replace('',pd.NA)
  before=len(df);df=df.drop_duplicates();exclusions[key+'_exact_duplicates']=before-len(df)
  clean[key]=df
 orders=clean['orders'].copy();customers=clean['customers'].copy()
 for key,df,cols in [('orders',orders,['order_id']),('customers',customers,['customer_id'])]:
  if df[cols].isna().any().any() or df.duplicated(cols).any():raise ValueError('Missing or conflicting primary keys in '+key)
 for col in ['order_purchase_timestamp','order_delivered_customer_date','order_estimated_delivery_date']:
  raw=orders[col];orders[col]=pd.to_datetime(raw,errors='coerce')
  exclusions['orders_invalid_'+col]=int((raw.notna()&orders[col].isna()).sum())
 good=orders.order_purchase_timestamp.notna()&orders.customer_id.notna()
 exclusions['orders_missing_purchase_or_customer']=int((~good).sum());orders=orders[good]
 customer=customers[['customer_id','customer_unique_id','customer_state','customer_city']].rename(columns={'customer_state':'br_state','customer_city':'br_city'})
 facts=orders.merge(customer,on='customer_id',how='left',validate='many_to_one')
 exclusions['orders_missing_customer_join']=int(facts.br_state.isna().sum())
 facts['br_state']=facts.br_state.fillna('Unknown');facts['br_city']=facts.br_city.fillna('Unknown')
 for key,columns in [('items',['price','freight_value']),('payments',['payment_value']),('reviews',['review_score'])]:
  df=clean[key].copy();valid=df.order_id.notna()
  for col in columns:
   df[col]=pd.to_numeric(df[col],errors='coerce');valid &= df[col].notna()&np.isfinite(df[col])
   valid &= df[col].between(1,5) if col=='review_score' else df[col]>=0
  if key in ('items','payments'):
   pk=['order_id','order_item_id' if key=='items' else 'payment_sequential']
   if df.duplicated(pk).any():raise ValueError('Conflicting primary keys in '+key)
  exclusions[key+'_invalid_values']=int((~valid).sum());df=df[valid]
  exclusions[key+'_orphan_rows']=int((~df.order_id.isin(orders.order_id)).sum())
  df=df[df.order_id.isin(orders.order_id)]
  if key=='items':agg=df.groupby('order_id').agg(sales_value=('price','sum'),freight_value=('freight_value','sum'),item_count=('order_id','size'))
  elif key=='payments':agg=df.groupby('order_id').agg(payment_value=('payment_value','sum'))
  else:agg=df.groupby('order_id').agg(review_score=('review_score','mean'),review_count=('review_score','size'))
  facts=facts.merge(agg,on='order_id',how='left',validate='one_to_one')
 facts['date']=facts.order_purchase_timestamp.dt.date
 delivered=facts.order_delivered_customer_date;estimate=facts.order_estimated_delivery_date
 comparable=(facts.order_status=='delivered')&delivered.notna()&estimate.notna()&(delivered>=facts.order_purchase_timestamp)
 # Calendar promised date: delivery at any time on that date is on time.
 facts['late_flag']=np.where(comparable,(delivered.dt.normalize()>estimate.dt.normalize()).astype(float),np.nan)
 facts['delivery_days']=np.where(comparable,(delivered-facts.order_purchase_timestamp).dt.total_seconds()/86400,np.nan)
 facts['olist_delivery_status']=np.where(comparable,np.where(facts.late_flag==1,'Late','On time'),'Unavailable')
 facts['order_status']=facts.order_status.fillna('Unknown')
 views={'olist_sales':facts[(facts.order_status=='delivered')&facts.sales_value.notna()],
        'olist_delivery':facts[facts.late_flag.notna()],
        'olist_reviews':facts[(facts.order_status=='delivered')&facts.review_score.notna()&facts.late_flag.notna()]}
 coverage={}
 for view,df in views.items():
  if df.empty:raise ValueError('No eligible orders for '+view)
  coverage[view]={'date_start':str(df.date.min()),'date_end':str(df.date.max()),'eligible_orders':len(df)}
 report={'dataset':'Olist Brazilian E-Commerce / real imported data','source_url':SOURCE,'license':'CC BY-NC-SA 4.0 (Kaggle dataset card)',
         'currency':'BRL','generated_at':datetime.now(timezone.utc).isoformat(),'source_rows':counts,'exclusions':exclusions,
         'imported_orders':len(facts),'coverage':coverage,'date_start':str(facts.date.min()),'date_end':str(facts.date.max()),
         'cleaning_policy':'Exact duplicate source rows removed; conflicting required primary keys rejected. Invalid numeric component rows and orphan components excluded. Orders require valid purchase date and customer ID; missing geography is Unknown. Sales includes delivered orders with item prices, excluding freight. Delivery requires delivered status, valid actual/estimated dates and nonnegative elapsed delivery time. Reviews include these comparable delivered orders with valid scores 1-5; multiple review rows are averaged per order. Missing review/delivery values excluded only from applicable views. All dates are purchase-date cohorts.'}
 return facts,report

def import_data(source,db=ROOT/'data/olist.duckdb'):
 frames,hashes=load(source);facts,report=prepare(frames);report['source_hashes']=hashes
 db=Path(db);db.parent.mkdir(parents=True,exist_ok=True);tmp=db.with_name(db.stem+'.importing.duckdb')
 if tmp.exists():tmp.unlink()
 try:
  with duckdb.connect(str(tmp)) as con:
   for key,frame in frames.items():
    con.register('source_frame',frame);con.execute('CREATE TABLE olist_raw_'+key+' AS SELECT * FROM source_frame');con.unregister('source_frame')
   con.register('fact_frame',facts);con.execute('CREATE TABLE olist_order_facts AS SELECT * FROM fact_frame')
   con.execute('CREATE TABLE olist_import_manifest(report VARCHAR)');con.execute('INSERT INTO olist_import_manifest VALUES (?)',[json.dumps(report)])
  os.replace(tmp,db)
 except Exception:
  if tmp.exists():tmp.unlink()
  raise
 return report

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('source');ap.add_argument('--db',default=str(ROOT/'data/olist.duckdb'));a=ap.parse_args()
 report=import_data(a.source,a.db);print(json.dumps(report,indent=2))
if __name__=='__main__':main()
