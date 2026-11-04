"""Credential-free local CLI. This command never provisions Azure resources."""
import argparse
import json
import logging
from pathlib import Path
import sys
from .pipeline import fetch,load_batches,report,split_workbook


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    fetcher=commands.add_parser('fetch',help='Fetch public UCI ZIP and split historical daily deliveries')
    splitter=commands.add_parser('split',help='Retain and split a local UCI-shaped workbook')
    splitter.add_argument('--file',type=Path,required=True);splitter.add_argument('--source-url')
    loader=commands.add_parser('load',help='Atomically publish each selected recorded date')
    loader.add_argument('--start');loader.add_argument('--end');loader.add_argument('--allow-revert',action='store_true')
    reporter=commands.add_parser('report',help='Regenerate coherent aggregate exports')
    for command in (fetcher,splitter,loader,reporter):command.add_argument('--data-dir',type=Path,default=Path('data'))
    args=parser.parse_args(argv);logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    try:
        if args.command=='fetch':result=fetch(args.data_dir)
        elif args.command=='split':result=split_workbook(args.file,args.data_dir,args.source_url)
        elif args.command=='load':result=load_batches(args.data_dir,args.start,args.end,args.allow_revert)
        else:result=report(args.data_dir)
        print(json.dumps(result,indent=2,allow_nan=False))
    except Exception as exc:
        print(f'{type(exc).__name__}: {exc}',file=sys.stderr);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
