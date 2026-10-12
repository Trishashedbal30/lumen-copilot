"""Optional imported dataset registry. Synthetic tables and dimensions remain intact."""
from datetime import date
import json
import os
from pathlib import Path
import duckdb
from backend import catalog as C
ROOT=Path(__file__).resolve().parents[1]
RETAIL_DB=Path(os.environ.get('LUMEN_RETAIL_DB', ROOT/'data'/'uci_retail.duckdb'))
REPORT=None
RETAIL_PAGE='uci.sales.overview'

def register(views):
    global REPORT
    if not RETAIL_DB.is_file(): return
    with duckdb.connect(str(RETAIL_DB),read_only=True) as con:
        REPORT=json.loads(con.execute('SELECT report FROM uci_import_manifest').fetchone()[0])
        for field in ('country','retail_product','customer_id'):
            C.DIMENSION_VALUES[field]=[r[0] for r in con.execute(f'SELECT DISTINCT "{field}" FROM uci_sales WHERE "{field}" IS NOT NULL ORDER BY 1').fetchall()]
    if 'United Kingdom' in C.DIMENSION_VALUES['country']:
        C.VALUE_SYNONYMS['country']={'uk':'United Kingdom','great britain':'United Kingdom','gb':'United Kingdom'}
    C.DIMENSION_LABELS.update(country='Country',retail_product='Product (StockCode)',customer_id='Customer ID')
    C.DIMENSION_SYNONYMS.update(country=['country','countries','nation','nations'],retail_product=['stockcode','stock code','retail product','retail products'])
    views['retail']={'label':'UCI Online Retail II · real imported data', 'table':'uci_sales', 'min_grain':'day',
       'description':REPORT['cleaning_policy'],'dims':['country','retail_product','customer_id'], 'default_metric':'revenue',
       'dataset':REPORT['dataset'],'currency':'GBP',
       'metrics':{'revenue':{'label':'Revenue (GBP)', 'sql':'SUM(revenue)', 'fmt':'gbp', 'additive':True,'good':'up',
                             'definition':REPORT['cleaning_policy'],'synonyms':['retail revenue','uci revenue']}}}
    views['retail']['metrics'].update({
        'retail_orders': {'label':'Order count','sql':'COUNT(DISTINCT invoice)','fmt':'retail_int','additive':False,'good':'up',
            'definition':'Distinct eligible positive-sales invoice identifiers in the selected scope. Not invoice-line count. Product-level counts can overlap.', 'synonyms':['retail order count','uci orders']},
        'retail_quantity': {'label':'Quantity sold','sql':'SUM(quantity)','fmt':'retail_int','additive':True,'good':'up',
            'definition':'Sum of positive quantities on eligible sales lines; returns and cancellations excluded.', 'synonyms':['retail quantity sold','uci units sold']},
        'retail_aov': {'label':'Average order value (GBP)','sql':'SUM(revenue)/NULLIF(COUNT(DISTINCT invoice),0)','fmt':'gbp','additive':False,'good':'up',
            'definition':'Eligible positive-sales revenue divided by distinct eligible invoices within the selected filters and dates. Not an average of line values or monthly averages.', 'synonyms':['retail average order value','uci aov']},
    })

def bounds(view):
    if view and view.startswith("olist_"):
        from backend.olist import bounds as olist_bounds
        return olist_bounds(view)
    if view=='retail' and REPORT: return date.fromisoformat(REPORT['date_start']),date.fromisoformat(REPORT['date_end'])
    return C.DATA_START,C.DATA_END

def augment_metadata(meta):
    if not REPORT:
        meta['datasets']={'retail':{'available':False,'instructions':'Import with python -m backend.data.import_retail <workbook.xlsx>; restart Lumen.',
                                  'source_url':'https://archive.ics.uci.edu/dataset/502/online+retail+ii'}}
        return meta
    from backend.data.generate_metadata import Builder
    b=Builder();d=b.directory('uci','UCI Online Retail II · real','trending-up','Imported historical transactions in GBP')
    sub=b.subdir(d,'sales','Sales')
    p=b.page(d,sub,'overview','UCI Online Retail II Sales','retail',
             REPORT['cleaning_policy'],['revenue','retail_orders','retail_quantity','retail_aov'],['country','retail_product'],
             synonyms=['uci sales','online retail ii','real data sales','retail sales'],date_preset='all_time',
             extra_widgets=[{'type':'grid','view':'retail','metrics':['revenue'],'dimensions':['retail_product'],
                             'title':'Top products · StockCode','top_n':25}])
    customer=b.page(d,sub,'customers','UCI Customer Sales','retail',
        'Rank known Customer IDs by positive-sales revenue, quantity or orders. Unidentified customers are excluded from rankings.',
        ['revenue','retail_orders','retail_quantity','retail_aov'],['customer_id'],
        synonyms=['uci customer ranking','retail customer sales'],date_preset='all_time')
    for retail_page in (p,customer):
        retail_page['default_state']['compare']='none'
        retail_page['data_bounds']={'start':REPORT['date_start'],'end':REPORT['date_end']}
        retail_page['dataset']='UCI Online Retail II / real imported data / GBP'
    meta['pages'].update(b.pages);meta['directories'].extend(b.dirs);meta['routes'].update({page['route']:page['id'] for page in (p,customer)})
    meta['datasets']={'retail':{'available':True,**REPORT}}
    meta['data_views']['retail']={'label':'UCI Online Retail II','description':REPORT['cleaning_policy'],
       'dimensions':[{'field':f,'label':C.DIMENSION_LABELS[f],'values':C.DIMENSION_VALUES[f]} for f in ['country','retail_product','customer_id']],
       'metrics':[{'name':name,'label':md['label'],'format':md['fmt'],'additive':md['additive'],'good_direction':md['good']} for name,md in _retail_metrics().items()],
       'default_metric':'revenue','min_grain':'day'}
    return meta


def _retail_metrics():
    from backend.semantic.layer import VIEWS
    return VIEWS['retail']['metrics']
