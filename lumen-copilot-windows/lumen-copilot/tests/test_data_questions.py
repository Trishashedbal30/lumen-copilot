"""Regression checks for data intent controls and unsupported retail scope."""
import os
from unittest.mock import patch
import pytest
from backend.main import AGENT
from backend.agent.controller import Agent

@pytest.mark.parametrize('question',['Show monthly revenue in 2026','What is weekly revenue in August 2026?','Show quarterly revenue in 2026'])
def test_explicit_time_grain_produces_a_series(question):
 agent=Agent(AGENT.meta)
 with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'rules'}):
  r=agent.handle(None,question,agent.planner.default_state('exec.dashboards.summary'))
 assert r['kind']=='act'
 assert any(t.get('analysis')=='trend' for t in r['trace'])
 assert r['cards'][0]['type']=='line'
 assert agent.verify(r['session_id'],r['turn_id'],r['target_state'])['ok']

@pytest.mark.parametrize('question',['Show revenue for Atlantis in 2011','Show revenue in Atlantis in 2011','What was profit in 2011?'])
def test_unsupported_real_scope_clarifies_before_model_or_actions(question):
 if 'uci.sales.overview' not in AGENT.meta['pages']:pytest.skip('Retail dataset not imported')
 agent=Agent(AGENT.meta)
 with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'llm','LUMEN_LLM_PROVIDER':'groq','LUMEN_LLM_API_KEY':'test-key'}),patch.object(agent.llm,'parse') as model:
  r=agent.handle(None,question,agent.planner.default_state('uci.sales.overview'))
 assert r['kind']=='clarify' and not r['actions']
 model.assert_not_called()

@pytest.mark.parametrize('question',['Show revenue for UK in 2011','Show revenue in France in 2011','Show revenue for November 2011'])
def test_valid_real_scopes_remain_available(question):
 if 'uci.sales.overview' not in AGENT.meta['pages']:pytest.skip('Retail dataset not imported')
 agent=Agent(AGENT.meta)
 with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'rules'}):
  r=agent.handle(None,question,agent.planner.default_state('uci.sales.overview'))
 assert r['kind']=='act'


def test_grounded_mean_keeps_calculation_when_model_unnecessarily_clarifies():
 agent=Agent(AGENT.meta);lp=agent.parser.parse('show revenue')
 lp.metrics=[];lp.clarification_question='Which months did you mean?'
 with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'llm','LUMEN_LLM_PROVIDER':'groq','LUMEN_LLM_API_KEY':'test-key'}),patch.object(agent.llm,'parse',return_value=lp) as model:
  r=agent.handle(None,'which moths revenue is more than avegare in 2026',agent.planner.default_state('exec.dashboards.summary'))
 assert r['kind']=='act'
 assert any(t.get('analysis')=='monthly_average' for t in r['trace'])
 assert 'average' in model.call_args.args[0] and 'avegare' not in model.call_args.args[0]
 assert 'Average monthly revenue' in r['reply']


def test_explicit_monthly_series_survives_model_kpi_intent():
 agent=Agent(AGENT.meta);lp=agent.parser.parse('what is revenue in 2026')
 with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'llm','LUMEN_LLM_PROVIDER':'groq','LUMEN_LLM_API_KEY':'test-key'}),patch.object(agent.llm,'parse',return_value=lp):
  r=agent.handle(None,'show monthly revenue in 2026',agent.planner.default_state('exec.dashboards.summary'))
 assert r['kind']=='act'
 assert any(t.get('analysis')=='trend' for t in r['trace'])
 assert r['target_state']['grain']=='month'


@pytest.mark.parametrize('question',['Which month had highest revenue in 2026','Which quarter had lowest revenue in 2026'])
def test_time_extreme_selects_trend_not_dimension_rank(question):
 agent=Agent(AGENT.meta)
 with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'rules'}):
  r=agent.handle(None,question,agent.planner.default_state('exec.dashboards.summary'))
 assert r['kind']=='act'
 assert any(t.get('analysis')=='trend' for t in r['trace'])
 assert any(f['label'].startswith('Peak') for f in r['facts'])

@pytest.mark.parametrize('question',['What is median revenue in 2011?','How many countries in 2011?','What is net revenue in 2011?'])
def test_unsupported_aggregate_is_not_a_revenue_total(question):
 if 'uci.sales.overview' not in AGENT.meta['pages']:pytest.skip('Retail dataset not imported')
 agent=Agent(AGENT.meta)
 with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'rules'}):
  r=agent.handle(None,question,agent.planner.default_state('uci.sales.overview'))
 assert r['kind']=='clarify' and not r['actions']


def test_json_only_model_cannot_add_valid_but_unrequested_filter():
 agent=Agent(AGENT.meta)
 fake={'intent':'query','metric':'sales.revenue','filters':{'region':['North']},'time_expression':'August 2026'}
 pr=agent.llm.parse('show revenue in August 2026',call_fn=lambda s,u:fake)
 assert not pr.filters
 assert pr.llm_blocked==['unrequested:region=North']
 assert pr.clarification_question


