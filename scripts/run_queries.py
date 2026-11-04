"""Execute the committed read-only analytical SQL against a local warehouse."""
import argparse
from datetime import date,datetime
from decimal import Decimal
import json
from pathlib import Path

import duckdb


def serialize(value):
    if isinstance(value,Decimal):return str(value)
    if isinstance(value,(date,datetime)):return value.isoformat()
    raise TypeError(type(value).__name__)


def run(data_dir):
    sql=Path(__file__).resolve().parents[1]/'sql/analysis.sql'
    with duckdb.connect(str(Path(data_dir)/'warehouse.duckdb'),read_only=True) as conn:
        conn.execute('BEGIN TRANSACTION')
        statements=conn.extract_statements(sql.read_text())
        if any(statement.type!=duckdb.StatementType.SELECT for statement in statements):
            raise ValueError('Analytical file must contain SELECT statements only')
        result={}
        for index,statement in enumerate(statements,1):
            cursor=conn.execute(statement.query)
            names=[x[0] for x in cursor.description]
            result[f'query_{index}']=[dict(zip(names,row)) for row in cursor.fetchall()]
        conn.execute('COMMIT')
    return json.loads(json.dumps(result,default=serialize,allow_nan=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=Path('data/live'))
    args=parser.parse_args()
    print(json.dumps(run(args.data_dir),indent=2,allow_nan=False))
