"""Original local daily ELT. Serialize writers and report publishers per data_dir."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import uuid
import zipfile

import duckdb
import openpyxl
import pyarrow as pa
import pyarrow.parquet as pq

LOG = logging.getLogger(__name__)
CONTRACT_VERSION = 'retail-invoice-v1'
HEADERS = ('InvoiceNo','StockCode','Description','Quantity','InvoiceDate','UnitPrice','CustomerID','Country')
MAX_SOURCE_BYTES = 40 * 1024 * 1024
MAX_EXPANDED_BYTES = 250 * 1024 * 1024
MAX_SOURCE_ROWS = 2_000_000
BUFFER_ROWS = 8192
MAX_BATCH_DAYS = 3660
SOURCE_URL = 'https://archive.ics.uci.edu/static/public/352/online%2Bretail.zip'
BATCH_SCHEMA = pa.schema([
    ('business_date',pa.date32()),('source_sha256',pa.string()),('source_row',pa.int64()),
    ('invoice_no',pa.string()),('stock_code',pa.string()),('description',pa.string()),
    ('quantity',pa.int64()),('invoice_at',pa.timestamp('us')),('unit_price',pa.decimal128(18,4)),
    ('customer_id',pa.int64()),('country',pa.string()),('line_amount',pa.decimal128(18,2)),
    ('line_class',pa.string()),('cancellation',pa.bool_()),('cancellation_sign_mismatch',pa.bool_()),
    ('negative_price',pa.bool_()),('product_key',pa.string()),('customer_key',pa.int64()),
    ('country_key',pa.string()),('reasons',pa.list_(pa.string())),('raw_payload',pa.string()),
])


class ContractError(ValueError):
    """Source/batch is incompatible with the declared contract; prior facts survive."""


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _default(value):
    if isinstance(value,(date,datetime,Decimal)):
        return str(value)
    raise TypeError(type(value).__name__)


def _json(value):
    return json.dumps(value,indent=2,default=_default,allow_nan=False)+'\n'


def _sha(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            result.update(block)
    return result.hexdigest()


def _key(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def _source_url(value):
    if value is None:
        return None
    parsed=urlsplit(value)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ContractError('source_url must be HTTPS without credentials, query or fragment')
    return value


def _day(value):
    if isinstance(value,date) and not isinstance(value,datetime):
        return value
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
        raise ContractError('business date must be YYYY-MM-DD')
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError('invalid business date') from exc


def _check_zip(path):
    if Path(path).stat().st_size > MAX_SOURCE_BYTES:
        raise ContractError('compressed source exceeds 40 MiB limit')
    try:
        with zipfile.ZipFile(path) as archive:
            files=archive.infolist()
            if len(files)>100 or sum(f.file_size for f in files)>MAX_EXPANDED_BYTES:
                raise ContractError('archive exceeds member/expanded-byte limits')
            if any(f.flag_bits & 1 for f in files):
                raise ContractError('encrypted archive is unsupported')
    except zipfile.BadZipFile as exc:
        raise ContractError('source is not a valid ZIP/XLSX archive') from exc


def _archive(file_path,data_dir,source_url):
    raw=data_dir/'raw';raw.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.capture-',suffix='.xlsx',dir=raw)
    temporary=Path(name);digest=hashlib.sha256();size=0
    try:
        with os.fdopen(fd,'wb') as output,Path(file_path).open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):
                size+=len(block)
                if size>MAX_SOURCE_BYTES:raise ContractError('source exceeds 40 MiB limit')
                digest.update(block);output.write(block)
            output.flush();os.fsync(output.fileno())
        if not size:raise ContractError('empty source')
        sha=digest.hexdigest();destination=raw/sha;destination.mkdir(exist_ok=True)
        stored=destination/'source.xlsx';manifest=destination/'manifest.json'
        if stored.exists():
            if _sha(stored)!=sha:raise ContractError('retained workbook checksum mismatch')
            temporary.unlink()
        else:os.replace(temporary,stored)
        if manifest.exists():
            metadata=json.loads(manifest.read_text())
            if metadata.get('source_sha256')!=sha or metadata.get('source_bytes')!=size:
                raise ContractError('raw manifest identity mismatch')
        else:
            metadata={'source_sha256':sha,'source_bytes':size,'source_url':source_url,
                      'captured_at':_utc(),'raw_relative_path':stored.relative_to(data_dir).as_posix()}
            temp=destination/'.manifest.tmp';temp.write_text(_json(metadata));os.replace(temp,manifest)
        return stored,metadata
    finally:temporary.unlink(missing_ok=True)


def _text(value):
    if isinstance(value,bool) or value is None:return None
    if isinstance(value,(int,float,Decimal)):
        try:
            d=Decimal(str(value))
            if not d.is_finite() or d!=d.to_integral_value():return None
            return str(int(d))
        except (ValueError,InvalidOperation):return None
    if not isinstance(value,str):return None
    value=value.strip()
    return value if value and not value.startswith('=') else None


def _integer(value,*,positive=False):
    if isinstance(value,bool) or value is None:return None
    try:
        number=Decimal(str(value))
        if not number.is_finite() or number!=number.to_integral_value():return None
        if abs(number)>9223372036854775807 or (positive and number<=0):return None
        return int(number)
    except (ValueError,TypeError,InvalidOperation):return None


def _price(value):
    if isinstance(value,bool) or value is None:return None
    try:
        with localcontext() as context:
            context.prec=50
            price=Decimal(str(value))
            if not price.is_finite():return None
            price=price.quantize(Decimal('.0001'),rounding=ROUND_HALF_UP)
            return price if abs(price)<Decimal('100000000000000') else None
    except (ValueError,TypeError,InvalidOperation):return None


def _raw(value):
    if isinstance(value,(date,datetime,Decimal)):return str(value)
    if isinstance(value,float) and not math.isfinite(value):return str(value)
    return value


def normalize_row(values,source_sha256,source_row):
    """Normalize one data row. Undatable rows reject the workbook, not disappear."""
    row=dict(zip(HEADERS,values))
    when=row['InvoiceDate']
    if not isinstance(when,datetime) or when.tzinfo is not None:
        raise ContractError(f'worksheet row {source_row}: InvoiceDate must be a naive datetime')
    invoice=_text(row['InvoiceNo']);stock=_text(row['StockCode']);country=_text(row['Country'])
    description=None if row['Description'] is None else str(row['Description']).strip() or None
    quantity=_integer(row['Quantity']);price=_price(row['UnitPrice'])
    customer=None if row['CustomerID'] is None else _integer(row['CustomerID'],positive=True)
    reasons=[]
    if invoice is None:reasons.append('invalid_invoice_no')
    if stock is None:reasons.append('invalid_stock_code')
    if country is None:reasons.append('invalid_country')
    if quantity is None:reasons.append('invalid_quantity')
    if price is None:reasons.append('invalid_unit_price')
    if row['CustomerID'] is not None and customer is None:reasons.append('invalid_customer_id')
    amount=None
    if quantity is not None and price is not None:
        with localcontext() as context:
            context.prec=60
            amount=(price*quantity).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            if abs(amount)>=Decimal('10000000000000000'):
                amount=None;reasons.append('line_amount_overflow')
    cancellation=bool(invoice and invoice.upper().startswith('C'))
    return {
        'business_date':when.date(),'source_sha256':source_sha256,'source_row':source_row,
        'invoice_no':invoice,'stock_code':stock,'description':description,'quantity':quantity,
        'invoice_at':when,'unit_price':price,'customer_id':customer,'country':country,
        'line_amount':amount,'line_class':None if amount is None else ('positive_sales' if amount>0 else 'negative_adjustment' if amount<0 else 'zero_value'),
        'cancellation':cancellation,'cancellation_sign_mismatch':quantity is not None and cancellation!=(quantity<0),
        'negative_price':price is not None and price<0,'product_key':_key([stock,description]) if stock is not None else None,
        'customer_key':customer or 0,'country_key':_key(country) if country is not None else None,
        'reasons':reasons,'raw_payload':json.dumps({k:_raw(v) for k,v in row.items()},sort_keys=True,ensure_ascii=False,allow_nan=False),
    }


def _publish_batch_pointer(data_dir,sha):
    path=data_dir/'batches'/'latest.json';temporary=path.with_name('.latest.tmp')
    temporary.write_text(_json({'source_sha256':sha,'manifest':f'batches/{sha}/manifest.json'}));os.replace(temporary,path)


def split_workbook(file_path,data_dir,source_url=None):
    """Retain exact workbook bytes and atomically expose a complete daily delivery set."""
    data_dir=Path(data_dir);source_url=_source_url(source_url)
    raw,metadata=_archive(file_path,data_dir,source_url)
    _check_zip(raw)
    sha=metadata['source_sha256'];batches=data_dir/'batches';batches.mkdir(exist_ok=True)
    completed=batches/sha
    if completed.exists():
        result=json.loads((completed/'manifest.json').read_text())
        _verify_manifest(data_dir,result)
        _publish_batch_pointer(data_dir,sha)
        return result
    temporary=batches/('.build-'+uuid.uuid4().hex);temporary.mkdir()
    workbook=None;counts=defaultdict(lambda:[0,0,0]);buffers=defaultdict(list);chunks=defaultdict(list)
    parts=temporary/'.parts';parts.mkdir();buffered_total=0
    def flush(day):
        nonlocal buffered_total
        if not buffers[day]:return
        part=parts/f'{day}-{len(chunks[day]):06d}.parquet'
        pq.write_table(pa.Table.from_pylist(buffers[day],schema=BATCH_SCHEMA),part,compression='snappy',version='2.6')
        chunks[day].append(part);buffered_total-=len(buffers[day]);buffers[day].clear()
    try:
        workbook=openpyxl.load_workbook(raw,read_only=True,data_only=False)
        if len(workbook.worksheets)!=1:raise ContractError('exactly one worksheet is required')
        sheet=workbook.worksheets[0];rows=sheet.iter_rows(values_only=True)
        header=next(rows,None)
        if header!=HEADERS:raise ContractError('workbook must contain exactly the eight ordered UCI headers')
        total=0
        for excel_row,values in enumerate(rows,2):
            if len(values)!=len(HEADERS):raise ContractError('unexpected row width')
            total+=1
            if total>MAX_SOURCE_ROWS:raise ContractError('workbook exceeds row limit')
            # Formula strings in required non-date fields are invalid identifiers/numbers,
            # not evaluated. Description text can contain any literal source text.
            normalized=normalize_row(values,sha,excel_row)
            day=normalized['business_date'].isoformat();buffers[day].append(normalized);buffered_total+=1
            counts[day][0]+=1;counts[day][1 if not normalized['reasons'] else 2]+=1
            if len(counts)>MAX_BATCH_DAYS:raise ContractError('workbook exceeds distinct-date limit')
            if buffered_total>=BUFFER_ROWS:
                flush(max(buffers,key=lambda d:(len(buffers[d]),d)))
        if not total:raise ContractError('empty workbook cannot delete a previous source')
        for day in sorted(buffers):flush(day)
        descriptors=[]
        for day,(count,accepted,quarantined) in sorted(counts.items()):
            p=temporary/f'{day}.parquet'
            # One final writer and one bounded chunk reader at a time, independent
            # of date cardinality. Temporary chunks are never visible deliveries.
            with pq.ParquetWriter(p,BATCH_SCHEMA,compression='snappy',version='2.6') as writer:
                for part in chunks[day]:
                    with pq.ParquetFile(part) as reader:
                        for batch in reader.iter_batches(batch_size=BUFFER_ROWS):
                            writer.write_table(pa.Table.from_batches([batch],schema=BATCH_SCHEMA))
                    part.unlink()
            descriptors.append({'business_date':day,'path':f'batches/{sha}/{day}.parquet','sha256':_sha(p),
                                'rows':count,'accepted_rows':accepted,'quarantined_rows':quarantined})
        parts.rmdir()
        result={**metadata,'contract_version':CONTRACT_VERSION,'worksheet':sheet.title,
                'raw_rows':total,'dates':descriptors,'simulation':'Historical invoices partitioned by recorded date; deliveries are simulated, not live.'}
        (temporary/'manifest.json').write_text(_json(result));os.replace(temporary,completed)
        _publish_batch_pointer(data_dir,sha)
        LOG.info('workbook_split source_sha256=%s rows=%s dates=%s',sha,total,len(descriptors))
        return result
    except (zipfile.BadZipFile,openpyxl.utils.exceptions.InvalidFileException) as exc:
        raise ContractError('invalid workbook') from exc
    finally:
        if workbook is not None:workbook.close()
        if temporary.exists():shutil.rmtree(temporary)


def _verify_manifest(data_dir,manifest):
    sha=manifest.get('source_sha256','')
    if not re.fullmatch('[a-f0-9]{64}',sha) or manifest.get('contract_version')!=CONTRACT_VERSION:
        raise ContractError('batch manifest identity/contract mismatch')
    if manifest.get('raw_relative_path')!=f'raw/{sha}/source.xlsx':raise ContractError('raw manifest path mismatch')
    if _sha(data_dir/manifest['raw_relative_path'])!=sha:raise ContractError('retained workbook checksum mismatch')
    dates=manifest.get('dates',[])
    if not dates or len({d['business_date'] for d in dates})!=len(dates):raise ContractError('duplicate or empty batch dates')
    total=0
    for entry in dates:
        day=_day(entry['business_date']).isoformat()
        if entry['path']!=f'batches/{sha}/{day}.parquet':raise ContractError('unexpected batch path')
        if entry['rows']!=entry['accepted_rows']+entry['quarantined_rows'] or entry['rows']<=0:
            raise ContractError('manifest conservation mismatch')
        total+=entry['rows']
    if total!=manifest['raw_rows']:raise ContractError('workbook/batch manifest row mismatch')


def _connect(data_dir,read_only=False):
    data_dir.mkdir(parents=True,exist_ok=True)
    con=duckdb.connect(str(data_dir/'warehouse.duckdb'),read_only=read_only)
    try:
        con.execute('SET threads=2');con.execute("SET memory_limit='1GB'")
        if not read_only:
            con.execute('SET temp_directory=?',[str(data_dir/'duckdb-tmp')]);_initialize(con)
        return con
    except Exception:
        con.close();raise


def _initialize(con):
    con.execute('''
    CREATE TABLE IF NOT EXISTS contract_metadata(contract_version VARCHAR PRIMARY KEY);
    INSERT INTO contract_metadata SELECT 'retail-invoice-v1' WHERE NOT EXISTS(SELECT 1 FROM contract_metadata);
    CREATE TABLE IF NOT EXISTS run_audit(run_id VARCHAR PRIMARY KEY,business_date DATE,source_sha256 VARCHAR,
      started_at TIMESTAMP NOT NULL,finished_at TIMESTAMP,status VARCHAR NOT NULL,replayed BOOLEAN DEFAULT false,error_type VARCHAR);
    CREATE TABLE IF NOT EXISTS workbook_sources(source_sha256 VARCHAR PRIMARY KEY,source_url VARCHAR,captured_at TIMESTAMP,
      source_bytes BIGINT,worksheet VARCHAR,raw_rows BIGINT,raw_relative_path VARCHAR,manifest_relative_path VARCHAR);
    CREATE TABLE IF NOT EXISTS batch_versions(business_date DATE,source_sha256 VARCHAR,raw_rows BIGINT,accepted_rows BIGINT,
      quarantined_rows BIGINT,parquet_sha256 VARCHAR,committed_at TIMESTAMP,PRIMARY KEY(business_date,source_sha256),
      CHECK(raw_rows=accepted_rows+quarantined_rows));
    CREATE TABLE IF NOT EXISTS current_batches(business_date DATE PRIMARY KEY,source_sha256 VARCHAR NOT NULL);
    CREATE TABLE IF NOT EXISTS dim_customer(customer_key BIGINT PRIMARY KEY,customer_id BIGINT);
    INSERT INTO dim_customer SELECT 0,NULL WHERE NOT EXISTS(SELECT 1 FROM dim_customer WHERE customer_key=0);
    CREATE TABLE IF NOT EXISTS dim_product(product_key VARCHAR PRIMARY KEY,stock_code VARCHAR,description VARCHAR);
    CREATE TABLE IF NOT EXISTS dim_country(country_key VARCHAR PRIMARY KEY,country VARCHAR);
    CREATE TABLE IF NOT EXISTS dim_date(business_date DATE PRIMARY KEY,year INTEGER,month INTEGER,day INTEGER);
    CREATE TABLE IF NOT EXISTS fact_sales(business_date DATE,source_sha256 VARCHAR,source_row BIGINT,invoice_no VARCHAR,
      product_key VARCHAR,customer_key BIGINT,country_key VARCHAR,invoice_at TIMESTAMP,quantity BIGINT,
      unit_price DECIMAL(18,4),line_amount DECIMAL(18,2),line_class VARCHAR,cancellation BOOLEAN,
      cancellation_sign_mismatch BOOLEAN,negative_price BOOLEAN,candidate_duplicate BOOLEAN,
      PRIMARY KEY(business_date,source_sha256,source_row));
    CREATE INDEX IF NOT EXISTS sales_customer_date ON fact_sales(customer_key,business_date);
    CREATE TABLE IF NOT EXISTS quarantine(business_date DATE,source_sha256 VARCHAR,source_row BIGINT,
      reasons VARCHAR[],raw_payload VARCHAR,PRIMARY KEY(business_date,source_sha256,source_row));
    CREATE VIEW IF NOT EXISTS daily_revenue AS SELECT business_date,country_key,
      COUNT(*) AS line_count,COUNT(DISTINCT invoice_no) AS invoice_count,
      SUM(quantity) AS signed_units,SUM(CASE WHEN line_amount>0 THEN line_amount ELSE 0 END) AS positive_sales,
      SUM(CASE WHEN line_amount<0 THEN line_amount ELSE 0 END) AS negative_adjustments,
      SUM(line_amount) AS net_revenue,COUNT(*) FILTER(WHERE line_amount=0) AS zero_value_lines,
      COUNT(*) FILTER(WHERE customer_key=0) AS unknown_customer_lines,
      COUNT(*) FILTER(WHERE candidate_duplicate) AS candidate_duplicate_lines,
      COUNT(*) FILTER(WHERE cancellation) AS cancellation_lines,
      COUNT(*) FILTER(WHERE cancellation_sign_mismatch) AS cancellation_sign_mismatch_lines,
      COUNT(*) FILTER(WHERE negative_price) AS negative_price_lines
      FROM fact_sales GROUP BY business_date,country_key;
    CREATE VIEW IF NOT EXISTS current_batch_versions AS SELECT b.* FROM batch_versions b
      JOIN current_batches c USING(business_date,source_sha256);
    CREATE VIEW IF NOT EXISTS quality_summary AS SELECT business_date,reason,COUNT(*) AS row_count
      FROM quarantine,UNNEST(reasons) r(reason) GROUP BY business_date,reason;
    ''')
    if con.execute('SELECT * FROM contract_metadata').fetchall()!=[(CONTRACT_VERSION,)]:
        raise ContractError('existing warehouse contract differs; reviewed migration or separate data_dir required')


def _hook(callback,phase):
    if callback:callback(phase)


def _load_one(con,data_dir,manifest,entry,allow_revert,failure_hook):
    day=_day(entry['business_date']);sha=manifest['source_sha256'];run_id=str(uuid.uuid4());in_tx=False
    con.execute("INSERT INTO run_audit VALUES(?,?,?,?,NULL,'running',false,NULL)",[run_id,day,sha,_utc()])
    try:
        path=data_dir/entry['path']
        if _sha(path)!=entry['sha256']:raise ContractError('daily Parquet checksum mismatch')
        with pq.ParquetFile(path) as parquet:
            if not parquet.schema_arrow.equals(BATCH_SCHEMA) or parquet.metadata.num_rows!=entry['rows']:
                raise ContractError('daily Parquet schema/row count mismatch')
        current=con.execute('SELECT source_sha256 FROM current_batches WHERE business_date=?',[day]).fetchone()
        previous=con.execute('SELECT raw_rows,accepted_rows,quarantined_rows FROM batch_versions WHERE business_date=? AND source_sha256=?',[day,sha]).fetchone()
        replayed=current==(sha,)
        if replayed:
            if previous!=(entry['rows'],entry['accepted_rows'],entry['quarantined_rows']):raise ContractError('committed batch metadata mismatch')
        else:
            if previous and not allow_revert:raise ContractError('historical source requires allow_revert=True')
            con.execute('CREATE OR REPLACE TEMP TABLE staged AS SELECT * FROM read_parquet(?,hive_partitioning=false)',[str(path)])
            check=con.execute('''SELECT count(*),count(DISTINCT source_row),count(*) FILTER(WHERE business_date<>? OR source_sha256<>? OR source_row<2 OR source_row IS NULL),
              count(*) FILTER(WHERE len(reasons)=0),count(*) FILTER(WHERE len(reasons)>0) FROM staged''',[day,sha]).fetchone()
            if check!=(entry['rows'],entry['rows'],0,entry['accepted_rows'],entry['quarantined_rows']):
                raise ContractError('daily batch row identity/conservation mismatch')
            con.execute('''CREATE OR REPLACE TEMP TABLE accepted AS SELECT *,
              row_number() OVER(PARTITION BY invoice_no,product_key,customer_key,country_key,invoice_at,
                quantity,unit_price,line_amount,cancellation ORDER BY source_row)>1 AS candidate_duplicate
              FROM staged WHERE len(reasons)=0''')
            invalid=con.execute('''SELECT count(*) FROM accepted WHERE invoice_no IS NULL OR stock_code IS NULL
              OR country IS NULL OR product_key IS NULL OR country_key IS NULL OR customer_key IS NULL
              OR quantity IS NULL OR unit_price IS NULL OR line_amount IS NULL OR invoice_at IS NULL
              OR CAST(invoice_at AS DATE)<>business_date
              OR TRY_CAST(ROUND(quantity::DECIMAL(19,0)*unit_price,2) AS DECIMAL(18,2)) IS DISTINCT FROM line_amount''').fetchone()[0]
            if invalid:raise ContractError('accepted batch contract/decimal reconciliation mismatch')
            _hook(failure_hook,'after_stage')
            con.execute('BEGIN TRANSACTION');in_tx=True
            con.execute('DELETE FROM fact_sales WHERE business_date=?',[day]);con.execute('DELETE FROM quarantine WHERE business_date=?',[day])
            _hook(failure_hook,'after_delete')
            con.execute('''INSERT INTO dim_product SELECT DISTINCT product_key,stock_code,description FROM accepted
              WHERE product_key NOT IN(SELECT product_key FROM dim_product)''')
            con.execute('''INSERT INTO dim_customer SELECT DISTINCT customer_key,customer_id FROM accepted
              WHERE customer_key NOT IN(SELECT customer_key FROM dim_customer)''')
            con.execute('''INSERT INTO dim_country SELECT DISTINCT country_key,country FROM accepted
              WHERE country_key NOT IN(SELECT country_key FROM dim_country)''')
            con.execute('INSERT INTO dim_date SELECT ?,?,?,? WHERE NOT EXISTS(SELECT 1 FROM dim_date WHERE business_date=?)',[day,day.year,day.month,day.day,day])
            con.execute('''INSERT INTO fact_sales SELECT business_date,source_sha256,source_row,invoice_no,product_key,customer_key,country_key,
              invoice_at,quantity,unit_price,line_amount,line_class,cancellation,cancellation_sign_mismatch,negative_price,candidate_duplicate FROM accepted''')
            con.execute('INSERT INTO quarantine SELECT business_date,source_sha256,source_row,reasons,raw_payload FROM staged WHERE len(reasons)>0')
            con.execute('''INSERT INTO workbook_sources SELECT ?,?,?,?,?,?,?,? WHERE NOT EXISTS(SELECT 1 FROM workbook_sources WHERE source_sha256=?)''',
              [sha,manifest['source_url'],manifest['captured_at'],manifest['source_bytes'],manifest['worksheet'],manifest['raw_rows'],manifest['raw_relative_path'],f'batches/{sha}/manifest.json',sha])
            if previous is None:
                con.execute('INSERT INTO batch_versions VALUES(?,?,?,?,?,?,?)',[day,sha,entry['rows'],entry['accepted_rows'],entry['quarantined_rows'],entry['sha256'],_utc()])
            con.execute('DELETE FROM current_batches WHERE business_date=?',[day]);con.execute('INSERT INTO current_batches VALUES(?,?)',[day,sha])
            _hook(failure_hook,'before_commit')
            con.execute('COMMIT');in_tx=False
        con.execute("UPDATE run_audit SET status='committed',finished_at=?,replayed=? WHERE run_id=?",[_utc(),replayed,run_id])
        return {'business_date':day.isoformat(),'source_sha256':sha,'raw_rows':entry['rows'],'accepted_rows':entry['accepted_rows'],
                'quarantined_rows':entry['quarantined_rows'],'replayed':replayed}
    except Exception as exc:
        if in_tx:con.execute('ROLLBACK')
        con.execute("UPDATE run_audit SET status='failed',finished_at=?,error_type=? WHERE run_id=?",[_utc(),type(exc).__name__,run_id])
        LOG.error('batch_failed day=%s run_id=%s error_type=%s',day,run_id,type(exc).__name__)
        raise


def load_batches(data_dir,start=None,end=None,allow_revert=False,failure_hook=None):
    """Publish selected recorded business dates; each date is a separate transaction."""
    data_dir=Path(data_dir);pointer=json.loads((data_dir/'batches/latest.json').read_text());sha=pointer['source_sha256']
    if not re.fullmatch('[a-f0-9]{64}',sha) or pointer['manifest']!=f'batches/{sha}/manifest.json':
        raise ContractError('split pointer identity mismatch')
    manifest=json.loads((data_dir/pointer['manifest']).read_text());_verify_manifest(data_dir,manifest)
    if manifest['source_sha256']!=sha:raise ContractError('split pointer SHA mismatch')
    lower=_day(start) if start is not None else min(_day(e['business_date']) for e in manifest['dates'])
    upper=_day(end) if end is not None else max(_day(e['business_date']) for e in manifest['dates'])
    if lower>upper:raise ContractError('start date must not be after end date')
    entries=[e for e in manifest['dates'] if lower<=_day(e['business_date'])<=upper]
    if not entries:raise ContractError('selected date range has no delivery; no implicit deletion')
    result=[]
    with _connect(data_dir) as con:
        existing={r[0] for r in con.execute('SELECT business_date FROM current_batches WHERE business_date BETWEEN ? AND ?',[lower,upper]).fetchall()}
        missing=existing-{_day(e['business_date']) for e in entries}
        if missing:raise ContractError('source omits previously published dates; explicit deletion workflow required')
        for entry in sorted(entries,key=lambda e:e['business_date']):
            result.append(_load_one(con,data_dir,manifest,entry,allow_revert,failure_hook))
    # A report is a separate publication after day transactions. On failure run report().
    exported=report(data_dir)
    LOG.info('batches_complete days=%s replayed=%s',len(result),sum(r['replayed'] for r in result))
    return {'days':result,'loaded_days':sum(not r['replayed'] for r in result),'replayed_days':sum(r['replayed'] for r in result),
            'report_generation':exported['generation']}


def _rows(con,sql):
    cursor=con.execute(sql);names=[c[0] for c in cursor.description]
    return [dict(zip(names,row)) for row in cursor.fetchall()]


def report(data_dir):
    """Export aggregate CSV/JSON from a coherent read transaction; atomic latest pointer."""
    import csv
    data_dir=Path(data_dir);generation=uuid.uuid4().hex;directory=data_dir/'reports/generations'/generation;directory.mkdir(parents=True)
    with _connect(data_dir,True) as con:
        con.execute('BEGIN TRANSACTION')
        batches=_rows(con,'SELECT * FROM current_batch_versions ORDER BY business_date')
        metrics=_rows(con,'''SELECT SUM(line_count) AS accepted_rows,SUM(positive_sales) AS positive_sales,
          SUM(negative_adjustments) AS negative_adjustments,SUM(net_revenue) AS net_revenue,
          SUM(zero_value_lines) AS zero_value_lines,SUM(unknown_customer_lines) AS unknown_customer_lines,
          SUM(candidate_duplicate_lines) AS candidate_duplicate_lines,SUM(cancellation_lines) AS cancellation_lines,
          SUM(cancellation_sign_mismatch_lines) AS cancellation_sign_mismatch_lines,SUM(negative_price_lines) AS negative_price_lines FROM daily_revenue''')[0]
        for key,value in metrics.items():
            if value is None:
                metrics[key]=Decimal('0.00') if key in ('positive_sales','negative_adjustments','net_revenue') else 0
        result={'generated_at':_utc(),'generation':generation,'contract_version':CONTRACT_VERSION,
          'execution':'local DuckDB; Azure Synapse has not been deployed or tested',
          'totals':{'raw_rows':sum(b['raw_rows'] for b in batches),'quarantined_rows':sum(b['quarantined_rows'] for b in batches),**metrics},
          'current_days':len(batches),'sources':_rows(con,'SELECT source_sha256,source_url,captured_at,source_bytes,worksheet,raw_rows FROM workbook_sources ORDER BY source_sha256'),
          'monthly':_rows(con,"SELECT date_trunc('month',business_date)::DATE AS month,SUM(line_count) AS accepted_rows,SUM(positive_sales) AS positive_sales,SUM(negative_adjustments) AS negative_adjustments,SUM(net_revenue) AS net_revenue FROM daily_revenue GROUP BY month ORDER BY month"),
          'quality':_rows(con,'SELECT * FROM quality_summary ORDER BY business_date,reason')}
        for name,sql in [('daily_revenue', 'SELECT d.*,c.country FROM daily_revenue d JOIN dim_country c USING(country_key) ORDER BY business_date,country'),
                         ('quality','SELECT * FROM quality_summary ORDER BY business_date,reason'),('batches','SELECT * FROM current_batch_versions ORDER BY business_date')]:
            cursor=con.execute(sql)
            with (directory/f'{name}.csv').open('w',newline='') as stream:
                writer=csv.writer(stream);writer.writerow([c[0] for c in cursor.description])
                while rows:=cursor.fetchmany(10000):writer.writerows(rows)
        (directory/'report.json').write_text(_json(result));con.execute('COMMIT')
    pointer=data_dir/'reports/latest.json';temporary=pointer.with_name('.latest.tmp')
    temporary.write_text(_json({'generation':generation,'report':f'generations/{generation}/report.json'}));os.replace(temporary,pointer)
    return json.loads(_json(result))


def fetch(data_dir):
    """Fetch the bounded public ZIP, retain it, and split its sole approved workbook."""
    data_dir=Path(data_dir);data_dir.mkdir(parents=True,exist_ok=True);deadline=time.monotonic()+90;last_error=None
    for attempt in range(3):
        fd,name=tempfile.mkstemp(prefix='.download-',suffix='.zip',dir=data_dir);temporary=Path(name)
        try:
            request=Request(SOURCE_URL,headers={'User-Agent':'retail-revenue-warehouse/0.1 public research'})
            with os.fdopen(fd,'wb') as output,urlopen(request,timeout=min(45,max(1,deadline-time.monotonic()))) as response:
                expected=response.headers.get('Content-Length');expected=int(expected) if expected else None
                if expected is not None and expected>MAX_SOURCE_BYTES:raise ContractError('remote ZIP exceeds byte limit')
                size=0
                while block:=response.read(1024*1024):
                    size+=len(block)
                    if size>MAX_SOURCE_BYTES or time.monotonic()>deadline:raise ContractError('download byte/deadline limit exceeded')
                    output.write(block)
                if expected is not None and size!=expected:raise ContractError('download length mismatch')
            _check_zip(temporary);sha=_sha(temporary);raw=data_dir/'raw/downloads'/sha;raw.mkdir(parents=True,exist_ok=True)
            retained=raw/'online-retail.zip'
            if retained.exists():
                if _sha(retained)!=sha:raise ContractError('retained ZIP checksum mismatch')
            else:shutil.copyfile(temporary,retained)
            manifest=raw/'manifest.json'
            if not manifest.exists():manifest.write_text(_json({'source_url':SOURCE_URL,'sha256':sha,'bytes':size,'captured_at':_utc()}))
            with zipfile.ZipFile(temporary) as archive:
                if archive.namelist()!=['Online Retail.xlsx']:raise ContractError('ZIP must contain exactly Online Retail.xlsx')
                member=archive.getinfo('Online Retail.xlsx')
                if member.file_size>MAX_SOURCE_BYTES:raise ContractError('workbook exceeds compressed source limit')
                fd,xname=tempfile.mkstemp(prefix='.workbook-',suffix='.xlsx',dir=data_dir);os.close(fd);xlsx=Path(xname)
                try:
                    with archive.open(member) as source,xlsx.open('wb') as output:shutil.copyfileobj(source,output)
                    extraction={'archive_sha256':sha,'member':'Online Retail.xlsx','workbook_sha256':_sha(xlsx),'workbook_bytes':xlsx.stat().st_size}
                    link=raw/'workbook.json'
                    if link.exists():
                        if json.loads(link.read_text())!=extraction:raise ContractError('ZIP extraction provenance mismatch')
                    else:
                        link_temp=raw/'.workbook.tmp';link_temp.write_text(_json(extraction));os.replace(link_temp,link)
                    result=split_workbook(xlsx,data_dir,source_url=SOURCE_URL)
                    result={**result,'download_sha256':sha,'download_bytes':size}
                    return result
                finally:xlsx.unlink(missing_ok=True)
        except HTTPError as exc:
            last_error=exc;exc.close()
            if exc.code not in (408,429,500,502,503,504):raise
        except (URLError,TimeoutError,ConnectionError) as exc:last_error=exc
        finally:temporary.unlink(missing_ok=True)
        if attempt<2:
            remaining=deadline-time.monotonic()
            if remaining<=0:break
            time.sleep(min(2**attempt,remaining))
    raise RuntimeError('source download failed within three attempts and deadline budget') from last_error
