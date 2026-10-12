"""Ground Olist intents to imported controls and explicit business definitions."""
import re
from backend import catalog as C
from backend.nlu.lexicon import norm
from backend.nlu import timeparse
from backend.olist import REPORT,VIEWSPEC
LOCAL={'write_blocked','out_of_scope','undo','reset','save_view','export','help','greeting','explain_page'}

def choose_view(text,current):
 s=norm(text)
 if re.search(r'\b(review|reviews|ratings?|scores?|satisfaction)\b',s):return 'olist_reviews'
 if re.search(r'\b(revenue|sales|aov|average order value)\b',s):return 'olist_sales'
 if re.search(r'\b(late|delayed?|delays|delivery|deliveries|shipping)\b',s):return 'olist_delivery'
 return current if current.startswith('olist_') else 'olist_sales'

def adapt(pr,text,view):
 if not view.startswith('olist_') or pr.intent in LOCAL:return pr
 s=norm(text);metric=VIEWSPEC[view][2][0]
 if view=='olist_sales':
  if re.search(r'\b(aov|average order value|avg order value)\b',s):metric='olist_aov'
  elif re.search(r'\b(orders?|order count)\b',s) and not re.search(r'\b(revenue|sales value)\b',s):metric='olist_orders'
 elif view=='olist_delivery':
  if re.search(r'\b(time|days|duration)\b',s):metric='olist_delivery_days'
  elif re.search(r'\b(count|how many|number of)\b',s):metric='olist_orders'
 elif re.search(r'\b(low|poor|bad)\b',s):metric='olist_low_review_rate'
 elif re.search(r'\b(count|how many|number of)\b',s):metric='olist_reviewed_orders'
 explicit_metric=bool(re.search(r'\b(revenue|sales|aov|orders?|review|reviews|ratings?|scores?|late|delay|delays|delivery|deliveries)\b',s))
 pr.metrics=[{'view':view,'metric':metric,'weak':False,'phrase':'Olist grounded request'}] if explicit_metric or not pr.followup else []
 pr.view_hints=[view]
 pr.group_by=[{'city':'br_city','region':'br_state'}.get(g,g) for g in pr.group_by]
 if re.search(r'\bstates?\b',s):pr.group_by=['br_state']
 if re.search(r'\bcities\b',s):pr.group_by=['br_city']
 if re.search(r'\b(by delivery status|late.*on time|on time.*late)\b',s):pr.group_by=['olist_delivery_status']
 if re.search(r'\blate\b',s) and re.search(r'\bon[ -]time\b',s) and pr.intent=='compare':pr.filters['olist_delivery_status']=['Late','On time']
 for state in C.DIMENSION_VALUES['br_state']:
  if state!='Unknown' and (re.search(r'\b'+re.escape(state)+r'\b',text) or re.search(r'\b(?:for|in|state)\s+'+re.escape(state.lower())+r'\b',s)):pr.filters['br_state']=[state];pr.group_by=[g for g in pr.group_by if g!='br_state']
 for city in C.DIMENSION_VALUES['br_city']:
  if city!='Unknown' and re.search(r'\b(?:for|in|city)\s+'+re.escape(city.lower())+r'\b',s):
   pr.filters['br_city']=[city];pr.unknown_entities=[]
 if re.search(r'\b(?:for|only|in) (?:the )?late (?:orders|deliveries)\b',s):pr.filters['olist_delivery_status']=['Late']
 if re.search(r'\b(?:for|only|in) (?:the )?on[ -]time (?:orders|deliveries)\b',s):pr.filters['olist_delivery_status']=['On time']
 dims={'br_state','br_city','olist_delivery_status','order_status'}
 invalid=[g for g in pr.group_by if g not in dims]+[f for f in list(pr.filters)+list(pr.excluded) if f not in dims]
 if invalid:pr.clarification_question='Olist currently supports Brazilian state/city, order status and delivery status. Product/category/seller/payment rankings are not exposed yet.'
 scope=re.search(r'\b(?:for|in)\s+([a-z][a-z ]*?)(?=\s+(?:in|during|from|for|last|this|by|vs)\b|\s+\d|[?.,]|$)',s)
 if scope and not pr.filters:
  value=scope.group(1).strip()
  if value not in {'late and on time deliveries','late and on-time deliveries','total','all time'} and not re.match(r'(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)',value):
   pr.clarification_question=f'{value.title()} is not an imported Olist state or city. Choose an available value.'
 if pr.unknown_entities:
  pr.clarification_question=f'{pr.unknown_entities[0]} is not an imported Olist state or city. Use an available value such as SP or RJ.';pr.unknown_entities=[]
 if re.search(r'\b(profit|margin|tax|taxes|freight|inventory|stockout|forecast|predict|quantity|units sold|customer ranking|payment methods?|median|percentile|variance|correlation|sellers?|categories|category|products?)\b',s):
  pr.clarification_question='Olist currently supports sales, delivery and reviews by state/city or delivery status. That metric or breakdown is not available yet.'
 if pr.intent=='why':
  if not (pr.time and pr.time.main):pr.followup=True
  if view!='olist_sales':
   pr.clarification_question='These records do not establish causes. Compare review scores for late and on-time deliveries to examine an association.'
   pr.clarification_options=[{'label':'Compare delivery and reviews','utterance':'Compare review scores for late and on-time deliveries in 2017'}]
  else:pr.group_by=pr.group_by or ['br_state']
 if re.search(r'\bbest\b',s) and re.search(r'\bstates?\b',s) and not explicit_metric:
  pr.clarification_question='Rank states by sales value or late-delivery rate?'
  pr.clarification_options=[{'label':'Sales value','utterance':re.sub(r'\bbest\b','top 5',text,flags=re.I)+' by sales value'}, {'label':'Late delivery rate','utterance':'Top 5 states by late delivery rate in 2017'}]
 if pr.time and pr.time.main and pr.time.main.preset=='all_time':
  from backend.olist import bounds
  lo,hi=bounds(view);pr.time.main=timeparse.Range(lo,hi,'All imported orders','all_time')
 if pr.time and pr.time.grain and pr.intent in ('show','query') and not pr.group_by:pr.intent='trend'
 return pr
