"""Regression and independent monthly-average calculation checks."""
import copy
import os
from unittest.mock import patch
import duckdb
import pytest
from backend.main import AGENT
from backend.agent.controller import Agent
from backend.agent.analytics import FactBook,monthly_average
from backend.semantic import engine


def test_monthly_mean_counts_empty_months_and_uses_strict_thresholds():
    con=duckdb.connect(':memory:');con.execute('CREATE TABLE sales_daily(date DATE,revenue DOUBLE)')
    con.execute("INSERT INTO sales_daily VALUES ('2026-01-01',10),('2026-01-31',10),('2026-03-01',40)")
    rng={'start':'2026-01-01','end':'2026-03-31','label':'fixture'}
    with patch.object(engine,'connection',return_value=con):
        fb=FactBook();result=monthly_average(fb,'sales','revenue',{},rng)
        assert [r['value'] for r in result['rows']]==[20,0,40]
        assert result['average']==20
        assert [r['period'] for r in result['rows'] if r['matches']]==['Mar 2026']
        below=monthly_average(FactBook(),'sales','revenue',{},rng,'below')
        assert [r['period'] for r in below['rows'] if r['matches']]==['Feb 2026']
        assert 'AVG(monthly_value) OVER ()' in fb.facts[0]['sql']
        assert fb.facts[0]['month_count']==3
        assert fb.facts[0]['calculation'].startswith('SUM(monthly totals)')
    con.close()


def test_exact_user_question_preserves_current_scope_and_aligns_full_months():
    agent=Agent(AGENT.meta);state=agent.planner.default_state('sales.channels.mix')
    state['filters']={'region':['South']};state['date_range']={'start':'2026-07-03','end':'2026-09-30','label':'Last 90 days'}
    with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'rules'}):
        r=agent.handle('average-regression','in which month was the revenue more than average',state)
    assert r['kind']=='act'
    assert any(t.get('analysis')=='monthly_average' for t in r['trace'])
    target=r['target_state'];assert target['grain']=='month' and target['compare']=='none'
    assert target['date_range']['start']=='2026-08-01' and target['date_range']['end']=='2026-09-30'
    assert target['filters']['region']==['South']
    # Independently aggregate source rows: do not reuse the new mean SQL.
    rows=engine.connection('sales').execute("SELECT month(date),SUM(revenue) FROM sales_daily WHERE date BETWEEN '2026-08-01' AND '2026-09-30' AND region='South' GROUP BY 1 ORDER BY 1").fetchall()
    expected=sum(v for _,v in rows)/len(rows)
    fact=next(f for f in r['facts'] if f['kind']=='monthly_average')
    assert fact['value']==pytest.approx(expected,abs=.0001)
    assert len(r['cards'][0]['series'])==2
    assert agent.verify(r['session_id'],r['turn_id'],target)['ok']


def test_uci_mean_independent_oracle_excludes_partial_december():
    import json
    from pathlib import Path
    if 'uci.sales.overview' not in AGENT.meta['pages']:pytest.skip('Official UCI dataset not imported')
    oracle=Path(__file__).resolve().parents[1]/'eval/reports/retail_oracle.json'
    if not oracle.is_file():pytest.skip('Independent source oracle unavailable')
    totals=json.loads(oracle.read_text(encoding='utf-8'))['monthly']
    months={k:v for k,v in totals.items() if '2011-01'<=k<='2011-11'}
    expected=sum(months.values())/len(months)
    agent=Agent(AGENT.meta)
    with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'rules'}):
        r=agent.handle(None,'Which months had revenue above average in 2011?',agent.planner.default_state('uci.sales.overview'))
    assert r['target_state']['date_range']['end']=='2011-11-30'
    assert next(f for f in r['facts'] if f['kind']=='monthly_average')['value']==pytest.approx(expected,abs=.0001)
    labels=r['cards'][0]['labels'];values=r['cards'][0]['series'][0]['values']
    assert [label for label,value in zip(labels,values) if value>expected]==['Sep 2011','Oct 2011','Nov 2011']


