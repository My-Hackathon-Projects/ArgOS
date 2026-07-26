"""Identity invariants — every "one real thing, one row" rule, checked in one place.

Deduplication is spread across layers that each own one identity: the personhood gate and
resolver own founders, `app.companies` owns ventures, `app.normalize` owns places, and the
signal writers own artifacts. Each is tested in isolation. This is the cross-cutting check that
the *database* actually reflects them after a real intake run — the thing a unit test cannot
tell you, because a duplicate is a property of the whole table, not of one call.

Run: uv run python -m app.maintenance.audit_identity
Exit code is the number of violated invariants, so it can gate a cron/CI step.
"""

import sys
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import SessionLocal


@dataclass(frozen=True)
class Check:
    name: str
    why: str
    sql: str
    # "invariant" must be empty or the data is wrong. "warning" is a real-world condition worth
    # surfacing that the system already handles safely — it never gates the exit code.
    severity: str = "invariant"


# Every query returns the offending rows; empty means the invariant holds.
CHECKS: tuple[Check, ...] = (
    Check(
        "signal: (source, external_id) unique",
        "the idempotency key for polling — a duplicate means re-ingesting creates new rows",
        "SELECT source, external_id, count(*) FROM signal GROUP BY 1,2 HAVING count(*) > 1",
    ),
    Check(
        "signal: canonical_url unique per source",
        "one artifact per URL; duplicates split a claim's evidence across twin rows",
        "SELECT source, canonical_url, count(*) FROM signal WHERE canonical_url IS NOT NULL "
        "GROUP BY 1,2 HAVING count(*) > 1",
    ),
    Check(
        "signal: kind is always set",
        "founder/market provenance must be explicit (ck_signal_kind covers the domain)",
        "SELECT id FROM signal WHERE kind IS NULL",
    ),
    Check(
        "signal: market artifacts carry no founder attribution",
        "cross-table rule no CHECK can express — market evidence must stay out of the "
        "founder-claim pipeline",
        "SELECT s.id FROM signal s JOIN founder_signal fs ON fs.signal_id = s.id "
        "WHERE s.kind = 'market'",
    ),
    Check(
        "founder_signal: one edge per (founder, signal)",
        "duplicate attribution double-counts evidence in the Founder Score",
        "SELECT founder_id, signal_id, count(*) FROM founder_signal GROUP BY 1,2 "
        "HAVING count(*) > 1",
    ),
    Check(
        "founder: identity handles claimed by more than one person",
        "organisation accounts (github:TheRobotStudio on two co-founders) are legitimate, so "
        "this is not a duplicate — but the handle stops identifying anyone, and the resolver "
        "withdraws it from merge evidence (_non_identifying_handles). Surfaced for review",
        """
        SELECT lower(value) AS handle, kind, count(DISTINCT founder_id) AS founders
        FROM (
            SELECT founder_id, 'github'   AS kind, github   AS value FROM identity
            UNION ALL SELECT founder_id, 'linkedin', linkedin FROM identity
            UNION ALL SELECT founder_id, 'orcid',    orcid    FROM identity
        ) x
        WHERE value IS NOT NULL AND btrim(value) <> ''
        GROUP BY 1,2 HAVING count(DISTINCT founder_id) > 1
        """,
        severity="warning",
    ),
    Check(
        "founder: no exact display-name twins in the same place",
        "same name + same resolved place is the duplicate shape discovery used to produce",
        "SELECT lower(btrim(display_name)) AS name, city_geonameid, count(*) FROM founder "
        "WHERE display_name IS NOT NULL "
        "GROUP BY 1,2 HAVING count(*) > 1",
    ),
    Check(
        "founder: every person passes the personhood gate",
        "events and organisations must never hold a Founder Score (digits/handles/org tokens)",
        "SELECT id, display_name FROM founder "
        "WHERE display_name ~ '[0-9]' OR display_name !~ '\\s' "
        "OR display_name ~* '(hackathon|makeathon|gmbh|ltd|inc\\.?$|university|institute)'",
    ),
    Check(
        "place: one city_key never maps to two place ids",
        "a split bucket means the same city resolved two ways — the dedup key is unstable",
        "SELECT city_key, count(DISTINCT city_geonameid) FROM founder "
        "WHERE city_key IS NOT NULL AND city_geonameid IS NOT NULL "
        "GROUP BY 1 HAVING count(DISTINCT city_geonameid) > 1",
    ),
    Check(
        "place: one place id never renders under two names",
        "the display name must be canonical, or 'Zurich'/'Zürich' reappear as separate places",
        "SELECT city_geonameid, count(DISTINCT city) FROM founder "
        "WHERE city_geonameid IS NOT NULL GROUP BY 1 HAVING count(DISTINCT city) > 1",
    ),
    Check(
        "place: a resolved city always carries its country",
        "country is derived from the resolved place; missing it means a half-resolved record",
        "SELECT id, city FROM founder WHERE city_geonameid IS NOT NULL AND country_code IS NULL",
    ),
    Check(
        "company: name_key unique",
        "one venture, one row — the Nimbus Edge duplicate shape",
        "SELECT name_key, count(*) FROM company WHERE name_key IS NOT NULL "
        "GROUP BY 1 HAVING count(*) > 1",
    ),
    Check(
        "company: domain unique",
        "a website identifies one venture more strongly than its display name",
        "SELECT domain, count(*) FROM company WHERE domain IS NOT NULL "
        "GROUP BY 1 HAVING count(*) > 1",
    ),
    Check(
        "founder_company: one edge per (founder, company)",
        "duplicate edges distort 'which ventures has this founder been part of'",
        "SELECT founder_id, company_id, count(*) FROM founder_company GROUP BY 1,2 "
        "HAVING count(*) > 1",
    ),
    Check(
        "opportunity: founder-first",
        "a deal with no person has no founder axis and no Founder Score",
        "SELECT id FROM opportunity WHERE founder_id IS NULL",
    ),
    Check(
        "opportunity: a named venture points at its company",
        "ck_opportunity_named_company — a named deal with no company row",
        "SELECT id, company_name FROM opportunity "
        "WHERE company_name IS NOT NULL AND company_id IS NULL",
    ),
    Check(
        "opportunity: at most one deal per (founder, company)",
        "the same person and the same venture is one deal, not several",
        "SELECT founder_id, company_id, count(*) FROM opportunity WHERE company_id IS NOT NULL "
        "GROUP BY 1,2 HAVING count(*) > 1",
    ),
    Check(
        "claim: dedup_key unique per opportunity",
        "duplicate claims inflate the evidence count behind a market axis",
        "SELECT opportunity_id, dedup_key, count(*) FROM claim WHERE dedup_key IS NOT NULL "
        "AND opportunity_id IS NOT NULL GROUP BY 1,2 HAVING count(*) > 1",
    ),
    Check(
        "claim_evidence: one edge per (claim, signal, stance)",
        "duplicate evidence double-counts in the trust formula",
        "SELECT claim_id, signal_id, stance, count(*) FROM claim_evidence GROUP BY 1,2,3 "
        "HAVING count(*) > 1",
    ),
)


