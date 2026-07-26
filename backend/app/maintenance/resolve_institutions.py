"""Resolve every affiliation string in founder.education to a ROR id.

Kept out of discovery on purpose: intake must not depend on a third-party API being up. This is
an explicit enrichment pass, safe to re-run — `institution_alias` caches every decision including
misses, so a second run makes no network calls at all.

Run: uv run python -m app.maintenance.resolve_institutions [--dry-run]
"""

import sys
from collections import Counter

import httpx
from sqlalchemy import select

from app.db import SessionLocal
from app.institutions import ROR_TIMEOUT_SECONDS, institution_key, resolve_institution
from app.models import Founder, Institution, InstitutionAlias


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    db = SessionLocal()
    try:
        strings: Counter[str] = Counter()
        for (education,) in db.execute(select(Founder.education)).all():
            for entry in education or []:
                school = (entry.get("school") or "").strip()
                if school:
                    strings[school] += 1

        keys = {institution_key(s) for s in strings}
        keys.discard(None)
        cached = {
            row.alias_key
            for row in db.execute(select(InstitutionAlias)).scalars()
            if row.alias_key in keys
        }
        print(f"distinct affiliation strings : {len(strings)}")
        print(f"distinct cache keys          : {len(keys)}")
        print(f"already resolved (cached)    : {len(cached)}")
        print(f"ROR calls needed             : {len(keys) - len(cached)}")
        if dry_run:
            return 0

        resolved = unresolved = 0
        with httpx.Client(timeout=ROR_TIMEOUT_SECONDS, follow_redirects=True) as client:
            # Ordered by frequency so the strings that matter most land first if a run is cut off.
            for school, _count in strings.most_common():
                institution = resolve_institution(db, school, client=client)
                if institution is None:
                    unresolved += 1
                else:
                    resolved += 1
        db.commit()

        print(f"\nresolved   : {resolved}")
        print(f"unresolved : {unresolved}")
        print(f"institutions: {db.execute(select(Institution)).scalars().all().__len__()}")
        print("\ntop institutions by founders sharing them:")
        rows = db.execute(
            select(Institution.name, Institution.ror_id, Institution.country_code)
        ).all()
        by_ror = {r.ror_id: r for r in rows}
        counts: Counter[str] = Counter()
        for school, count in strings.items():
            key = institution_key(school)
            alias = db.execute(
                select(InstitutionAlias).where(InstitutionAlias.alias_key == key)
            ).scalar_one_or_none()
            if alias and alias.institution_id:
                institution = db.get(Institution, alias.institution_id)
                if institution:
                    counts[institution.ror_id] += count
        for ror_id, count in counts.most_common(10):
            row = by_ror.get(ror_id)
            if row:
                print(f"  {count:4}  {ror_id:12} {row.country_code or '--'}  {row.name}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
