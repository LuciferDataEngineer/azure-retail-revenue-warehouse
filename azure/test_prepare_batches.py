"""Offline shape-adapter checks. No Azure credentials, SDK calls or SQL runtime."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import pyarrow.parquet as pq
from retail_warehouse.pipeline import split_workbook
from scripts.generate_fixture import line, write_fixture
from prepare_batches import prepare


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.data=self.root/'data'
        self.source=write_fixture(self.root/'source.xlsx')
        self.manifest=split_workbook(self.source,self.data)

    def test_all_rows_and_signed_totals_survive_flattening(self):
        result=prepare(self.data,self.manifest,self.root/'out')
        self.assertEqual(sum(x['rows'] for x in result),10)
        self.assertEqual(sum(x['accepted_rows'] for x in result),8)
        self.assertEqual(sum(x['quarantined_rows'] for x in result),2)
        self.assertEqual(result[0]['net_sales'],'8.37')
        first=pq.read_table(self.root/'out'/result[0]['batch_path']).to_pylist()
        self.assertEqual([x['source_row'] for x in first],list(range(2,10)))
        self.assertEqual(sum(x['is_valid'] for x in first),6)
        self.assertTrue(all(isinstance(json.loads(x['reasons_json']),list) for x in first))
        second=prepare(self.data,self.manifest,self.root/'out2')
        self.assertEqual(result,second)

    def test_changed_parquet_fails_before_ready_marker(self):
        path=self.data/self.manifest['dates'][0]['path']
        path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'SHA mismatch'):
            prepare(self.data,self.manifest,self.root/'out')

    def test_manifest_count_mismatch_does_not_publish_ready(self):
        changed=copy.deepcopy(self.manifest);changed['dates'][0]['accepted_rows']+=1
        with self.assertRaisesRegex(ValueError,'conservation'):
            prepare(self.data,changed,self.root/'out')

    def test_sql_width_limit_fails_instead_of_truncating_source(self):
        source=write_fixture(self.root/'wide.xlsx',[line(Description='x'*1025)])
        manifest=split_workbook(source,self.data)
        with self.assertRaisesRegex(ValueError,'description exceeds'):
            prepare(self.data,manifest,self.root/'out')

    def test_contract_mismatch_is_explicit(self):
        changed=copy.deepcopy(self.manifest);changed['contract_version']='unreviewed'
        with self.assertRaisesRegex(ValueError,'Unreviewed'):
            prepare(self.data,changed,self.root/'out')


if __name__=='__main__':unittest.main()
