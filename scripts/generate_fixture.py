"""Generate a deterministic, wholly synthetic UCI-shaped retail workbook.

All invoices, people, products and amounts in this fixture are invented. The
fixture is not a sampled subset of the UCI workbook.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from openpyxl import Workbook

HEADERS = ('InvoiceNo', 'StockCode', 'Description', 'Quantity', 'InvoiceDate',
           'UnitPrice', 'CustomerID', 'Country')
FIXED_TIME = datetime(2024, 1, 1)


def line(**changes):
    row = {'InvoiceNo': '100', 'StockCode': 'A', 'Description': 'Invented blue mug',
           'Quantity': 2, 'InvoiceDate': datetime(2010, 12, 1, 10, 0),
           'UnitPrice': 3.125, 'CustomerID': 12345, 'Country': 'United Kingdom'}
    row.update(changes)
    return row


def sample_rows():
    """Ten rows: eight accepted and two quarantined, over two business dates."""
    return [
        line(),
        line(),  # Deliberately identical modeled values; keep both physical rows.
        line(InvoiceNo='C100', Quantity=-1),
        line(InvoiceNo='101', StockCode='B', Description=None, Quantity=1,
             UnitPrice=0, CustomerID=None, Country='Germany'),
        line(InvoiceNo='102', StockCode='C', Quantity=3, UnitPrice=0.3333),
        line(InvoiceNo='103', StockCode='D', Quantity=1, UnitPrice=-2),
        line(InvoiceNo='104', Quantity=1.5),
        line(InvoiceNo='105', StockCode=None),
        line(InvoiceNo='200', Description='Invented blue mug revised', Quantity=1,
             InvoiceDate=datetime(2010, 12, 2, 9), UnitPrice=7.5, CustomerID=54321),
        line(InvoiceNo='C201', StockCode='E', Quantity=1,
             InvoiceDate=datetime(2010, 12, 2, 10), UnitPrice=4),
    ]


def write_fixture(path, rows=None, *, headers=HEADERS, sheet_name='Online Retail'):
    """Normalize ZIP metadata so repeated fixture generation has identical bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    workbook.properties.creator = 'Synthetic portfolio fixture'
    workbook.properties.lastModifiedBy = 'Synthetic portfolio fixture'
    workbook.properties.title = 'Wholly synthetic retail fixture; no observed sales'
    workbook.properties.description = 'Invented deterministic data for tests only'
    workbook.properties.created = FIXED_TIME
    workbook.properties.modified = FIXED_TIME
    worksheet = workbook.active
    worksheet.title = sheet_name
    worksheet.append(list(headers))
    for row in sample_rows() if rows is None else rows:
        worksheet.append([row.get(name) for name in headers])
    original = BytesIO()
    workbook.save(original)
    workbook.close()
    # openpyxl overwrites modified time on save; replace just that XML value.
    from xml.etree import ElementTree as ET
    namespace = '{http://purl.org/dc/terms/}'
    with ZipFile(original) as source, ZipFile(path, 'w', compression=ZIP_DEFLATED) as target:
        for name in sorted(source.namelist()):
            content = source.read(name)
            if name == 'docProps/core.xml':
                tree = ET.fromstring(content)
                for key in ('created', 'modified'):
                    node = tree.find(namespace + key)
                    if node is not None:
                        node.text = '2024-01-01T00:00:00Z'
                content = ET.tostring(tree, encoding='utf-8')
            info = ZipInfo(name, (2024, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            target.writestr(info, content)
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('data/fixtures/synthetic-retail.xlsx'))
    args = parser.parse_args()
    print(write_fixture(args.output))
