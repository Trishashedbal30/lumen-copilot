"""Explicitly artificial importer fixtures; these rows are never demo data."""
from decimal import Decimal
import json
import duckdb
import pandas as pd
import pytest
from backend.data.import_retail import import_files, normalize, prepare

def fixture():
    return pd.DataFrame({'Invoice':['1','2','C3','4','5','6','7','8','9','1'],
       'StockCode':['A','B','A','B','A','B','A','A','A','A'],
       'Description':['a','b','a','b',None,'b','a','a','a','a'],
       'Quantity':[2,3,-1,-2,1,1,'bad',1,1,2],
       'Price':['1.20','2.50','1.20','2.50','1.20',0,1,1,1,'1.20'],
       'InvoiceDate':['2011-01-05','2011-02-06','2011-02-06','2011-02-06','2011-02-06','2011-02-06','2011-02-06','bad','2011-02-06','2011-01-05'],
       'Customer ID':[None]*10,'Country':['UK','France','UK','France','UK','UK','UK','UK',None,'UK']})

def test_import_aliases_cleaning_and_independent_total(tmp_path):
    f=fixture();path=tmp_path/'fixture.csv';f.to_csv(path,index=False)
    report=import_files([path],tmp_path/'retail.duckdb')
    assert report['input_rows']==10 and report['imported_rows']==3 and report['excluded_rows']==7
    assert report['cleaning_exclusions']=={'cancellation':1,'return':1,'nonpositive_quantity_or_price':1,'invalid_numeric':1,'invalid_date':1,'missing_required_value':1,'duplicate':1}
    with duckdb.connect(str(tmp_path/'retail.duckdb'),read_only=True) as con:
        value=con.execute('SELECT SUM(revenue) FROM uci_sales').fetchone()[0]
        assert Decimal(str(value)) == Decimal('2')*Decimal('1.20')+Decimal('3')*Decimal('2.50')+Decimal('1.20')
        assert con.execute("SELECT description FROM uci_sales WHERE invoice='5'").fetchone()[0]=='A'
        assert con.execute('SELECT COUNT(*) FROM uci_import_rows').fetchone()[0]==10
    assert report['missing_customer_ids_retained']==3 and report['missing_descriptions_retained']==1

def test_workbook_all_sheets_and_new_aliases(tmp_path):
    f=fixture().iloc[:2].rename(columns={'Invoice':'InvoiceNo','Price':'UnitPrice','Customer ID':'CustomerID'})
    path=tmp_path/'fixture.xlsx'
    with pd.ExcelWriter(path) as writer:
        f.iloc[:1].to_excel(writer,sheet_name='2009-2010',index=False)
        f.iloc[1:].to_excel(writer,sheet_name='2010-2011',index=False)
    report=import_files([path],tmp_path/'data.duckdb')
    assert report['imported_rows']==2 and len(report['sources'])==2

def test_invalid_import_preserves_previous_database(tmp_path):
    path=tmp_path/'fixture.csv';fixture().iloc[:2].to_csv(path,index=False)
    db=tmp_path/'retail.duckdb';import_files([path],db);before=db.read_bytes()
    pd.DataFrame({'unsupported':[1]}).to_csv(path,index=False)
    with pytest.raises(ValueError,match='Missing required columns'): import_files([path],db)
    assert db.read_bytes()==before

def test_empty_import_does_not_claim_real_data(tmp_path):
    f=fixture().iloc[2:3];path=tmp_path/'cancelled.csv';f.to_csv(path,index=False)
    with pytest.raises(ValueError,match='No eligible sales'): import_files([path],tmp_path/'absent.duckdb')
    assert not (tmp_path/'absent.duckdb').exists()


def test_same_agent_real_workflow_and_validation_in_isolated_process(tmp_path):
    import os, subprocess, sys
    # Artificial fixture remains in pytest's temporary directory.
    f=fixture().iloc[:2].copy()
    f.loc[0,"InvoiceDate"]="2011-01-01"
    f.loc[1,"InvoiceDate"]="2011-12-31"
    source=tmp_path/"fixture.csv";f.to_csv(source,index=False)
    db=tmp_path/"fixture.duckdb";import_files([source],db)
    script = r"""
from backend.main import AGENT, app
from fastapi.testclient import TestClient
client=TestClient(app)
state=AGENT.planner.default_state('uci.sales.overview')
assert state['date_range']['start']=='2011-01-01'
for question in ['Show monthly revenue for 2011', 'Top 5 countries by revenue in 2011', 'Top 5 products by revenue in 2011', 'Compare December 2011 vs January 2011 revenue']:
    r=AGENT.handle('retail-fixture',question,state)
    assert r['kind']=='act', (question,r)
    assert r['target_state']['page_id']=='uci.sales.overview'
    if question.startswith('Top 5'):
        highlighted=[a['widget_id'] for a in r['actions'] if a['type']=='highlight'][0]
        widget=next(w for w in AGENT.meta['pages']['uci.sales.overview']['widgets'] if w['id']==highlighted)
        assert widget['dimensions']==(['country'] if 'countries' in question else ['retail_product'])
    assert all(f['view']=='retail' for f in r['facts'])
    assert AGENT.verify(r['session_id'],r['turn_id'],r['target_state'])['ok']
    assert client.post('/api/render',json={'state':r['target_state']}).status_code==200
    state=r['target_state']
r=AGENT.handle('retail-fixture','what about France?',state)
assert r['kind']=='act' and r['target_state']['filters']['country']==['France']
r=AGENT.handle('retail-fixture','undo',r['target_state']); assert r['target_state']==state
assert AGENT.handle(None,'Show profit in 2011',state)['kind']=='clarify'
assert AGENT.handle(None,'Show revenue for 2026',state)['kind']=='clarify'
bad=dict(state,filters={'country':['Atlantis']})
assert client.post('/api/render',json={'state':bad}).status_code==422
assert not [w for w in client.post('/api/render',json={'state':state}).json()['widgets'] if w.get('error')]
"""
    env=dict(os.environ,LUMEN_RETAIL_DB=str(db),LUMEN_AGENT_MODE='rules')
    run=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=60)
    assert run.returncode==0,run.stdout+run.stderr
