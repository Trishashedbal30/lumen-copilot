"""Independent Decimal/Pandas oracle from the source files, separate from importer and semantic SQL."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import time
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]

def source_oracle(paths, dayfirst=True):
    """Does not call import normalization, cleaning, query compiler or DuckDB for expected values."""
    pieces=[];sources=[]
    aliases={'Invoice':'invoice','InvoiceNo':'invoice','StockCode':'product','Description':'description',
             'Quantity':'quantity','Qty':'quantity','InvoiceDate':'date','Invoice Date':'date','Date':'date',
             'Price':'price','UnitPrice':'price','Unit Price':'price',
             'Customer ID':'customer','CustomerID':'customer','Customer_ID':'customer','Country':'country'}
    keys={re.sub('[^a-z0-9]','',k.lower()):v for k,v in aliases.items()}
    for filename in paths:
        path=Path(filename)
        print(f'Reading independent source: {path.name}',flush=True)
        frames=pd.read_excel(path,sheet_name=None,dtype=object) if path.suffix.lower() in ('.xlsx','.xls') else {'CSV':pd.read_csv(path,dtype=str,encoding='utf-8-sig',sep=None,engine='python')}
        sources.append({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        for frame in frames.values():
            frame=frame.rename(columns={c:keys.get(re.sub('[^a-z0-9]','',str(c).lower().lstrip('\ufeff')),c) for c in frame.columns})
            for name in ('description','customer'):
                if name not in frame: frame[name]=None
            pieces.append(frame[['invoice','product','description','quantity','date','price','customer','country']])
    raw=pd.concat(pieces,ignore_index=True)
    for key in ('invoice','product','description','customer','country'):
        raw[key]=raw[key].astype('string').str.strip().replace('',pd.NA)
    unique=~raw.duplicated(keep='first')
    quantity=pd.to_numeric(raw.quantity,errors='coerce')
    price=pd.to_numeric(raw.price,errors='coerce')
    dates=pd.to_datetime(raw.date,errors='coerce',format='mixed',dayfirst=dayfirst)
    eligible=(unique & dates.notna() & raw[['invoice','product','country']].notna().all(axis=1)
              & ~raw.invoice.str.upper().str.startswith('C',na=False)
              & (quantity>0) & (price>0) & np.isfinite(quantity) & np.isfinite(price) & np.isfinite(quantity*price))
    monthly=defaultdict(Decimal);country_year=defaultdict(lambda:defaultdict(Decimal))
    product_year=defaultdict(lambda:defaultdict(Decimal));month_country=defaultdict(lambda:defaultdict(Decimal))
    customer_year=defaultdict(lambda:defaultdict(Decimal));month_product=defaultdict(lambda:defaultdict(Decimal))
    quantity_year=defaultdict(Decimal);invoice_year=defaultdict(set)
    total=Decimal(0);lo=None;hi=None
    # Decimal products and sums are independent of the runtime's floating-point SUM(revenue).
    for dt,q,p,country,product,invoice,customer in zip(dates[eligible],quantity[eligible],price[eligible],raw.country[eligible],raw['product'][eligible],raw.invoice[eligible],raw.customer[eligible]):
        amount=Decimal(str(q))*Decimal(str(p));month=dt.strftime('%Y-%m');year=str(dt.year)
        monthly[month]+=amount;country_year[year][country]+=amount;product_year[year][product]+=amount
        month_country[month][country]+=amount;total+=amount
        month_product[month][product]+=amount
        quantity_year[year]+=Decimal(str(q));invoice_year[year].add(invoice)
        if pd.notna(customer): customer_year[year][customer]+=amount
        date_=dt.date();lo=min(lo,date_) if lo else date_;hi=max(hi,date_) if hi else date_
    convert=lambda d:{k:float(v) for k,v in sorted(d.items())}
    return {'sources':sources,'source_rows':len(raw),'eligible_rows':int(eligible.sum()),'excluded_rows':int((~eligible).sum()),
            'date_start':lo.isoformat(),'date_end':hi.isoformat(),'total_gbp':float(total),'monthly':convert(monthly),
            'country_year':{y:convert(v) for y,v in country_year.items()},
            'product_year':{y:convert(v) for y,v in product_year.items()},
            'quantity_year':convert(quantity_year),'orders_year':{y:len(v) for y,v in invoice_year.items()},
            'customer_year':{y:convert(v) for y,v in customer_year.items()},
            'month_product':{m:convert(v) for m,v in month_product.items()},
            'month_country':{m:convert(v) for m,v in month_country.items()},
            'method':'Independent workbook/CSV parsing, boolean eligibility mask, Decimal quantity*price aggregation; no import helper or runtime SQL used for expected values.'}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('files',nargs='+')
    ap.add_argument('--date-order',choices=['dayfirst','monthfirst'],default='dayfirst');a=ap.parse_args()
    t0=time.perf_counter();oracle=source_oracle(a.files,a.date_order=='dayfirst')
    os.environ['LUMEN_AGENT_MODE']='rules'
    from backend.semantic import engine
    from backend.semantic.layer import QuerySpec
    from backend.datasets import REPORT
    if not REPORT: ap.exit(1,'Import retail data first.\n')
    checks=[]
    def compare(name,actual,expected,tolerance=.005):
        ok=actual is not None and abs(actual-expected)<=tolerance
        checks.append({'check':name,'actual':actual,'independent_expected':expected,'ok':ok,'tolerance_gbp':tolerance})
    compare('eligible row count',REPORT['imported_rows'],oracle['eligible_rows'],0)
    compare('excluded row count',REPORT['excluded_rows'],oracle['excluded_rows'],0)
    actual,sql=engine.scalar('retail','revenue',oracle['date_start'],oracle['date_end'])
    compare('all-time revenue',actual,oracle['total_gbp'])
    rows,_=engine.run_records(QuerySpec('retail',['revenue'],oracle['date_start'],oracle['date_end'],time_grain='month'))
    runtime={r['period'][:7]:r['revenue'] for r in rows}
    for month,value in oracle['monthly'].items(): compare('monthly '+month,runtime.get(month),value)
    for dim,source in [('country',oracle['country_year']),('retail_product',oracle['product_year'])]:
        for year,expected_values in source.items():
            start=max(year+'-01-01',oracle['date_start']);end=min(year+'-12-31',oracle['date_end'])
            actual,_=engine.run_records(QuerySpec('retail',['revenue'],start,end,group_by=[dim],sort='revenue',limit=5))
            expected=sorted(expected_values.items(),key=lambda x:(-x[1],x[0]))[:5]
            checks.append({'check':dim+' ranking '+year,'actual':[r[dim] for r in actual],
                           'independent_expected':[r[0] for r in expected],'ok':[r[dim] for r in actual]==[r[0] for r in expected]})
            for row,(member,value) in zip(actual,expected): compare(dim+' '+year+' '+member,row['revenue'],value)
    complete=[m for m in oracle['monthly'] if m+'-01'>=oracle['date_start'] and pd.Period(m).end_time.date().isoformat()<=oracle['date_end']]
    if len(complete)>=2:
        current,previous=complete[-1],complete[-2]
        from backend.agent.analytics import FactBook,retail_contributors
        ranges=lambda m:{'start':m+'-01','end':pd.Period(m).end_time.date().isoformat(),'label':m}
        fb=FactBook();contributors=retail_contributors(fb,{},ranges(current),ranges(previous))
        compare('period comparison delta',sum(r['delta'] for r in contributors),oracle['monthly'][current]-oracle['monthly'][previous])
        countries=set(oracle['month_country'][current])|set(oracle['month_country'][previous])
        actual={r['member']:r['delta'] for r in contributors}
        for country in countries:
            compare('country contribution '+country,actual.get(country),oracle['month_country'][current].get(country,0)-oracle['month_country'][previous].get(country,0))
    else:
        checks.append({'check':'two complete month comparison','ok':False,'reason':'Not enough coverage'})
    out={'generated_at':datetime.now(timezone.utc).isoformat(),'dataset':REPORT['dataset'],'method':oracle['method'],
         'source_hashes':oracle['sources'],'runtime_source_hashes':REPORT['sources'],'duration_seconds':round(time.perf_counter()-t0,2),
         'checks':checks,'passed':sum(c['ok'] for c in checks),'total_checks':len(checks),
         'sql_example':sql,'total_gbp':oracle['total_gbp'],'eligible_rows':oracle['eligible_rows']}
    report_dir=ROOT/'eval'/'reports';report_dir.mkdir(exist_ok=True)
    (report_dir/'retail_oracle.json').write_text(json.dumps(oracle,indent=2),encoding='utf-8')
    (report_dir/'retail_independent.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in out.items() if k not in ('checks','runtime_source_hashes')},indent=2))
    print('Failures:',[c for c in checks if not c['ok']])
    raise SystemExit(0 if all(c['ok'] for c in checks) else 1)
if __name__=='__main__':main()
