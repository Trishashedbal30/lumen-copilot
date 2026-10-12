"""Artificial local HTTP fixtures test the API contract, not a live Baserow deployment."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse
import duckdb
import pytest
from backend.connectors.baserow import snapshot
from backend.data.import_retail import import_files

COLUMNS = ['InvoiceNo','StockCode','Quantity','InvoiceDate','UnitPrice','CustomerID','Country']
ROWS = [dict(zip(COLUMNS, ['1','A',2,'2011-10-01',3,None,'France']), id=1),
        dict(zip(COLUMNS, ['2','B',4,'2011-11-01',5,'9','Germany']), id=2)]

@pytest.fixture
def api():
    state = {'calls': [], 'mode': 'valid'}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state['calls'].append((self.path, self.headers.get('Authorization')))
            if state['mode']=='auth': self.send_response(403); self.end_headers(); return
            if '/fields/' in self.path:
                body = [{'id':i+1,'name':n,'type':'text'} for i,n in enumerate(COLUMNS)]
            else:
                page = int(parse_qs(urlparse(self.path).query)['page'][0])
                body = {'count':2, 'results': [ROWS[page-1]], 'next': 'https://untrusted.example/next' if page==1 else None}
                if state['mode']=='duplicate' and page==2: body['results']=[ROWS[0]]
                if state['mode']=='incomplete':body['next']=None
                if state['mode']=='changed' and page==2:body['count']=3
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
            self.wfile.write(json.dumps(body).encode())
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{server.server_port}',state
    server.shutdown();server.server_close();thread.join()

def test_paginated_http_snapshot_import_and_provenance(api,tmp_path):
    url,state=api;csv=tmp_path/'sales.csv'
    report=snapshot(url,123,'test-only-token',csv,page_size=1)
    assert report['rows']==2 and report['pages']==2
    assert len(state['calls'])==3
    assert all(token=='Token test-only-token' for _,token in state['calls'])
    assert all('untrusted.example' not in path for path,_ in state['calls'])
    db=tmp_path/'test.duckdb';imported=import_files([csv],db,provenance=report)
    assert imported['connector']['table_id']=='123'
    with duckdb.connect(str(db)) as con:
        assert con.execute('SELECT SUM(revenue) FROM uci_sales').fetchone()[0]==26
        assert json.loads(con.execute('SELECT report FROM uci_import_manifest').fetchone()[0])['connector']['rows']==2
    assert 'test-only-token' not in csv.with_suffix('.csv.provenance.json').read_text()

@pytest.mark.parametrize('mode',['auth','duplicate','incomplete','changed'])
def test_failed_snapshot_preserves_existing_file(api,tmp_path,mode):
    url,state=api;state['mode']=mode;csv=tmp_path/'sales.csv';csv.write_text('preserve')
    with pytest.raises(ValueError):snapshot(url,123,'test-only-token',csv,page_size=1)
    assert csv.read_text()=='preserve'

@pytest.mark.parametrize('url,table,token',[('http://remote.example',123,'token'),('https://user:pass@example.com',123,'token'),('https://example.com','../123','token'),('https://example.com',123,''),('https://example.com?token=secret',123,'token')])
def test_bad_configuration_rejected_without_network(tmp_path,url,table,token):
    with pytest.raises(ValueError):snapshot(url,table,token,tmp_path/'sales.csv')
