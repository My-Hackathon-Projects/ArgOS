"""Manual claim-generation run over founders with new signals.

Uses data already in the DB from the sourcing/discovery runs — no re-scraping.
Run: uv run python -m app.claims.run
"""

from app.claims.service import run_claims
from app.db import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        out = run_claims(db)
    finally:
        db.close()

    print(f"\n=== claim generation complete (job {out['job_run_id']}) ===")
    print(f"founders processed: {out['founders_processed']}")
    for r in out["results"]:
        if r.get("skipped"):
            print(f"  - {r['founder_id'][:8]} skipped ({r['skipped']})")
            continue
        fs = r.get("founder_score", {})
        comp = r.get("components", {})
        print(
            f"  - {r.get('founder')}: {r['mode']} "
            f"minted={r.get('claims_minted')} attached={r.get('evidence_attached')} "
            f"score {fs.get('before')} -> {fs.get('after')}  "
            f"[tech={comp.get('tech')} exec={comp.get('execution')} "
            f"pedigree={comp.get('pedigree')} infl={comp.get('influence')} mom={comp.get('momentum')}]"
        )


if __name__ == "__main__":
    main()
