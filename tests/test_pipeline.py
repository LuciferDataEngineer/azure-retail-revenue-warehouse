from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from zipfile import ZipFile, ZIP_DEFLATED

import duckdb

from retail_warehouse import pipeline
from scripts.generate_fixture import HEADERS, line, sample_rows, write_fixture


class RetailWarehouseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / 'data'
        self.sequence = 0

    def source(self, rows=None, **kwargs):
        self.sequence += 1
        return write_fixture(self.root / f'source-{self.sequence}.xlsx', rows, **kwargs)

    def split(self, source=None):
        return pipeline.split_workbook(source or self.source(), self.data,
            source_url='https://example.org/wholly-synthetic-retail.xlsx')

    def load(self, **kwargs):
        return pipeline.load_batches(self.data, **kwargs)

    def query(self, sql, params=None):
        with duckdb.connect(str(self.data / 'warehouse.duckdb'), read_only=True) as con:
            return con.execute(sql, params or []).fetchall()

    def state(self):
        names = ('fact_sales', 'quarantine', 'batch_versions', 'current_batches',
                 'dim_customer', 'dim_product', 'dim_country', 'dim_date')
        return {name: sorted(map(repr, self.query(f'SELECT * FROM {name}')))
                for name in names}

    def test_fixture_bytes_reproduce(self):
        self.assertEqual(self.source().read_bytes(), self.source().read_bytes())

    def test_global_buffer_chunks_preserve_unsorted_date_rows_and_reproduce_batches(self):
        rows=[line(InvoiceNo=str(100+i),Quantity=i+1,UnitPrice=0.12,
                   InvoiceDate=datetime(2010,12,1+(i%3),10)) for i in range(9)]
        source=self.source(rows)
        write_table=pipeline.pq.write_table
        with patch.object(pipeline,'BUFFER_ROWS',2),patch.object(pipeline.pq,'write_table',wraps=write_table) as writes:
            first=self.split(source)
            second_dir=self.root/'second-delivery'
            second=pipeline.split_workbook(source,second_dir)
        self.assertTrue(writes.call_args_list)
        self.assertTrue(all(call.args[0].num_rows<=2 for call in writes.call_args_list))
        self.assertEqual([d['rows'] for d in first['dates']],[3,3,3])
        self.assertEqual([d['sha256'] for d in first['dates']],
                         [d['sha256'] for d in second['dates']])
        self.assertEqual(list((self.data/'batches').rglob('.parts')),[])
        self.load()
        self.assertEqual(self.query('SELECT source_row,quantity FROM fact_sales ORDER BY source_row'),
                         [(i+2,i+1) for i in range(9)])
        self.assertEqual(self.query('SELECT SUM(line_amount) FROM fact_sales'),[(Decimal('5.40'),)])

    def test_distinct_date_limit_failure_keeps_complete_previous_delivery(self):
        self.split()
        pointer=self.data/'batches/latest.json'
        prior=pointer.read_bytes()
        source=self.source([line(InvoiceNo='limit-one'),
            line(InvoiceNo='limit-two',InvoiceDate=datetime(2010,12,3))])
        with patch.object(pipeline,'MAX_BATCH_DAYS',1):
            with self.assertRaises(pipeline.ContractError):
                self.split(source)
        self.assertEqual(pointer.read_bytes(),prior)
        self.assertEqual(list((self.data/'batches').glob('.build-*')),[])

    def test_signed_amounts_conserve_rows_and_keep_adjustments(self):
        self.split()
        result = self.load()
        self.assertEqual(len(result['days']), 2)
        self.assertEqual(sum(day['raw_rows'] for day in result['days']), 10)
        self.assertEqual(sum(day['accepted_rows'] for day in result['days']), 8)
        self.assertEqual(sum(day['quarantined_rows'] for day in result['days']), 2)
        self.assertEqual(self.query('SELECT COUNT(*),SUM(line_amount) FROM fact_sales'),
                         [(8, Decimal('19.87'))])
        self.assertEqual(self.query('''SELECT line_class,SUM(line_amount) FROM fact_sales
            GROUP BY line_class ORDER BY line_class'''),
            [('negative_adjustment', Decimal('-5.13')), ('positive_sales', Decimal('25.00')),
             ('zero_value', Decimal('0.00'))])
        self.assertEqual(self.query('SELECT COUNT(*) FROM fact_sales WHERE negative_price'), [(1,)])
        self.assertEqual(self.query('SELECT COUNT(*) FROM fact_sales WHERE cancellation'), [(2,)])
        self.assertEqual(self.query('SELECT COUNT(*) FROM fact_sales WHERE cancellation_sign_mismatch'), [(1,)])

    def test_identity_is_workbook_sha_plus_physical_excel_row(self):
        source = self.source([line(), line()])
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        self.split(source)
        self.load()
        self.assertEqual(self.query('SELECT source_sha256,source_row FROM fact_sales ORDER BY source_row'),
                         [(digest, 2), (digest, 3)])
        self.assertEqual(self.query('SELECT COUNT(*) FROM fact_sales WHERE candidate_duplicate'), [(1,)])

    def test_missing_customer_uses_unknown_member_and_missing_description_is_retained(self):
        self.split(self.source([line(CustomerID=None, Description=None)]))
        self.load()
        self.assertEqual(self.query('SELECT customer_key,line_amount FROM fact_sales'), [(0, Decimal('6.25'))])
        self.assertEqual(self.query('SELECT customer_id FROM dim_customer WHERE customer_key=0'), [(None,)])
        self.assertEqual(self.query('''SELECT COUNT(*) FROM fact_sales f
            JOIN dim_product p USING(product_key) JOIN dim_customer c USING(customer_key)
            JOIN dim_country n USING(country_key) JOIN dim_date d USING(business_date)'''), [(1,)])

    def test_same_invoice_product_lines_are_not_collapsed(self):
        self.split(self.source([line(Quantity=1), line(Quantity=3)]))
        self.load()
        self.assertEqual(self.query('SELECT COUNT(*),SUM(quantity),SUM(line_amount) FROM fact_sales'),
                         [(2, 4, Decimal('12.51'))])

    def test_money_rounds_after_quantity_multiplication(self):
        self.split(self.source([line(Quantity=3, UnitPrice=0.335), line(Quantity=-3, UnitPrice=0.335)]))
        self.load()
        self.assertEqual(self.query('SELECT unit_price,line_amount FROM fact_sales ORDER BY source_row'),
                         [(Decimal('0.3350'), Decimal('1.01')), (Decimal('0.3350'), Decimal('-1.01'))])

    def test_fractional_unit_price_normalizes_to_four_places(self):
        self.split(self.source([line(Quantity=10, UnitPrice=0.12345)]))
        self.load()
        self.assertEqual(self.query('SELECT unit_price,line_amount FROM fact_sales'),
                         [(Decimal('0.1235'), Decimal('1.24'))])

    def test_replay_keeps_every_business_table_unchanged(self):
        self.split()
        self.load()
        before = self.state()
        replay = self.load()
        self.assertTrue(all(day['replayed'] for day in replay['days']))
        self.assertEqual(before, self.state())

    def test_corrected_date_replaces_only_selected_date(self):
        self.split()
        self.load()
        original_other_day = self.query("SELECT * FROM fact_sales WHERE business_date=DATE '2010-12-02' ORDER BY source_row")
        corrected = sample_rows()
        corrected[0] = line(Quantity=1, UnitPrice=100)
        self.split(self.source(corrected))
        self.load(start='2010-12-01', end='2010-12-01')
        self.assertEqual(self.query("SELECT SUM(line_amount) FROM fact_sales WHERE business_date=DATE '2010-12-01'"),
                         [(Decimal('102.12'),)])
        self.assertEqual(self.query("SELECT * FROM fact_sales WHERE business_date=DATE '2010-12-02' ORDER BY source_row"),
                         original_other_day)
        self.assertEqual(self.query('SELECT COUNT(*) FROM batch_versions'), [(3,)])

    def test_historical_source_cannot_silently_replace_a_newer_published_version(self):
        first = self.source([line(UnitPrice=10)])
        second = self.source([line(UnitPrice=20)])
        self.split(first)
        self.load()
        self.split(second)
        self.load()
        before = self.state()
        self.split(first)
        with self.assertRaises(pipeline.ContractError):
            self.load()
        self.assertEqual(before, self.state())
        self.load(allow_revert=True)
        self.assertEqual(self.query('SELECT SUM(line_amount) FROM fact_sales'), [(Decimal('20.00'),)])

    def test_seven_day_backfill_uses_inclusive_parameters(self):
        rows = [line(InvoiceNo=str(100+i), Quantity=1, UnitPrice=i+1,
                     InvoiceDate=datetime(2010, 12, 1) + timedelta(days=i)) for i in range(10)]
        self.split(self.source(rows))
        result = self.load(start='2010-12-02', end='2010-12-08')
        self.assertEqual(len(result['days']), 7)
        self.assertEqual(self.query('SELECT COUNT(*),SUM(line_amount) FROM fact_sales'), [(7, Decimal('35.00'))])
        self.assertEqual(self.query('SELECT COUNT(*) FROM current_batches'), [(7,)])

    def test_product_description_versions_preserve_historical_attributes(self):
        self.split(self.source([line(Description='Invented old description'),
            line(Description='Invented later description', InvoiceDate=datetime(2010,12,2,10))]))
        self.load()
        self.assertEqual(self.query('SELECT COUNT(DISTINCT product_key) FROM fact_sales'), [(2,)])
        self.assertEqual(self.query('''SELECT p.description FROM fact_sales f
            JOIN dim_product p USING(product_key) ORDER BY business_date'''),
            [('Invented old description',), ('Invented later description',)])

    def test_bad_header_rejects_workbook_without_replacing_split_pointer(self):
        self.split()
        pointer = self.data / 'batches/latest.json'
        before = pointer.read_bytes()
        headers = tuple('WrongInvoice' if name == 'InvoiceNo' else name for name in HEADERS)
        with self.assertRaises(pipeline.ContractError):
            self.split(self.source(headers=headers))
        self.assertEqual(pointer.read_bytes(), before)

    def test_invalid_date_rejects_whole_workbook_to_avoid_unassigned_row_loss(self):
        self.split()
        pointer = self.data / 'batches/latest.json'
        before = pointer.read_bytes()
        for value in (None, 'not-a-date'):
            with self.subTest(value=value):
                with self.assertRaises(pipeline.ContractError):
                    self.split(self.source([line(), line(InvoiceDate=value)]))
                self.assertEqual(pointer.read_bytes(), before)

    def test_empty_source_cannot_silently_delete_existing_sales(self):
        self.split()
        self.load()
        before = self.state()
        with self.assertRaises(pipeline.ContractError):
            self.split(self.source([]))
        self.assertEqual(before, self.state())

    def test_invalid_row_values_quarantine_with_nonempty_reasons(self):
        rows = [line(), line(InvoiceNo=None), line(StockCode=None), line(Country=None),
                line(Quantity=1.5), line(Quantity=None), line(UnitPrice=None),
                line(CustomerID=1.5), line(UnitPrice=1e30)]
        self.split(self.source(rows))
        result = self.load()
        day = result['days'][0]
        self.assertEqual((day['raw_rows'], day['accepted_rows'], day['quarantined_rows']), (9,1,8))
        rejected = self.query('SELECT source_row,reasons FROM quarantine ORDER BY source_row')
        self.assertEqual([r[0] for r in rejected], list(range(3,11)))
        self.assertTrue(all(r[1] for r in rejected))

    def test_zero_and_negative_quantity_price_are_not_silently_removed(self):
        self.split(self.source([line(Quantity=0), line(Quantity=-2), line(Quantity=-2, UnitPrice=-1)]))
        self.load()
        self.assertEqual(self.query('SELECT quantity,line_amount FROM fact_sales ORDER BY source_row'),
                         [(0,Decimal('0.00')),(-2,Decimal('-6.25')),(-2,Decimal('2.00'))])

    def test_all_quarantined_day_reports_zero_accepted_and_zero_revenue(self):
        self.split(self.source([line(Quantity=1.5),line(StockCode=None)]))
        self.load()
        totals = pipeline.report(self.data)['totals']
        self.assertEqual(totals['raw_rows'],2)
        self.assertEqual(totals['quarantined_rows'],2)
        self.assertEqual(totals['accepted_rows'],0)
        self.assertEqual(Decimal(totals['net_revenue']),Decimal('0.00'))

    def test_formula_identifier_is_quarantined_without_evaluation(self):
        self.split(self.source([line(InvoiceNo='=1+1'),line(StockCode='=2+2'),line(Country='=3+3')]))
        result=self.load()
        self.assertEqual(result['days'][0]['accepted_rows'],0)
        self.assertEqual(result['days'][0]['quarantined_rows'],3)

    def test_secret_bearing_source_url_is_rejected_before_recording_provenance(self):
        source = self.source()
        for url in ['https://user:password@example.org/input.xlsx',
                    'https://example.org/input.xlsx?sig=synthetic-secret']:
            with self.subTest(url=url):
                with self.assertRaises(pipeline.ContractError):
                    pipeline.split_workbook(source,self.data,source_url=url)

    def test_failure_after_delete_rolls_back_prior_date_and_dimensions(self):
        self.split(self.source([line()]))
        self.load()
        before = self.state()
        self.split(self.source([line(StockCode='NEW', Description='New synthetic product', UnitPrice=99)]))
        seen = []
        def fail(phase):
            seen.append(phase)
            if phase == 'after_delete':
                raise RuntimeError('injected after DELETE')
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            self.load(failure_hook=fail)
        self.assertIn('after_delete', seen)
        self.assertEqual(before, self.state())
        self.load()
        self.assertEqual(self.query('SELECT SUM(line_amount) FROM fact_sales'), [(Decimal('198.00'),)])

    def test_failure_before_commit_rolls_back_insertions_and_current_pointer(self):
        self.split(self.source([line()]))
        self.load()
        before = self.state()
        self.split(self.source([line(CustomerID=99999, Country='Invented country', UnitPrice=99)]))
        def fail(phase):
            if phase == 'before_commit':
                raise RuntimeError('injected before COMMIT')
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            self.load(failure_hook=fail)
        self.assertEqual(before, self.state())

    def test_multi_day_failure_preserves_prior_committed_day_and_rolls_back_failed_day(self):
        self.split(self.source([line(Quantity=1, UnitPrice=1),
            line(Quantity=1, UnitPrice=2, InvoiceDate=datetime(2010,12,2,10))]))
        self.load()
        self.split(self.source([line(Quantity=1, UnitPrice=10),
            line(Quantity=1, UnitPrice=20, InvoiceDate=datetime(2010,12,2,10))]))
        commits_seen = 0
        def fail_second_day(phase):
            nonlocal commits_seen
            if phase == 'before_commit':
                commits_seen += 1
                if commits_seen == 2:
                    raise RuntimeError('injected second-day failure')
        with self.assertRaisesRegex(RuntimeError,'second-day'):
            self.load(failure_hook=fail_second_day)
        self.assertEqual(self.query('SELECT line_amount FROM fact_sales ORDER BY business_date'),
                         [(Decimal('10.00'),),(Decimal('2.00'),)])
        recovery = self.load()
        self.assertTrue(recovery['days'][0]['replayed'])
        self.assertFalse(recovery['days'][1]['replayed'])
        self.assertEqual(self.query('SELECT line_amount FROM fact_sales ORDER BY business_date'),
                         [(Decimal('10.00'),),(Decimal('20.00'),)])

    def test_invalid_requested_range_cannot_mutate_existing_data(self):
        self.split()
        self.load()
        before = self.state()
        with self.assertRaises(pipeline.ContractError):
            self.load(start='2010-12-02',end='2010-12-01')
        self.assertEqual(before,self.state())

    def test_raw_archive_digest_matches_original_bytes(self):
        source = self.source()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        self.split(source)
        retained = [p for p in (self.data/'raw').rglob('*.xlsx')
                    if hashlib.sha256(p.read_bytes()).hexdigest() == digest]
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0].read_bytes(), source.read_bytes())

    def test_tampered_parquet_cannot_replace_committed_state(self):
        self.split()
        self.load()
        before = self.state()
        self.split(self.source([line(UnitPrice=99)]))
        pointer = json.loads((self.data/'batches/latest.json').read_text())
        manifest_path = self.data / pointer['manifest']
        parquet = next(manifest_path.parent.rglob('*.parquet'))
        parquet.write_bytes(parquet.read_bytes()+b'corruption')
        with self.assertRaises(pipeline.ContractError):
            self.load()
        self.assertEqual(before, self.state())

    def test_raw_corruption_is_detected_before_same_source_reuse(self):
        source = self.source()
        self.split(source)
        raw = next((self.data/'raw').rglob('*.xlsx'))
        raw.write_bytes(b'not-a-workbook')
        with self.assertRaises(pipeline.ContractError):
            self.split(source)

    def test_report_failure_keeps_previous_export_then_replay_recovers(self):
        self.split(self.source([line()]))
        self.load()
        pointer = self.data/'reports/latest.json'
        prior = pointer.read_bytes()
        self.split(self.source([line(UnitPrice=99)]))
        real_replace = pipeline.os.replace
        def fail_report_pointer(src, dst):
            if Path(dst) == pointer:
                raise OSError('injected report publication failure')
            return real_replace(src,dst)
        with patch.object(pipeline.os,'replace',side_effect=fail_report_pointer):
            with self.assertRaisesRegex(OSError,'injected'):
                self.load()
        self.assertEqual(pointer.read_bytes(),prior)
        self.assertEqual(self.query('SELECT SUM(line_amount) FROM fact_sales'),[(Decimal('198.00'),)])
        result = self.load()
        self.assertTrue(result['days'][0]['replayed'])
        self.assertNotEqual(pointer.read_bytes(),prior)

    def download_response(self, content=None, declared_length=None):
        if content is None:
            archive=io.BytesIO()
            with ZipFile(archive,'w',compression=ZIP_DEFLATED) as zipped:
                zipped.writestr('Online Retail.xlsx',self.source().read_bytes())
            content=archive.getvalue()
        response=io.BytesIO(content)
        response.headers={} if declared_length is None else {'Content-Length':str(declared_length)}
        return response

    def test_fetch_retains_zip_workbook_and_public_provenance(self):
        response=self.download_response()
        with patch.object(pipeline,'urlopen',return_value=response) as opened:
            result=pipeline.fetch(self.data)
        self.assertEqual(result['raw_rows'],10)
        self.assertEqual(result['source_url'],pipeline.SOURCE_URL)
        self.assertEqual(opened.call_count,1)
        self.assertGreater(opened.call_args.kwargs['timeout'],0)
        self.assertLessEqual(opened.call_args.kwargs['timeout'],45)
        self.assertEqual(len(list((self.data/'raw/downloads').rglob('*.zip'))),1)
        self.assertEqual(len(list((self.data/'raw').rglob('*.xlsx'))),1)

    def test_fetch_declared_byte_limit_rejects_without_splitting(self):
        response=self.download_response(b'',pipeline.MAX_SOURCE_BYTES+1)
        with patch.object(pipeline,'urlopen',return_value=response),patch.object(pipeline,'split_workbook') as split:
            with self.assertRaises(pipeline.ContractError):
                pipeline.fetch(self.data)
        split.assert_not_called()
        self.assertEqual(list(self.data.glob('.download-*')),[])

    def test_fetch_stream_byte_limit_without_length_rejects(self):
        response=self.download_response(b'123456789')
        with patch.object(pipeline,'urlopen',return_value=response),patch.object(pipeline,'MAX_SOURCE_BYTES',8):
            with self.assertRaises(pipeline.ContractError):
                pipeline.fetch(self.data)

    def test_fetch_incomplete_content_length_rejects(self):
        response=self.download_response(b'12345',6)
        with patch.object(pipeline,'urlopen',return_value=response):
            with self.assertRaises(pipeline.ContractError):
                pipeline.fetch(self.data)

    def test_fetch_transient_error_retries_and_closes_error_stream(self):
        body=io.BytesIO(b'synthetic unavailable')
        transient=HTTPError(pipeline.SOURCE_URL,503,'synthetic',{},body)
        with (patch.object(pipeline,'urlopen',side_effect=[transient,self.download_response()]) as opened,
                patch.object(pipeline.time,'sleep')):
            result=pipeline.fetch(self.data)
        self.assertEqual(opened.call_count,2)
        self.assertEqual(result['raw_rows'],10)
        self.assertTrue(body.closed)

    def test_fetch_permanent_error_does_not_retry_and_closes_stream(self):
        body=io.BytesIO(b'synthetic missing')
        missing=HTTPError(pipeline.SOURCE_URL,404,'synthetic',{},body)
        with patch.object(pipeline,'urlopen',side_effect=missing) as opened:
            with self.assertRaises(HTTPError):
                pipeline.fetch(self.data)
        self.assertEqual(opened.call_count,1)
        self.assertTrue(body.closed)

    def test_fetch_stops_after_three_transport_errors(self):
        with (patch.object(pipeline,'urlopen',side_effect=URLError('synthetic offline')) as opened,
                patch.object(pipeline.time,'sleep')):
            with self.assertRaises(RuntimeError):
                pipeline.fetch(self.data)
        self.assertEqual(opened.call_count,3)


if __name__ == '__main__':
    unittest.main()
