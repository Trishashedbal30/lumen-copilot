"""Judge-facing capability evidence; measured reports retain their original scope/date."""
import json
from pathlib import Path
from eval.provenance import source_hash

ROOT=Path(__file__).resolve().parents[1]

def build(meta,agent):
    current=source_hash()
    reports={}
    for name in ['latest','e2e','retail_independent','fresh_human_backend','fresh_human_browser','retail_live_llm','retail_live_browser','olist_independent','olist_browser','olist_live']:
        path=ROOT/'eval'/'reports'/(name+'.json')
        if not path.exists():
            reports[name]={'available':False};continue
        try:
            body=json.loads(path.read_text(encoding='utf-8-sig'))
        except (ValueError,OSError):
            reports[name]={'available':False,'error':'Unreadable report'};continue
        stamp=body.get('source_hash') if isinstance(body,dict) else None
        reports[name]={'available':True,'source_hash':stamp,'matches_current_source':stamp==current if stamp else None,
                       'body':body}
    return {'pages':len(meta['pages']),'widgets':sum(len(p['widgets']) for p in meta['pages'].values()),
            'data_views':len(meta['data_views']),'source_hash':current,'reports':reports,
            'datasets':meta.get('datasets',{}),'live_kpis':agent.live_kpis(),
            'connector':{'implemented':'Baserow read-only UCI table/field-schema snapshot',
                         'live_platform_verified':False,
                         'data_provenance':meta.get('datasets',{}).get('retail',{}).get('connector'),
                         'limitations':'No external page/widget/navigation control; no write-back or arbitrary database semantic model.'},
            'evaluation_limits':['Reused benchmark is not a fresh holdout.',
              'Three human task questions were known during development.',
              'Guardrail rate measures invalid final controls, not every model misunderstanding.',
              'Numerical evidence traceability is not proof of external causes.',
              'Rules latency, live model samples and browser timings have separate scopes.',
              'Unstamped reports retain historical scope; source-stamped mismatches are shown.']}
