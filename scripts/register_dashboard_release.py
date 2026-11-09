#!/usr/bin/env python3
"""Register an actual public project and refresh the two GitHub Pages snapshots."""
import argparse
import subprocess
import sys
from pathlib import Path

from dashboard_releases import PUBLIC_RECORD, RECORD_LIMIT, REPOS, register_receipt, verify_publication


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", choices=REPOS, required=True)
    parser.add_argument("--commit", required=True, help="Full public release commit")
    parser.add_argument("--published-on", required=True, help="Actual Melbourne publication date YYYY-MM-DD")
    parser.add_argument("--record", type=Path, required=True, help=f"Reviewed local copy of {PUBLIC_RECORD}")
    args = parser.parse_args()
    with args.record.open("rb") as source:
        receipt = verify_publication(args.project, args.commit, args.published_on, source.read(RECORD_LIMIT + 1))
    inserted = register_receipt(receipt)
    scripts = Path(__file__).resolve().parent
    # A retry completes a previously interrupted refresh after registering the receipt.
    for command in ([scripts / "build_dashboard_data.py", "--apply-releases"],
                    [scripts / "build_dashboard_snapshot.py"]):
        subprocess.run([sys.executable, *command], check=True)
    print(f"{args.project}: {'registered' if inserted else 'already registered'} at {args.commit}")


if __name__ == "__main__":
    main()
