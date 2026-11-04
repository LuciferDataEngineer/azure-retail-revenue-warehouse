"""Independent full-source reconciliation with openpyxl and Python Decimal.

This does not import the warehouse or read its generated Parquet. It is an oracle
for the observed UCI workbook, not a second general-purpose ingestion adapter.
"""
import argparse
from collections import Counter
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path

from openpyxl import load_workbook


def inspect(path):
    expected = ('InvoiceNo','StockCode','Description','Quantity','InvoiceDate','UnitPrice','CustomerID','Country')
    counts = Counter()
    sums = {'positive_gbp':Decimal(0),'negative_gbp':Decimal(0),'net_gbp':Decimal(0)}
    days = {}
    workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        if workbook.sheetnames != ['Online Retail']:
            raise ValueError('Oracle expects the observed single-sheet UCI workbook')
        rows = workbook['Online Retail'].iter_rows(values_only=True)
        if next(rows) != expected:
            raise ValueError('Oracle header mismatch')
        for row in rows:
            invoice,stock,description,quantity,when,price,customer,country = row
            if not isinstance(when,datetime) or when.tzinfo is not None:
                raise ValueError('Oracle requires native naive Excel timestamps')
            q = Decimal(str(quantity))
            p = Decimal(str(price))
            if not q.is_finite() or q != q.to_integral_value() or not p.is_finite():
                raise ValueError('Oracle numeric contract mismatch')
            value = (q * p.quantize(Decimal('.0001'), rounding=ROUND_HALF_UP)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            counts['raw_rows'] += 1
            counts['missing_customer_rows'] += customer is None
            counts['missing_description_rows'] += description is None
            counts['cancellation_invoice_rows'] += str(invoice).lower().startswith('c')
            counts['negative_quantity_rows'] += q < 0
            counts['negative_price_rows'] += p < 0
            counts['zero_price_rows'] += p == 0
            counts['positive_amount_rows'] += value > 0
            counts['negative_amount_rows'] += value < 0
            counts['zero_amount_rows'] += value == 0
            sums['net_gbp'] += value
            if value > 0:
                sums['positive_gbp'] += value
            elif value < 0:
                sums['negative_gbp'] += value
            day = when.date().isoformat()
            state = days.setdefault(day, {'rows':0,'positive_gbp':Decimal(0),
                                         'negative_gbp':Decimal(0),'net_gbp':Decimal(0)})
            state['rows'] += 1
            state['net_gbp'] += value
            state['positive_gbp'] += max(value,Decimal(0))
            state['negative_gbp'] += min(value,Decimal(0))
    finally:
        workbook.close()
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    result = {'method':'Independent source workbook scan; openpyxl + Python Decimal',
              'workbook_sha256':digest.hexdigest(),'counts':dict(counts),
              'amounts':sums,'observed_business_dates':len(days),
              'first_date':min(days),'last_date':max(days),
              'daily':{d:days[d] for d in sorted(days)}}
    return json.loads(json.dumps(result,default=str,allow_nan=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(inspect(args.workbook),indent=2,allow_nan=False))
