"""Re-canonicalize signal URLs and merge the artifacts that were stored twice.

`canonical_url` is the global dedup key, so a URL form the canonicalizer leaves distinct becomes
a second row for the same artifact. Three forms slipped through: the scheme (http vs https), the
path case on handle hosts (x.com/FlavioRump vs /flaviorump), and arXiv's abs/pdf/html + version
renderings of one paper.

That is not cosmetic. Claim trust is noisy-OR over evidence weights, so one artifact cited twice
reads as two independent corroborations: a single source at w=0.6 scores 0.6, the same source
duplicated scores 0.84, and `corroboration_n` reports 2. Ten live claims were inflated this way,
e.g. "Daniel San José Pro co-authored 'CRISP...'" at trust 0.903 / n=2 on one arXiv paper cited
as both /abs/ and /pdf/.

Without this migration the code fix alone would make things worse, not better: every existing row
would keep its stale key and the next run would mint a *third* row under the new one.

Attribution and evidence are moved to the surviving row before the duplicates are deleted; the
survivor is the earliest-ingested row so provenance timestamps stay truthful. Trust scores for
affected claims are NOT recomputed here (that needs the scoring code) —
`app/maintenance/recompute_trust.py` does it as an explicit follow-up.

The canonicalizer below is a FROZEN COPY of app.sourcing.graph._canonicalize, per the same rule
as 0011: a migration must keep reproducing the same result even after the live function changes.
"""

import re
from urllib.parse import urlsplit, urlunsplit

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels = None
depends_on = None

# Verified byte-for-byte against app.sourcing.graph._TRACKING at the time of writing. A frozen
# copy that DIFFERS is worse than no copy: it would key rows differently from the live code and
# the next run would mint a third row. (First draft of this file got it wrong — it invented
# "source"/"mc_cid"/"referrer" and dropped "ref_src".)
_TRACKING = frozenset(
    {
        "fbclid", "gclid", "ref", "ref_src",
        "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term",
    }
)  # fmt: skip
_CASE_INSENSITIVE_PATH_HOSTS = frozenset(
    {"x.com", "twitter.com", "github.com", "linkedin.com", "medium.com"}
)
_ARXIV_ID = re.compile(r"^/(?:abs|pdf|html)/(\d{4}\.\d{4,5})(?:v\d+)?/?$", re.IGNORECASE)


def _canonicalize(url: str) -> str:
    """Frozen copy of app.sourcing.graph._canonicalize — do not import the live one."""
    if not url:
        return url
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    q = sorted(kv for kv in parts.query.split("&") if kv and kv.split("=")[0] not in _TRACKING)
    path = parts.path.rstrip("/") or "/"
    if host in _CASE_INSENSITIVE_PATH_HOSTS:
        path = path.lower()
    if host == "arxiv.org" and (match := _ARXIV_ID.match(path)):
        path = f"/abs/{match.group(1).lower()}"
    return urlunsplit(("https", host, path, "&".join(q), ""))


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, source, external_id, canonical_url FROM signal "
            "WHERE canonical_url IS NOT NULL ORDER BY ingested_at, id"
        )
    ).all()

    # First row seen per (source, new key) wins — the ordering above makes that the earliest.
    survivors: dict[tuple[str, str], str] = {}
    merges: list[tuple[str, str]] = []  # (loser_id, winner_id)
    rekey: list[tuple[str, str]] = []  # (id, new_canonical)
    for row in rows:
        new_url = _canonicalize(row.canonical_url)
        key = (row.source, new_url)
        winner = survivors.get(key)
        if winner is None:
            survivors[key] = str(row.id)
            if new_url != row.canonical_url:
                rekey.append((str(row.id), new_url))
        else:
            merges.append((str(row.id), winner))

    for loser, winner in merges:
        params = {"loser": loser, "winner": winner}
        # Move attribution, skipping edges the winner already has (composite PK).
        bind.execute(
            sa.text(
                "UPDATE founder_signal fs SET signal_id = :winner "
                "WHERE fs.signal_id = :loser AND NOT EXISTS ("
                "SELECT 1 FROM founder_signal x "
                "WHERE x.founder_id = fs.founder_id AND x.signal_id = :winner)"
            ),
            params,
        )
        bind.execute(sa.text("DELETE FROM founder_signal WHERE signal_id = :loser"), params)
        # Move evidence, skipping edges the winner already has (uq_claim_evidence_edge). Anything
        # left is a duplicate citation of one artifact — exactly the inflation being removed.
        bind.execute(
            sa.text(
                "UPDATE claim_evidence ce SET signal_id = :winner "
                "WHERE ce.signal_id = :loser AND NOT EXISTS ("
                "SELECT 1 FROM claim_evidence x "
                "WHERE x.claim_id = ce.claim_id AND x.signal_id = :winner)"
            ),
            params,
        )
        bind.execute(sa.text("DELETE FROM claim_evidence WHERE signal_id = :loser"), params)
        bind.execute(sa.text("DELETE FROM signal WHERE id = :loser"), params)

    # Re-key the survivors last, so the UPDATE cannot collide with a duplicate still present.
    for signal_id, new_url in rekey:
        bind.execute(
            sa.text(
                "UPDATE signal SET canonical_url = :url, "
                "external_id = CASE WHEN external_id = canonical_url "
                "THEN :url ELSE external_id END "
                "WHERE id = :id"
            ),
            {"url": new_url, "id": signal_id},
        )

    print(f"[0015] merged {len(merges)} duplicate signals, re-keyed {len(rekey)}")


def downgrade() -> None:
    # Deleted rows and their attribution cannot be reconstructed, and the pre-merge URL spellings
    # are gone. Refusing beats pretending this is reversible.
    raise NotImplementedError(
        "0015 merges duplicate signal rows and drops the losing spellings; it cannot be undone. "
        "Restore from a backup taken before the upgrade."
    )
