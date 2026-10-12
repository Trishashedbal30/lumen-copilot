"""Snapshot a Baserow table containing a genuine UCI Online Retail II export.
Credentials stay in BASEROW_TOKEN. No writes to Baserow; no replacement of app data
unless the caller explicitly supplies --import-db.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import uuid
from urllib.parse import urlparse

import pandas as pd
import requests
from backend.data.import_retail import normalize, import_files

DOCS = 'https://baserow.io/user-docs/database-api'


def snapshot(base_url, table_id, token, output, *, page_size=200, max_rows=2000000, client=None):
    base_url = base_url.rstrip('/')
    parsed = urlparse(base_url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Use an HTTP(S) API base URL without credentials, query or fragment.')
    if parsed.scheme != 'https' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Remote API connections require HTTPS; local HTTP is supported.')
    if not re.fullmatch(r'[1-9][0-9]*', str(table_id)):
        raise ValueError('Baserow table ID must be a positive integer.')
    if not token or '\n' in token or '\r' in token:
        raise ValueError('Set BASEROW_TOKEN to a read-only table token.')
    if not 1 <= page_size <= 200 or max_rows < 1:
        raise ValueError('Page size must be 1..200; row limit must be positive.')
    headers = {'Authorization': 'Token ' + token}
    own_client = client is None
    client = client or requests.Session()
    def get(path, params=None):
        # Do not follow redirects with an authentication header or log server bodies.
        response = client.get(base_url + path, headers=headers, params=params, timeout=(5, 30), allow_redirects=False)
        if response.status_code != 200:
            raise ValueError(f'Baserow HTTP {response.status_code}; check API URL, table ID and read permission.')
        try:
            return response.json()
        except ValueError:
            raise ValueError('Baserow returned invalid JSON.') from None
    try:
        fields = get(f'/api/database/fields/table/{table_id}/')
        if not isinstance(fields, list) or not fields or any(not isinstance(f, dict) or not isinstance(f.get('name'), str) for f in fields):
            raise ValueError('Invalid Baserow field schema.')
        names = [f['name'] for f in fields]
        if len(set(names)) != len(names):
            raise ValueError('Duplicate Baserow field names.')
        normalize(pd.DataFrame(columns=names))  # Required UCI schema and alias validation before downloading.
        rows, seen, count, page = [], set(), None, 1
        while True:
            body = get(f'/api/database/rows/table/{table_id}/', {'user_field_names': 'true', 'size': page_size, 'page': page})
            if not isinstance(body, dict) or not isinstance(body.get('results'), list) or not isinstance(body.get('count'), int) or body['count'] < 0:
                raise ValueError('Invalid Baserow row response.')
            if count is None:
                count = body['count']
                if count > max_rows:
                    raise ValueError(f'Table has {count} rows, exceeding the explicit limit {max_rows}; no partial import.')
            elif count != body['count']:
                raise ValueError('Table changed while reading; retry when edits are paused.')
            batch = body['results']
            for row in batch:
                if not isinstance(row, dict) or not isinstance(row.get('id'), int) or row['id'] in seen:
                    raise ValueError('Invalid or repeated row ID; refusing an incomplete snapshot.')
                seen.add(row['id'])
                record = {name: row.get(name) for name in names}
                if any(isinstance(value, (dict, list)) for value in record.values()):
                    raise ValueError('Use scalar text/date/number UCI fields; linked/select objects require explicit mapping.')
                rows.append(record)
            if len(rows) > count or len(rows) > max_rows:
                raise ValueError('Pagination count mismatch; no snapshot written.')
            # Construct page URLs ourselves: never send credentials to a server-provided next URL.
            if not body.get('next'):
                if len(rows) != count:
                    raise ValueError('Incomplete pagination; no snapshot written.')
                break
            if not batch or len(rows) >= count:
                raise ValueError('Inconsistent pagination; no snapshot written.')
            page += 1
        if not rows:
            raise ValueError('Empty table; existing files remain unchanged.')
        frame = pd.DataFrame(rows, columns=names)
        normalize(frame)
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        stage = output.with_name(output.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            frame.to_csv(stage, index=False, encoding='utf-8-sig')
            digest = hashlib.sha256(stage.read_bytes()).hexdigest()
            stage.replace(output)
        finally:
            if stage.exists(): stage.unlink()
        report = {'connector': 'baserow', 'scope': 'read-only UCI table data and field schema; not platform UI control',
                  'api_base_url': base_url, 'table_id': str(table_id), 'rows': len(rows), 'pages': page,
                  'fields': [{'id': f.get('id'), 'name': f['name'], 'type': f.get('type')} for f in fields],
                  'snapshot_sha256': digest, 'fetched_at': datetime.now(timezone.utc).isoformat(),
                  'snapshot_consistency': 'Count and unique IDs checked; edits with unchanged count require a platform snapshot/freeze.',
                  'documentation': DOCS}
        output.with_suffix(output.suffix + '.provenance.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        return report
    finally:
        if own_client: client.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--url', required=True, help='API base, e.g. https://api.baserow.io or http://localhost:8080')
    ap.add_argument('--table', required=True)
    ap.add_argument('--output', default='data/connectors/baserow_uci.csv')
    ap.add_argument('--max-rows', type=int, default=2000000)
    ap.add_argument('--import-db', help='Explicit destination DuckDB; stop Lumen before replacing active data.')
    ap.add_argument('--source-uci', action='store_true', required=True, help='Confirm the table is an actual UCI Online Retail II export, not arbitrary/generated records.')
    a = ap.parse_args()
    try:
        report = snapshot(a.url, a.table, os.environ.get('BASEROW_TOKEN'), a.output, max_rows=a.max_rows)
        if a.import_db:
            imported = import_files([a.output], a.import_db, provenance=report)
            report['import'] = imported
        print(json.dumps(report, indent=2))
    except (ValueError, OSError, requests.RequestException) as exc:
        # Request exception strings can contain URLs; never echo headers/token/server bodies.
        ap.exit(1, f'Connector failed: {exc if isinstance(exc, ValueError) else type(exc).__name__}\n')

if __name__ == '__main__': main()
