"""Retail metric, clarification, partial-coverage and evidence integration checks."""
import os
from unittest.mock import patch
import pytest
from backend.main import AGENT
from backend.agent.controller import Agent
from backend.render import render_page
from backend.semantic import engine
from backend.semantic.layer import QuerySpec

@pytest.fixture
def agent():
 if 'uci.sales.overview' not in AGENT.meta['pages']:pytest.skip('Retail not imported')
 with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'rules'}):yield Agent(AGENT.meta)

def ask(agent,text,sid=None,state=None):
 return agent.handle(sid,text,state or agent.planner.default_state('uci.sales.overview'))

@pytest.mark.parametrize('question,metric',[
 ('How many orders in 2011?','retail_orders'),
 ('What is quantity sold in 2011?','retail_quantity'),
 ('What is the average order value in November 2011?','retail_aov'),
 ('Top 5 products by quantity sold in 2011','retail_quantity'),
])
def test_metric_routes_and_evidence(agent,question,metric):
 r=ask(agent,question)
 assert r['kind']=='act' and r['facts'][0]['metric']==metric
 assert r['target_state']['page_id']=='uci.sales.overview'
 assert r['facts'][0]['metric_definition'] and r['facts'][0]['sql']
 assert agent.verify(r['session_id'],r['turn_id'],r['target_state'])['ok']
 rendered=render_page(agent.planner,r['target_state'])
 assert not any(w.get('error') for w in rendered['widgets'])

@pytest.mark.parametrize('noun',['products','customers','countries'])
def test_ambiguous_best_offers_executable_choices(agent,noun):
 r=ask(agent,f'Show the best {noun} in 2011')
 assert r['kind']=='clarify' and not r['actions'] and not r['target_state']
 assert [s['label'] for s in r['suggestions']]==['Revenue','Quantity sold','Order count']
 for s in r['suggestions']:
  result=ask(agent,s['utterance'])
  assert result['kind']=='act'
  assert agent.verify(result['session_id'],result['turn_id'],result['target_state'])['ok']

def test_partial_december_warns_and_equal_day_choice_applies(agent):
 r=ask(agent,'Compare revenue in November 2011 and December 2011')
 assert r['kind']=='act' and 'Incomplete month' in r['reply']
 assert 'different numbers of days' in r['reply']
 assert r['suggestions'][0]['label']=='Compare first 9 days'
 next_=ask(agent,r['suggestions'][0]['utterance'],r['session_id'],r['target_state'])
 assert next_['kind']=='act'
 state=next_['target_state']
 assert state['date_range']['end'].endswith('-09') and state['compare_range']['end'].endswith('-09')
 assert agent.verify(next_['session_id'],next_['turn_id'],state)['ok']
 assert render_page(agent.planner,r['target_state'])['warnings']

def test_missing_customer_ids_excluded_from_ranking(agent):
 rows,_=engine.run_records(QuerySpec('retail',['revenue'],'2011-01-01','2011-12-09',group_by=['customer_id'],sort='revenue',limit=10))
 assert len(rows)==10 and all(x['customer_id'] for x in rows)
 r=ask(agent,'Who are the top 10 customers by revenue in 2011?')
 assert r['cards'][0]['labels']==[x['customer_id'] for x in rows]
 assert r['target_state']['top_n']==10

def test_product_followup_reconciles_to_overall_delta_and_has_evidence(agent):
 r=ask(agent,'Compare revenue in October 2011 and November 2011')
 next_=ask(agent,'Which products contributed most to the change?',r['session_id'],r['target_state'])
 assert next_['kind']=='act' and next_['analysis']['dimension']=='retail_product'
 current=next(x['value'] for x in next_['facts'] if x['kind']=='value')
 previous=[x['value'] for x in next_['facts'] if x['kind']=='value'][1]
 contributions=[x for x in next_['facts'] if x['kind']=='contribution']
 assert len(contributions)==6
 assert sum(x['value'] for x in contributions)==pytest.approx(current-previous,abs=.01)
 assert next_['analysis']['total_delta']==pytest.approx(current-previous,abs=.01)
 assert 'External causes are not established' in next_['reply']
 assert agent.verify(next_['session_id'],next_['turn_id'],next_['target_state'])['ok']

def test_unknown_customer_clarifies_without_actions(agent):
 r=ask(agent,'Show revenue for customer 99999999 in 2011')
 assert r['kind']=='clarify' and not r['actions']

def test_quantity_followup_keeps_metric(agent):
 r=ask(agent,'Show quantity sold in November 2011')
 next_=ask(agent,'What about Germany?',r['session_id'],r['target_state'])
 assert next_['kind']=='act' and next_['facts'][0]['metric']=='retail_quantity'
 assert next_['target_state']['filters']['country']==['Germany']
