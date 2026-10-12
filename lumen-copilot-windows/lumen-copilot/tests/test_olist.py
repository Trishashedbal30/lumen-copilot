"""Olist import grain, calendar lateness, routing and grounded-state regressions."""
import os
from unittest.mock import patch
import pandas as pd
import pytest
from backend.data.import_olist import prepare
from backend.main import AGENT
from backend.agent.controller import Agent
from backend.render import render_page


def fixture_frames():
 return {
 'orders':pd.DataFrame([['o1','c1','delivered','2017-01-01','2017-01-04 16:00:00','2017-01-04'],['o2','c2','canceled','2017-01-02',None,'2017-01-05']],columns=['order_id','customer_id','order_status','order_purchase_timestamp','order_delivered_customer_date','order_estimated_delivery_date']),
 'customers':pd.DataFrame([['c1','u1','SP','sao paulo'],['c2','u2','RJ','rio de janeiro']],columns=['customer_id','customer_unique_id','customer_state','customer_city']),
 'items':pd.DataFrame([['o1','1','10','2'],['o1','2','20','3'],['o2','1','500','0']],columns=['order_id','order_item_id','price','freight_value']),
 'payments':pd.DataFrame([['o1','1','5'],['o1','2','25']],columns=['order_id','payment_sequential','payment_value']),
 'reviews':pd.DataFrame([['o1','r1','1'],['o1','r2','5'],['o2','r3','5']],columns=['order_id','review_id','review_score'])}

def test_components_aggregate_before_join_without_multiplying_sales():
 facts,report=prepare(fixture_frames());row=facts[facts.order_id=='o1'].iloc[0]
 assert len(facts)==2 and row.sales_value==30 and row.payment_value==30 and row.freight_value==5
 assert row.review_score==3 and row.review_count==2 and row.late_flag==0
 assert report['coverage']['olist_sales']['eligible_orders']==1
 assert report['coverage']['olist_reviews']['eligible_orders']==1

def test_conflicting_keys_fail_and_exact_duplicates_excluded():
 frames=fixture_frames();frames['items']=pd.concat([frames['items'],frames['items'].iloc[:1]])
 facts,report=prepare(frames);assert report['exclusions']['items_exact_duplicates']==1
 frames['orders']=pd.concat([frames['orders'],frames['orders'].iloc[:1].assign(order_status='canceled')])
 with pytest.raises(ValueError,match='primary keys'):prepare(frames)

@pytest.fixture
def agent():
 if 'olist.sales.overview' not in AGENT.meta['pages']:pytest.skip('Olist not imported')
 with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'rules'}):yield Agent(AGENT.meta)

@pytest.mark.parametrize('question,pid,metric',[
 ('Show monthly sales value for 2017','olist.sales.overview','olist_revenue'),
 ('Top 5 states by late delivery rate in 2017','olist.delivery.overview','olist_late_rate'),
 ('Show average delivery time for SP in 2017','olist.delivery.overview','olist_delivery_days'),
 ('Compare review scores for late and on-time deliveries in 2017','olist.reviews.overview','olist_review_score'),
 ('What is average order value in 2017?','olist.sales.overview','olist_aov')])
def test_navigation_valid_controls_and_evidence(agent,question,pid,metric):
 r=agent.handle(None,question,agent.planner.default_state('olist.sales.overview'))
 assert r['kind']=='act' and r['target_state']['page_id']==pid and r['facts'][0]['metric']==metric
 assert agent.verify(r['session_id'],r['turn_id'],r['target_state'])['ok']
 assert all(f['dataset'].startswith('Olist') and f['metric_definition'] and f['sql'] for f in r['facts'])
 assert not any(w.get('error') for w in render_page(agent.planner,r['target_state'])['widgets'])

def test_followup_explanation_preserves_comparison_dates(agent):
 r=agent.handle(None,'Compare sales in October 2017 and November 2017',agent.planner.default_state('olist.sales.overview'))
 next_=agent.handle(r['session_id'],'Why did sales change?',r['target_state'])
 assert next_['target_state']['date_range']==r['target_state']['date_range']
 assert next_['target_state']['compare_range']==r['target_state']['compare_range']
 values=[f['value'] for f in next_['facts'] if f['kind']=='value']
 contributions=[f['value'] for f in next_['facts'] if f['kind']=='contribution']
 assert sum(contributions)==pytest.approx(values[0]-values[1],abs=.005)

def test_entity_comparison_and_followup_keep_scope(agent):
 r=agent.handle(None,'Compare review scores for late and on-time deliveries in 2017',agent.planner.default_state('olist.sales.overview'))
 assert r['target_state']['compare']=='none'
 next_=agent.handle(r['session_id'],'What about SP?',r['target_state'])
 assert next_['target_state']['page_id']=='olist.reviews.overview'
 assert next_['target_state']['filters']['br_state']==['SP']
 assert next_['target_state']['date_range']==r['target_state']['date_range']
 assert 'On time' in next_['reply'] and 'Late' in next_['reply']

@pytest.mark.parametrize('question',['Show profit for 2017','Top 5 sellers by revenue in 2017','Show sales for Atlantis in 2017'])
def test_unsupported_requests_make_no_actions(agent,question):
 r=agent.handle(None,question,agent.planner.default_state('olist.sales.overview'))
 assert r['kind']=='clarify' and not r['actions']


def test_switching_workspaces_cannot_reuse_a_foreign_dataset_metric(agent):
 r=agent.handle(None,'Show revenue in 2011',agent.planner.default_state('uci.sales.overview'))
 next_=agent.handle(r['session_id'],'What about 2017?',agent.planner.default_state('olist.sales.overview'))
 assert next_['kind']=='act' and next_['target_state']['page_id']=='olist.sales.overview'
 assert next_['facts'][0]['dataset'].startswith('Olist')