def test_partial_month_clarifies_and_llm_keeps_mean_request():
    agent=Agent(AGENT.meta);home=agent.planner.default_state('sales.channels.mix')
    with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'rules'}):
        r=agent.handle(None,'which month had revenue above average from 2026-09-05 to 2026-09-20',home)
    assert r['kind']=='clarify' and not r['actions']
    # A model can miss the mean operation; deterministic request controls must survive.
    lp=agent.parser.parse('show revenue in 2026')
    with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'llm','LUMEN_LLM_PROVIDER':'ollama'}),patch.object(agent.llm,'parse',return_value=lp):
        r=agent.handle(None,'which months had revenue above average in 2026',home)
    assert any(t.get('analysis')=='monthly_average' for t in r['trace'])
    assert r['target_state']['grain']=='month'


def test_average_followup_preserves_operation_and_has_evidence_link():
    agent=Agent(AGENT.meta);home=agent.planner.default_state('sales.channels.mix')
    with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'rules'}):
        first=agent.handle('mean-followup','Which months had South revenue above average in 2026?',home)
        second=agent.handle('mean-followup','what about North?',first['target_state'])
    assert any(t.get('analysis')=='monthly_average' for t in second['trace'])
    assert second['target_state']['filters']['region']==['North']
    assert any(c['label']=='Complete monthly totals and arithmetic mean' for c in second['citations'])
    assert second['target_state']['grain']=='month'


@pytest.mark.parametrize('text',[
    'which moths revenue is more than avegare',
    'which monts had revenue above avarage',
    'which monht had revenue greater than avreage',
    'which months had revenue below avergae',
])
def test_monthly_average_analytical_typos_are_corrected(text):
    agent=Agent(AGENT.meta)
    parsed=agent.parser.parse(text)
    assert parsed.average_direction in ('above','below')
    assert parsed.intent=='trend' and parsed.time.grain=='month'
    assert parsed.typo_fixes
    with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'rules'}):
        r=agent.handle(None,text,agent.planner.default_state('exec.dashboards.summary'))
    assert r['kind']=='act'
    assert any(t.get('analysis')=='monthly_average' for t in r['trace'])
    assert 'Average monthly revenue' in r['reply']


def test_analytical_typo_correction_preserves_protected_entities_and_other_requests():
    from backend.nlu.parser import normalize_monthly_average_terms
    text='show revenue for moths'
    assert normalize_monthly_average_terms(text)==(text,[])
    text='which months had revenue above avegare for moths'
    corrected,fixes=normalize_monthly_average_terms(text,protected={'moths'})
    assert corrected=='which months had revenue above average for moths'
    assert fixes==[('avegare','average')]


def test_exact_avg_request_overrides_llm_kpi_and_matches_independent_total():
    agent=Agent(AGENT.meta)
    question='Which month revenue is more than avg revenue in total'
    state=agent.planner.default_state('sales.regional.south')
    state['filters']={'region':['South']}
    state['date_range']={'start':'2026-07-03','end':'2026-09-30','label':'Last 90 days'}
    parsed=agent.parser.parse(question)
    assert parsed.average_direction=='above'
    assert ('avg','average') in parsed.typo_fixes
    # Reproduce the successful model response that interpreted this as a KPI.
    lp=agent.parser.parse('what is revenue')
    with patch.dict(os.environ,{'LUMEN_AGENT_MODE':'llm','LUMEN_LLM_PROVIDER':'groq','LUMEN_LLM_API_KEY':'test-key'}), patch.object(agent.llm,'parse',return_value=lp):
        result=agent.handle(None,question,state)
    assert result['kind']=='act'
    understanding=next(t for t in result['trace'] if t['node']=='understand')
    assert understanding['source']=='llm' and understanding['model_request_status']=='succeeded'
    assert ('avg','average') in understanding['slots']['typos_fixed']
    assert any(t.get('analysis')=='monthly_average' for t in result['trace'])
    target=result['target_state']
    assert target['filters']['region']==['South']
    assert target['grain']=='month' and target['compare']=='none'
    rows=engine.connection('sales').execute("SELECT month(date),SUM(revenue) FROM sales_daily WHERE date BETWEEN '2026-08-01' AND '2026-09-30' AND region='South' GROUP BY 1 ORDER BY 1").fetchall()
    expected=sum(value for _,value in rows)/2
    fact=next(f for f in result['facts'] if f['kind']=='monthly_average')
    assert fact['value']==pytest.approx(expected,abs=.0001)
    assert 'Average monthly revenue' in result['reply']
    assert agent.verify(result['session_id'],result['turn_id'],target)['ok']
