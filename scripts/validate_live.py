"""Reconcile full UCI source oracle, current star, replays and aggregate exports.

Run after source_oracle.py and the full live load. No downloads or cloud calls.
"""
import argparse
import csv
from decimal import Decimal
import json
from pathlib import Path
import platform

import duckdb
import openpyxl
import pyarrow
from retail_warehouse.pipeline import load_batches,report

TABLES=('workbook_sources','batch_versions','current_batches','fact_sales','quarantine',
        'dim_customer','dim_product','dim_country','dim_date')


def fingerprints(data_dir):
    with duckdb.connect(str(data_dir/'warehouse.duckdb'),read_only=True) as conn:
        return {name:list(conn.execute(f'''SELECT count(*),bit_xor(hash(t)),
                    sum(hash(t)::DECIMAL(38,0))::VARCHAR FROM {name} t''').fetchone())
                for name in TABLES}


def validate(data_dir,oracle_path):
    oracle=json.loads(oracle_path.read_text())
    with duckdb.connect(str(data_dir/'warehouse.duckdb'),read_only=True) as conn:
        sources=conn.execute('SELECT DISTINCT source_sha256 FROM current_batches').fetchall()
        assert sources==[(oracle['workbook_sha256'],)],'Expected one observed UCI source version'
        count=oracle['counts']['raw_rows']
        physical=conn.execute('''SELECT count(*),count(DISTINCT source_row),min(source_row),max(source_row)
                                FROM fact_sales''').fetchone()
        assert physical==(count,count,2,count+1)
        assert conn.execute('SELECT count(*) FROM quarantine').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM current_batches').fetchone()[0]==oracle['observed_business_dates']
        daily=conn.execute('''SELECT business_date,count(*),
            sum(CASE WHEN line_amount>0 THEN line_amount ELSE 0 END),
            sum(CASE WHEN line_amount<0 THEN line_amount ELSE 0 END),sum(line_amount)
            FROM fact_sales GROUP BY business_date ORDER BY business_date''').fetchall()
        for day,rows,positive,negative,net in daily:
            expected=oracle['daily'][str(day)]
            assert (rows,positive,negative,net)==(expected['rows'],Decimal(expected['positive_gbp']),
                                                Decimal(expected['negative_gbp']),Decimal(expected['net_gbp']))
        for dimension,key in [('dim_customer','customer_key'),('dim_product','product_key'),
                              ('dim_country','country_key'),('dim_date','business_date')]:
            assert conn.execute(f'''SELECT count(*) FROM fact_sales f
                LEFT JOIN {dimension} d ON f.{key}=d.{key} WHERE d.{key} IS NULL''').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM fact_sales WHERE customer_key=0').fetchone()[0]==oracle['counts']['missing_customer_rows']
        assert conn.execute('''SELECT count(*) FROM fact_sales f JOIN dim_product p USING(product_key)
            WHERE p.description IS NULL''').fetchone()[0]==oracle['counts']['missing_description_rows']
        dimension_counts={name:conn.execute(f'SELECT count(*) FROM {name}').fetchone()[0]
                          for name in TABLES if name.startswith('dim_')}
    before=fingerprints(data_dir)
    replay=load_batches(data_dir)
    assert replay['loaded_days']==0 and replay['replayed_days']==oracle['observed_business_dates']
    after=fingerprints(data_dir)
    assert before==after
    backfill=load_batches(data_dir,start='2010-12-01',end='2010-12-07')
    assert backfill['loaded_days']==0
    expected_backfill=sum('2010-12-01'<=day<='2010-12-07' for day in oracle['daily'])
    assert backfill['replayed_days']==expected_backfill
    assert fingerprints(data_dir)==after
    output=report(data_dir)
    generated=data_dir/'reports/generations'/output['generation']
    comparisons={}
    with duckdb.connect(str(data_dir/'warehouse.duckdb'),read_only=True) as conn:
        queries={
            'daily_revenue':'SELECT d.*,c.country FROM daily_revenue d JOIN dim_country c USING(country_key) ORDER BY business_date,country',
            'quality':'SELECT * FROM quality_summary ORDER BY business_date,reason',
            'batches':'SELECT * FROM current_batch_versions ORDER BY business_date'}
        for name,sql in queries.items():
            cursor=conn.execute(sql);number=0
            with (generated/f'{name}.csv').open(newline='') as stream:
                reader=csv.reader(stream)
                assert next(reader)==[c[0] for c in cursor.description]
                for rows in iter(lambda:cursor.fetchmany(10000),[]):
                    for row in rows:
                        assert next(reader)==['' if value is None else str(value) for value in row]
                        number+=1
                assert next(reader,None) is None
            comparisons[name]=number
    return {'execution':'local only; no Azure SQL or infrastructure runtime validation',
            'python':platform.python_version(),'duckdb':duckdb.__version__,'pyarrow':pyarrow.__version__,
            'openpyxl':openpyxl.__version__,'source_sha256':oracle['workbook_sha256'],
            'independent_daily_decimal_reconciliations':len(daily),
            'physical_source_rows_exactly_accounted':count,'dimension_orphans':0,
            'dimension_counts':dimension_counts,'same_source_replayed_days':replay['replayed_days'],
            'seven_calendar_date_backfill_observed_days':expected_backfill,
            'business_fingerprints_unchanged':True,'fingerprints':after,
            'csv_rows_exactly_compared':comparisons,'totals':output['totals']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=Path('data/live'))
    parser.add_argument('--oracle',type=Path,default=Path('examples/source-oracle-2026-11-04.json'))
    args=parser.parse_args()
    print(json.dumps(validate(args.data_dir,args.oracle),indent=2,allow_nan=False))
