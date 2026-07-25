"""Reconcile duplicate founders in the local database.

Usage:
    python -m app.maintenance.reconcile_entities --dry-run
    python -m app.maintenance.reconcile_entities --apply
"""

import argparse
import json

from app.db import SessionLocal
from app.reconcile import reconcile_founders


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True)
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        result = reconcile_founders(db, dry_run=not args.apply)
        print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()
