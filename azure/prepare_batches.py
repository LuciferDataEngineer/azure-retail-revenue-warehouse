"""Flatten completed local batches for the Synapse staging contract; no Azure I/O."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

CLOUD_CONTRACT = 'retail-synapse-v1'
FIELDS = [
    ('business_date', pa.date32()), ('source_sha256', pa.string()), ('source_row', pa.int64()),
    ('invoice_no', pa.string()), ('stock_code', pa.string()), ('description', pa.string()),
    ('quantity', pa.int64()), ('invoice_at', pa.timestamp('us')), ('unit_price', pa.decimal128(18,4)),
    ('customer_id', pa.int64()), ('country', pa.string()), ('line_amount', pa.decimal128(18,2)),
    ('line_class', pa.string()), ('cancellation', pa.bool_()), ('cancellation_sign_mismatch', pa.bool_()),
    ('negative_price', pa.bool_()), ('product_key', pa.string()), ('customer_key', pa.int64()),
    ('country_key', pa.string()), ('is_valid', pa.bool_()), ('reasons_json', pa.string()), ('raw_payload', pa.string()),
]
SCHEMA = pa.schema(FIELDS, metadata={b'contract': CLOUD_CONTRACT.encode()})
LENGTHS = {'invoice_no':64, 'stock_code':64, 'description':1024, 'country':128,
           'line_class':24, 'product_key':64, 'country_key':64, 'reasons_json':4000, 'raw_payload':4000}


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def prepare(data_dir, manifest, output_dir):
    """Return ready manifests only after every source batch/hash/count is validated.

    This is an explicit shape adapter, not a second normalization implementation.
    It reuses local accepted/quarantine decisions and preserves all source rows.
    """
    data_dir=Path(data_dir);output_dir=Path(output_dir)
    if manifest['contract_version']!='retail-invoice-v1':
        raise ValueError('Unreviewed local contract')
    digest=manifest['source_sha256']
    if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Invalid source SHA')
    ready=[]
    for batch in manifest['dates']:
        date=batch['business_date'];source=data_dir/batch['path']
        if not source.resolve().is_relative_to(data_dir.resolve()):raise ValueError('Batch path escapes data directory')
        if sha256(source)!=batch['sha256']:raise ValueError('Batch SHA mismatch')
        input_table=pq.read_table(source)
        flat=[];accepted=0;net=Decimal('0.00');positive=Decimal('0.00');negative=Decimal('0.00')
        ordinals=set()
        for row in input_table.to_pylist():
            if str(row['business_date'])!=date or row['source_sha256']!=digest:
                raise ValueError('Mixed source/day in batch')
            if row['source_row'] in ordinals:raise ValueError('Duplicate physical source row')
            ordinals.add(row['source_row'])
            reasons=row.pop('reasons')
            row['is_valid']=len(reasons)==0
            row['reasons_json']=json.dumps(reasons,separators=(',',':'),ensure_ascii=False)
            for field,limit in LENGTHS.items():
                value=row.get(field)
                if value is not None and len(value.encode('utf-16-le'))//2>limit:
                    raise ValueError(f'{field} exceeds reviewed SQL character limit')
            flat.append({name:row.get(name) for name,_ in FIELDS})
            if row['is_valid']:
                accepted+=1;net+=row['line_amount']
                if row['line_amount']>0:positive+=row['line_amount']
                if row['line_amount']<0:negative+=row['line_amount']
        if len(flat)!=batch['rows'] or accepted!=batch['accepted_rows'] or len(flat)-accepted!=batch['quarantined_rows']:
            raise ValueError('Source-to-cloud batch conservation mismatch')
        rel=f'prepared/{CLOUD_CONTRACT}/{digest}/{date}.parquet'
        target=output_dir/rel;target.parent.mkdir(parents=True,exist_ok=True)
        pq.write_table(pa.Table.from_pylist(flat,schema=SCHEMA),target,compression='snappy',version='2.6')
        entry={'contract_version':CLOUD_CONTRACT,'source_sha256':digest,'business_date':date,
               'batch_path':rel,'batch_sha256':sha256(target),'source_batch_sha256':batch['sha256'],
               'rows':len(flat),'accepted_rows':accepted,'quarantined_rows':len(flat)-accepted,
               'positive_sales':str(positive),'negative_adjustments':str(negative),'net_sales':str(net)}
        ready.append(entry)
    if sum(x['rows'] for x in ready)!=manifest['raw_rows']:raise ValueError('Workbook row conservation mismatch')
    return ready
