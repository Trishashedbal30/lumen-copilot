"""Ground retail requests using the imported catalog; uses the existing planner and action DSL."""
import re
from backend import catalog as C
from backend.datasets import REPORT, RETAIL_PAGE, bounds
from backend.nlu import timeparse
from backend.nlu.lexicon import norm

LOCAL = {'write_blocked','out_of_scope','undo','reset','save_view','export','help','greeting','explain_page'}

def active_view(text, state, metadata):
    current=metadata['pages'].get((state or {}).get('page_id'),{}).get('view','sales')
    from backend.olist import REPORT as OLIST_REPORT
    if OLIST_REPORT and (re.search(r'\b(olist|brazil|brazilian ecommerce)\b',text,re.I) or (current.startswith('olist_') and not re.search(r'\b(uci|online retail ii)\b',text,re.I))):
        from backend.nlu.olist import choose_view
        return choose_view(text,current)
    if REPORT and (re.search(r'\b(uci|online retail ii|real data)\b',text,re.I) or
                   metadata['pages'].get((state or {}).get('page_id'),{}).get('view')=='retail'):
        return 'retail'
    return metadata['pages'].get((state or {}).get('page_id'),{}).get('view','sales')

def adapt(pr, text, view):
    if view.startswith('olist_'):
        from backend.nlu.olist import adapt as adapt_olist
        return adapt_olist(pr,text,view)
    if view != 'retail' or pr.intent in LOCAL: return pr
    if re.search(r'\b(uci|online retail ii|real data)\b',text,re.I):
        pr.page_mentions=[(RETAIL_PAGE,1.0,norm('UCI Online Retail II Sales'))]
    if re.search(r'\b(net revenue|net sales|unit price|vat|tax|taxes)\b|\bhow many (?:distinct |unique )?(?:countries|products|customers)\b', norm(text)):
        pr.clarification_question = 'This UCI view supports positive-sales revenue, order count, quantity sold, average order value, country/product/customer-ID rankings and period comparisons. Net returns, customer counts, prices and taxes are not available as metrics.'
    s=norm(text)
    selected = None
    if re.search(r'\b(average order value|avg order value|aov)\b',s): selected='retail_aov'
    elif re.search(r'\b(quantity|quantities|units sold|items sold)\b',s): selected='retail_quantity'
    elif re.search(r'\b(orders?|invoices?)\b',s): selected='retail_orders'
    elif re.search(r'\b(revenue|sales)\b',s): selected='revenue'
    supported={'revenue','orders','aov','retail_orders','retail_quantity','retail_aov'}
    unsupported=[m['metric'] for m in pr.metrics if m['metric'] not in supported and not (m['metric']=='active_customers' and re.search(r'\bcustomers?\b',s))]
    invalid_fields=[f for f in list(pr.filters)+list(pr.excluded) if f not in ('country','retail_product','customer_id')]
    if unsupported or invalid_fields:
        pr.clarification_question='UCI sales supports revenue, order count, quantity sold and average order value by country, StockCode or Customer ID. Choose a supported sales request or open a synthetic page.'
    existing=[m for m in pr.metrics if m['view']=='retail']
    metric=selected or (existing[0]['metric'] if existing else 'revenue')
    pr.metrics=[{'view':'retail','metric':metric,'weak':False,'phrase':'active UCI sales'}]
    if not selected and pr.followup and not existing: pr.metrics=[]
    pr.view_hints=['retail']
    pr.group_by=[('retail_product' if g=='product' else g) for g in pr.group_by]
    if any(g not in ('country','retail_product','customer_id') for g in pr.group_by):
        pr.clarification_question='UCI sales can be grouped by country, product StockCode or Customer ID.'
    s=norm(text)
    pr.unknown_entities = [e for e in pr.unknown_entities if norm(e) not in {norm(c) for c in pr.filters.get('country', [])}]
    if pr.unknown_entities:
        pr.clarification_question = f"{pr.unknown_entities[0]} is not an imported country or StockCode. Choose an available value."
        pr.unknown_entities = []
    if re.search(r'\bproducts?\b',s) and 'retail_product' not in pr.group_by: pr.group_by.append('retail_product')
    if re.search(r'\bcountries?\b',s) and 'country' not in pr.group_by: pr.group_by.append('country')
    # An unrecognised explicit scope must not silently become an all-country total.
    scope = re.search(r'\b(?:for|in)\s+([a-z][a-z ]*?)(?=\s+(?:in|during|from|for|last|this|by|vs|versus)\b|\s+\d|[?.,]|$)', s)
    if scope and not pr.filters and not pr.excluded:
        value = scope.group(1).strip()
        temporal = r'(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec|total|all time|all imported sales|two available months)'
        if not re.fullmatch(temporal, value) and not re.match(r'(?:stock ?code|sku|product|customer|the |each |every |monthly|available months)', value):
            pr.clarification_question = f'{value.title()} is not an imported country or StockCode. Choose an available value.'
    # Exact stock codes only: never snap an unknown product to a synthetic one.
    match=re.search(r'\b(?:stock\s*code|stockcode|sku|product)\s+([a-z0-9]+)\b',s)
    if match and not match.group(1).isdigit() and match.group(1) in {'by','revenue','sales','trend'}: match=None
    if match:
        token=match.group(1)
        product=next((v for v in C.DIMENSION_VALUES['retail_product'] if v.lower()==token),None)
        if product:
            pr.filters['retail_product']=[product];pr.group_by=[g for g in pr.group_by if g!='retail_product']
        else: pr.clarification_question=f'StockCode {token} is not available. Choose an imported StockCode.'
    if re.search(r'\bcustomers?\b',s):
        pr.group_by=[g for g in pr.group_by if g!='customer_id']+['customer_id']
        match=re.search(r'\bcustomer(?: id)?\s+([0-9]+(?:\.0)?)\b',s)
        if match:
            token=match.group(1)
            value=next((v for v in C.DIMENSION_VALUES['customer_id'] if v==token or v.removesuffix('.0')==token.removesuffix('.0')),None)
            if value: pr.filters['customer_id']=[value];pr.group_by=[]
            else: pr.clarification_question=f'Customer ID {token} is not available. Choose an imported Customer ID.'
    if re.search(r'\b(contributed|contributors?|contribution)\b',s): pr.intent='why'
    if re.search(r'\bbest\b',s) and re.search(r'\b(products?|customers?|countries)\b',s) and not selected:
        pr.clarification_question='How should I rank them: by revenue, quantity sold or order count?'
        base=re.sub(r'\bbest\b','top 10',text,flags=re.I)
        pr.clarification_options=[{'label':label,'utterance':base+' by '+metric} for label,metric in [('Revenue','revenue'),('Quantity sold','quantity sold'),('Order count','order count')]]
    lo,hi=bounds('retail')
    if pr.time and pr.time.main and pr.time.main.preset=='all_time': pr.time.main=timeparse.Range(lo,hi,'All imported sales','all_time')
    if pr.intent=='compare' and re.search(r'\btwo available months\b',s):
        complete=[m for m in REPORT['available_months'] if timeparse.month_end(int(m[:4]),int(m[5:]))<=hi and timeparse.date(int(m[:4]),int(m[5:]),1)>=lo]
        if len(complete)<2:
            pr.clarification_question='Import at least two complete months for a period comparison.'
        else:
            a,b=complete[-1],complete[-2]
            pr.time=timeparse.parse(f'{a}-01 to {a}-{timeparse.month_end(int(a[:4]),int(a[5:])).day} vs {b}-01 to {b}-{timeparse.month_end(int(b[:4]),int(b[5:])).day}',today=hi)
            pr.followup=False
    if pr.time and pr.time.grain and pr.intent in ('show','query') and not pr.group_by: pr.intent='trend'
    return pr