def audit(db: Session) -> list[tuple[Check, list]]:
    """Return [(check, offending_rows)] for every violated invariant."""
    failures = []
    for check in CHECKS:
        rows = db.execute(text(check.sql)).all()
        if rows:
            failures.append((check, rows))
    return failures


def main() -> int:
    db = SessionLocal()
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        failures = audit(db)
        violations = [f for f in failures if f[0].severity == "invariant"]
        for check in CHECKS:
            hit = next((f for f in failures if f[0] is check), None)
            if hit is None:
                mark = "ok"
            else:
                mark = ("FAIL" if check.severity == "invariant" else "warn") + f" ({len(hit[1])})"
            print(f"  [{mark:>9}] {check.name}")
        if failures:
            print()
            for check, rows in failures:
                label = "VIOLATION" if check.severity == "invariant" else "warning"
                print(f"{label}: {check.name}\n  why: {check.why}")
                for row in rows[:10]:
                    print(f"    {tuple(row)}")
                if len(rows) > 10:
                    print(f"    ... {len(rows) - 10} more")
        invariants = [c for c in CHECKS if c.severity == "invariant"]
        print(
            f"\n{len(invariants) - len(violations)}/{len(invariants)} identity invariants hold; "
            f"{len(failures) - len(violations)} warning(s)"
        )
        return len(violations)
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    sys.exit(main())
