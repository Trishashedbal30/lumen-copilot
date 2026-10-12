"""Import supplied UCI Online Retail II workbook or CSV exports; never generates transactions."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import uuid

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SOURCE_URL = 'https://archive.ics.uci.edu/dataset/502/online+retail+ii'
ATTRIBUTION = 'Chen, D. (2012). Online Retail II. UCI Machine Learning Repository. DOI:10.24432/C5CG6D. CC BY 4.0.'
ALIASES = {'invoice': ['Invoice', 'InvoiceNo'], 'stock_code': ['StockCode', 'Stock Code'],
           'description': ['Description'], 'quantity': ['Quantity', 'Qty'],
           'invoice_date': ['InvoiceDate', 'Invoice Date', 'Date'], 'unit_price': ['Price', 'UnitPrice', 'Unit Price'],
           'customer_id': ['Customer ID', 'CustomerID', 'Customer_ID'], 'country': ['Country']}
REQUIRED = {'invoice', 'stock_code', 'quantity', 'invoice_date', 'unit_price', 'country'}
POLICY = ('Revenue is gross merchandise sales: SUM(Quantity * UnitPrice) in GBP for positive quantity and price, '
          'excluding C-prefixed cancellation invoices, returns (negative quantity), invalid dates/numbers, '
          'missing invoice/stock code/country, and exact duplicate source rows. '
          'Missing customer IDs are retained; missing descriptions use StockCode. '
          'No inferred VAT, margin, exchange rate, shipping, or external causal claims.')

def normalize(frame):
    key = lambda x: re.sub(r'[^a-z0-9]', '', str(x).lower().lstrip('\ufeff'))
    mapping = {}
    for canonical, aliases in ALIASES.items():
        found = [c for c in frame.columns if key(c) in {key(a) for a in aliases}]
        if len(found) > 1:
            raise ValueError(f'Ambiguous aliases for {canonical}: {found}')
        if found:
            mapping[canonical] = found[0]
    missing = REQUIRED - mapping.keys()
    if missing:
        raise ValueError(f'Missing required columns: {sorted(missing)}. Actual columns: {list(frame.columns)}')
    out = pd.DataFrame({k: frame[v] for k,v in mapping.items()})
    for optional in ('description', 'customer_id'):
        if optional not in out:
            out[optional] = None
    return out, mapping

def read_sources(paths):
    frames, sources = [], []
    for path in paths:
        path = Path(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if path.suffix.lower() in ('.xlsx', '.xls'):
            sheets = pd.read_excel(path, sheet_name=None, dtype=object)
        elif path.suffix.lower() == '.csv':
            sheets = {'CSV': pd.read_csv(path, dtype=str, encoding='utf-8-sig', sep=None, engine='python')}
        else:
            raise ValueError('Supported input: .xlsx, .xls, .csv')
        for name, frame in sheets.items():
            canonical, mapping = normalize(frame)
            frames.append(canonical)
            sources.append({'file': path.name, 'sheet': str(name), 'sha256': digest,
                            'rows': len(frame), 'actual_columns': list(map(str,frame.columns)), 'aliases': mapping})
    if not frames:
        raise ValueError('No input data')
    return pd.concat(frames, ignore_index=True), sources

def prepare(raw, date_order='dayfirst'):
    raw = raw.copy()
    for col in ('invoice', 'stock_code', 'description', 'customer_id', 'country'):
        raw[col] = raw[col].astype('string').str.strip().replace('', pd.NA)
    duplicated = raw.duplicated(keep='first')
    cleaned = raw.copy()
    cleaned['quantity'] = pd.to_numeric(raw.quantity, errors='coerce')
    cleaned['unit_price'] = pd.to_numeric(raw.unit_price, errors='coerce')
    # Excel native datetimes are already unambiguous. CSV ambiguous numeric dates use the explicit CLI convention.
    cleaned['invoice_date'] = pd.to_datetime(raw.invoice_date, errors='coerce', format='mixed', dayfirst=date_order=='dayfirst')
    cleaned['revenue'] = cleaned.quantity * cleaned.unit_price
    reason = pd.Series('', index=raw.index, dtype='string')
    masks = [
      ('invalid_date', cleaned.invoice_date.isna()),
      ('invalid_numeric', ~np.isfinite(cleaned.quantity.fillna(np.nan)) | ~np.isfinite(cleaned.unit_price.fillna(np.nan)) | ~np.isfinite(cleaned.revenue.fillna(np.nan))),
      ('missing_required_value', cleaned[['invoice','stock_code','country']].isna().any(axis=1)),
      ('duplicate', duplicated),
      ('cancellation', cleaned.invoice.str.upper().str.startswith('C', na=False)),
      ('return', cleaned.quantity < 0),
      ('nonpositive_quantity_or_price', (cleaned.quantity <= 0) | (cleaned.unit_price <= 0)),
    ]
    for label, mask in masks:
        reason.loc[mask & reason.eq('')] = label
    cleaned['exclusion_reason'] = reason
    missing_description = cleaned.description.isna()
    cleaned['description'] = cleaned.description.fillna(cleaned.stock_code)
    cleaned['date'] = cleaned.invoice_date.dt.date
    # Stable product identity is StockCode, even when descriptions change.
    cleaned['retail_product'] = cleaned.stock_code
    accepted = cleaned.loc[reason.eq('')].copy()
    if accepted.empty:
        raise ValueError('No eligible sales rows remain after cleaning; existing dataset was not changed.')
    report = {'input_rows': len(raw), 'imported_rows': len(accepted), 'excluded_rows': int(reason.ne('').sum()),
              'cleaning_exclusions': dict(Counter(reason[reason.ne('')].tolist())),
              'missing_customer_ids_retained': int(accepted.customer_id.isna().sum()),
              'missing_descriptions_retained': int(missing_description[reason.eq('')].sum()),
              'date_start': str(accepted.date.min()), 'date_end': str(accepted.date.max()),
              'available_months': sorted(accepted.invoice_date.dt.strftime('%Y-%m').unique().tolist()),
              'currency': 'GBP', 'dataset': 'UCI Online Retail II (imported source)',
              'source_url': SOURCE_URL, 'attribution': ATTRIBUTION, 'cleaning_policy': POLICY,
              'csv_date_order': date_order, 'imported_at': datetime.now(timezone.utc).isoformat()}
    return cleaned, accepted, report

def import_files(paths, db_path=None, date_order='dayfirst', provenance=None):
    raw, sources = read_sources(paths)
    cleaned, accepted, report = prepare(raw, date_order)
    report['sources'] = sources
    if provenance is not None:
        report['connector'] = provenance
    output = Path(db_path or ROOT/'data'/'uci_retail.duckdb')
    output.parent.mkdir(parents=True,exist_ok=True)
    stage = output.with_name(output.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with duckdb.connect(str(stage)) as con:
            con.register('source_frame', cleaned)
            con.register('sales_frame', accepted)
            con.execute('CREATE TABLE uci_import_rows AS SELECT * FROM source_frame')
            con.execute('CREATE TABLE uci_sales AS SELECT * FROM sales_frame')
            con.execute('CREATE TABLE uci_import_manifest (report VARCHAR)')
            con.execute('INSERT INTO uci_import_manifest VALUES (?)', [json.dumps(report)])
        stage.replace(output)
    except Exception:
        if stage.exists(): stage.unlink()
        raise
    return report

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('files',nargs='+',help='Workbook (all sheets) or one/more CSV exports')
    ap.add_argument('--db',default=str(ROOT/'data'/'uci_retail.duckdb'))
    ap.add_argument('--date-order', choices=['dayfirst','monthfirst'], default='dayfirst')
    a=ap.parse_args()
    try:
        print(json.dumps(import_files(a.files,a.db,a.date_order),indent=2))
        print('Import complete. Restart Lumen to refresh catalog, dimensions and bounds.')
    except Exception as exc:
        ap.exit(1, f'Import failed: {exc}\nStop Lumen before replacing an active dataset.\n')
if __name__=='__main__': main()