def test_json_only_model_accepts_an_explicit_filter_alias():
 agent=Agent(AGENT.meta)
 fake={'intent':'query','metric':'sales.revenue','filters':{'channel':['Online Store']},'time_expression':'August 2026'}
 pr=agent.llm.parse('show online revenue in August 2026',call_fn=lambda s,u:fake)
 assert pr.filters=={'channel':['Online Store']}
 assert not pr.llm_blocked



def test_monthly_business_review_remains_a_named_page_lookup():
 agent=Agent(AGENT.meta)
 pr=agent.parser.parse('monthly business review')
 assert pr.intent!='trend'
 with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'rules'}):
  r=agent.handle(None,'monthly business review',agent.planner.default_state('exec.dashboards.summary'))
 assert r['target_state']['page_id']=='exec.dashboards.mbr'


def test_city_category_scope_prefers_the_specific_city_destination():
 agent=Agent(AGENT.meta)
 with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'rules'}):
  r=agent.handle(None,'revenue for the electronics category in hyderabad last month',agent.planner.default_state('exec.dashboards.summary'))
 assert r['target_state']['page_id']=='sales.city.hyderabad'
 assert r['target_state']['filters']=={'city':['Hyderabad'],'category':['Electronics']}



def test_available_month_comparison_survives_model_clarification():
 if 'uci.sales.overview' not in AGENT.meta['pages']:pytest.skip('Retail dataset not imported')
 agent=Agent(AGENT.meta);lp=agent.parser.parse('show revenue')
 lp.clarification_question='Which two months do you mean?'
 with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'llm','LUMEN_LLM_PROVIDER':'groq','LUMEN_LLM_API_KEY':'test-key'}),patch.object(agent.llm,'parse',return_value=lp):
  r=agent.handle(None,'Compare revenue in two available months',agent.planner.default_state('uci.sales.overview'))
 assert r['kind']=='act'
 assert any(t.get('analysis')=='compare_periods' for t in r['trace'])
 assert r['target_state']['date_range']['start']=='2011-11-01'
 assert r['target_state']['compare_range']['start']=='2011-10-01'


def test_explicit_date_cannot_be_changed_by_model():
 agent=Agent(AGENT.meta);lp=agent.parser.parse('show revenue in July 2026')
 with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'llm','LUMEN_LLM_PROVIDER':'groq','LUMEN_LLM_API_KEY':'test-key'}),patch.object(agent.llm,'parse',return_value=lp):
  r=agent.handle(None,'show revenue in August 2026',agent.planner.default_state('exec.dashboards.summary'))
 assert r['target_state']['date_range']['start']=='2026-08-01'
 assert r['target_state']['date_range']['end']=='2026-08-31'



def test_model_month_dimension_is_normalized_to_time_grain():
 agent=Agent(AGENT.meta)
 fake={'intent':'trend','metric':'sales.revenue','group_by':['month'],'time_expression':'2026','filters':{}}
 pr=agent.llm.parse('show monthly revenue in 2026',call_fn=lambda s,u:fake)
 assert not pr.group_by and pr.time.grain=='month'
 assert not pr.llm_blocked and not pr.clarification_question



def test_saved_view_preserves_ui_controls_without_derived_render_fields():
 import copy
 agent=Agent(AGENT.meta);state=agent.planner.default_state('sales.city.leaderboard')
 state['top_n']=5;expected=copy.deepcopy(state)
 state['cmp_range']=agent.planner.comparison_range(state)
 with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'rules'}):
  r=agent.handle(None,'save this view',state)
 assert r['kind']=='confirm' and not r['actions']
 saved=agent.confirm(r['session_id'],r['needs_confirmation']['id'],True)
 assert saved['saved_view']['state']==expected



@pytest.mark.parametrize('question',['Which year had highest revenue','Show yearly revenue'])
def test_unavailable_yearly_chart_does_not_misverify_monthly_ui(question):
 agent=Agent(AGENT.meta)
 with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'rules'}):
  r=agent.handle(None,question,agent.planner.default_state('exec.dashboards.summary'))
 assert r['kind']=='clarify' and not r['actions']


@pytest.mark.parametrize('question', [
 'Who are the top 10 customers by revenue in 2011?',
 'Rank customers by sales in 2011',
 'Show revenue by customer ID in 2011',
])
@pytest.mark.parametrize('mode', ['rules', 'llm'])
def test_customer_ranking_uses_grounded_dimension_and_verified_state(question, mode):
 if 'uci.sales.overview' not in AGENT.meta['pages']:pytest.skip('Retail dataset not imported')
 agent=Agent(AGENT.meta);state=agent.planner.default_state('uci.sales.overview')
 # Model can understand the words while omitting the newly supported dimension.
 lp=agent.parser.parse('what is revenue in 2011');lp.clarification_question='Which dimension identifies customers?'
 with patch.dict(os.environ,{'LUMEN_AGENT_MODE':mode,'LUMEN_LLM_PROVIDER':'groq','LUMEN_LLM_API_KEY':'test-key'}),patch.object(agent.llm,'parse',return_value=lp):
  r=agent.handle(None,question,state)
 assert r['kind']=='act' and r['target_state']['page_id']=='uci.sales.customers'
 assert 'customer ids' in r['reply'] and all(x is not None for x in r['cards'][0]['labels'])
 assert agent.verify(r['session_id'],r['turn_id'],r['target_state'])['ok']
