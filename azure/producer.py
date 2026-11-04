"""Container Apps producer: shared source adapter, immutable uploads, ready marker last.

Actual Azure execution remains unvalidated. Local --prepare-only never loads an
Azure credential or SDK. Publication requires explicit --upload.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from retail_warehouse.pipeline import fetch, split_workbook
from prepare_batches import CLOUD_CONTRACT, prepare, sha256


def upload_immutable(service, container, name, content):
    from azure.core.exceptions import ResourceExistsError
    client=service.get_blob_client(container,name)
    digest=hashlib.sha256(content).hexdigest()
    try:
        client.upload_blob(content,overwrite=False,metadata={'sha256':digest},validate_content=True)
    except ResourceExistsError:
        existing=client.download_blob().readall()
        if hashlib.sha256(existing).hexdigest()!=digest:
            raise ValueError('Existing blob identity conflict; refusing overwrite')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook',type=Path)
    parser.add_argument('--data-dir',type=Path,default=Path('/tmp/retail-data'))
    parser.add_argument('--output-dir',type=Path,default=Path('/tmp/retail-cloud'))
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--upload',action='store_true')
    parser.add_argument('--storage-account',default=os.environ.get('RETAIL_STORAGE_ACCOUNT',''))
    args=parser.parse_args()
    if args.prepare_only==args.upload:parser.error('Choose exactly one of --prepare-only or --upload')
    manifest=split_workbook(args.workbook,args.data_dir) if args.workbook else fetch(args.data_dir)
    ready=prepare(args.data_dir,manifest,args.output_dir)
    if args.upload:
        if not re.fullmatch(r'[a-z0-9]{3,24}',args.storage_account):raise ValueError('Invalid storage account')
        from azure.identity import ManagedIdentityCredential
        from azure.storage.blob import BlobServiceClient
        # Deliberately no fallback to developer credentials or client secrets.
        with ManagedIdentityCredential() as identity, BlobServiceClient(
            f'https://{args.storage_account}.blob.core.windows.net',credential=identity) as service:
            raw=args.data_dir/manifest['raw_relative_path']
            if sha256(raw)!=manifest['source_sha256']:raise ValueError('Raw checksum mismatch')
            upload_immutable(service,'raw',f"{manifest['source_sha256']}/source.xlsx",raw.read_bytes())
            # Capture metadata changes across ephemeral job runs. Preserve each
            # capture instead of conflicting on the same content-addressed path.
            upload_immutable(service,'raw',f"{manifest['source_sha256']}/captures/{uuid4().hex}.json",
                             json.dumps(manifest,sort_keys=True,indent=2).encode())
            for entry in ready:
                file=args.output_dir/entry['batch_path']
                if sha256(file)!=entry['batch_sha256']:raise ValueError('Prepared batch changed before upload')
                upload_immutable(service,'batches',entry['batch_path'],file.read_bytes())
            # Each ready marker is immutable and appears only after ALL workbook
            # batches upload. Consumers select an explicit source SHA and date.
            for entry in ready:
                name=f"ready/{CLOUD_CONTRACT}/{entry['source_sha256']}/{entry['business_date']}.json"
                upload_immutable(service,'batches',name,json.dumps(entry,sort_keys=True,indent=2).encode())
    path=args.output_dir/'prepared-manifests.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(ready,indent=2)+'\n')
    print(json.dumps({'cloud_upload':args.upload,'dates':len(ready),'rows':sum(r['rows'] for r in ready),
                      'manifest_path':str(path)},indent=2))


if __name__=='__main__':main()
