"""Identity values become canonical tokens, and the resolver's decisions become durable.

Four things that all fail the same way — a comparison between two spellings of one fact — get a
schema behind them.

**`identity` values are rewritten to their canonical token.** `github` arrived 90/90 bare but in
mixed case, `linkedin` 229/229 as a full URL; `entity_resolution` compared those spellings
literally, so `0000-0002-1825-0097` and `https://orcid.org/0000-0002-1825-0097` — one researcher's
ORCID — read as two different identifiers. Because a strong identifier is person-unique, "both
sides publish one and they differ" is proof of distinctness, so a normalizer miss became a
confident wrong answer that forked one person and reset a Founder Score that must never reset.
Verified against all 542 live rows: no group collapses only after canonicalization, so this
migration repairs no live fork — it removes the mechanism before the extractor produces one. It
already does: one `twitter` column holds a `linkedin.com/in/` URL.

**Non-identifying values become NULL here, not identity.** A `linkedin.com/posts/…` URL is real
evidence about a person and no evidence of *which* person; the writer now reroutes those to
`Signal`. This migration only clears the column — 1 `/posts/` URL and 1 wrong-host twitter value.

**`founder_resolution_review` records the counterpart.** When names match but canonical strong
identifiers disagree the resolver forks, because the two error directions are not equally
recoverable: a fork is found by `find_merge_candidates` and undone by `merge_founders` with an
audit trail, while attaching one human's evidence to another is found by nothing and has no split
operation. `counterpart_founder_id` is SET NULL, not CASCADE — merging the counterpart away must
not delete the record of why the two were ever held apart.

**`entity_merge.canonical_founder_id` stops cascading.** CASCADE deleted a founder's entire merge
history the moment that founder was itself merged into someone else, which is the steady state for
an iterative deduper. Merge history is append-only: SET NULL plus an immutable
`canonical_founder_ref`, mirroring `merged_founder_ref`.

The identity indexes are deliberately NOT global per handle. Five handles are held by 2–6 founders
each (`openhelix-team` by six) — all organisation accounts, the case `non_identifying_handles`
exists for and `audit_identity` classifies as legitimate. A global unique index would make a
documented-legal state a hard error. ORCID is the exception: it identifies one researcher by
construction.

The parsers below are a FROZEN COPY of `app.identity`, per the same rule as 0011/0015: a migration
must keep reproducing the same result after the live function changes. Verified equal to the live
parsers across all 542 rows at the time of writing.

`review_fingerprint` now hashes canonical identity values, so fingerprints of the 21 existing
`founder_resolution_review` rows are stale. Harmless — a mention already recorded gets recorded
once more — and not worth rewriting rows whose input strings are gone.
"""

import re
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels = None
depends_on = None

# --- FROZEN COPY of app.identity (do not import the live module) -------------------------------

_GITHUB_RESERVED = frozenset(
    """about apps collections codespaces contact customer-storiesdashboard enterprise events
    explore features issues join login logout marketplace new notifications orgs organizations
    pricing pulls readme security settings sponsors stars topics trending signup site
    security-advisories""".split()
)
_TWITTER_RESERVED = frozenset(
    """about account compose explore hashtag home i intent jobs login logout messages notifications
    privacy search settings share signup status tos welcome who_to_follow""".split()
)
_LINKEDIN_ARTIFACT_PREFIXES = ("posts", "feed", "pulse", "company", "school", "groups", "jobs")

_GITHUB_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
_TWITTER_HANDLE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
_LINKEDIN_SLUG = re.compile(r"^[\w\-%.]{3,100}$", re.UNICODE)
_ORCID_DIGITS = re.compile(r"(\d{4})-?(\d{4})-?(\d{4})-?(\d{3}[\dXx])")

_HOSTS = {
    "github": ("github.com",),
    "twitter": ("twitter.com", "x.com"),
    "linkedin": ("linkedin.",),
}


def _segments(kind: str, raw: str) -> list[str] | None:
    value = raw.strip()
    hosts = _HOSTS[kind]
    if "://" in value or any(host in value.casefold() for host in hosts):
        parsed = urlsplit(value if "://" in value else f"https://{value}")
        host = parsed.netloc.casefold().removeprefix("www.").split(":")[0]
        if not any(known in host for known in hosts):
            return None
        return [segment for segment in parsed.path.split("/") if segment]
    return [segment for segment in value.lstrip("@").strip("/").split("/") if segment]


def _normalize_website(raw: str | None) -> str | None:
    if not raw or not raw.strip():
        return None
    parsed = urlsplit(raw.strip() if "://" in raw else f"https://{raw.strip()}")
    host = parsed.netloc.casefold().removeprefix("www.")
    if not host:
        return None
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parsed.query) if not k.startswith("trk")))
    return urlunsplit(("https", host, parsed.path.rstrip("/"), query, ""))


def _orcid_checksum_ok(digits: str) -> bool:
    if len(digits) != 16:
        return False
    total = 0
    for character in digits[:15]:
        if not character.isdigit():
            return False
        total = (total + int(character)) * 2
    remainder = (12 - total % 11) % 11
    return ("X" if remainder == 10 else str(remainder)) == digits[15].upper()


def _canonical(kind: str, raw: str | None) -> str | None:
    """The canonical token, or None when the value does not identify a person.

    Frozen mirror of `app.identity.canonical_identity`. Artifact URLs and rejects both collapse to
    None here: this migration only has to clear the column, while the live writer additionally
    reroutes an artifact to a Signal and counts a reject.
    """
    if raw is None or not str(raw).strip():
        return None
    raw = str(raw).strip()

    if kind == "website":
        return _normalize_website(raw)

    if kind == "orcid":
        match = _ORCID_DIGITS.search(raw)
        if match is None:
            return None
        digits = "".join(match.groups()).upper()
        if not _orcid_checksum_ok(digits):
            return None
        return "-".join(digits[i : i + 4] for i in range(0, 16, 4))

    segments = _segments(kind, raw)
    if not segments:
        return None

    if kind == "github":
        login = segments[0]
        if login.casefold() in _GITHUB_RESERVED or not _GITHUB_LOGIN.match(login):
            return None
        return login.casefold()

    if kind == "twitter":
        if len(segments) >= 2 and segments[1].casefold() == "status":
            return None  # a tweet permalink is an artifact, not a handle
        handle = segments[0]
        if handle.casefold() in _TWITTER_RESERVED or not _TWITTER_HANDLE.match(handle):
            return None
        return handle.casefold()

    if kind == "linkedin":
        head = segments[0].casefold()
        if head in _LINKEDIN_ARTIFACT_PREFIXES:
            return None  # a post/company/school page identifies nobody
        if head in ("in", "pub"):
            if len(segments) < 2:
                return None
            slug = segments[1]
        else:
            slug = segments[0]
        slug = unquote(slug)
        return slug.casefold() if _LINKEDIN_SLUG.match(slug) else None

    raise ValueError(f"unknown identity kind: {kind!r}")


# --- migration ---------------------------------------------------------------------------------

_KINDS = ("github", "twitter", "linkedin", "orcid", "website")


def _assert_no_duplicates(bind, query: str, what: str) -> None:
    """Refuse to create a unique index over data that violates it, with the offenders named.

    Postgres would refuse anyway, with an error that names the index and not the rows. All four
    checks pass on the live database; they exist so that when one day they do not, the operator
    is told which founders to look at instead of which index failed.
    """
    rows = bind.execute(sa.text(query)).all()
    if rows:
        raise RuntimeError(f"0016 cannot proceed: {what} — {[tuple(r) for r in rows][:10]}")


def upgrade() -> None:
    bind = op.get_bind()

    # 1. The resolver's fork decision becomes durable: who it was held apart from, and on what.
    op.add_column(
        "founder_resolution_review",
        sa.Column("counterpart_founder_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "founder_resolution_review_counterpart_founder_id_fkey",
        "founder_resolution_review",
        "founder",
        ["counterpart_founder_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "founder_resolution_review", sa.Column("conflict_kinds", sa.String(), nullable=True)
    )

    # 2. Merge history is append-only. Drop the CASCADE, keep an immutable ref.
    op.add_column("entity_merge", sa.Column("canonical_founder_ref", sa.UUID(as_uuid=True)))
    bind.execute(sa.text("UPDATE entity_merge SET canonical_founder_ref = canonical_founder_id"))
    op.alter_column("entity_merge", "canonical_founder_id", nullable=True)
    op.drop_constraint("entity_merge_canonical_founder_id_fkey", "entity_merge", type_="foreignkey")
    op.create_foreign_key(
        "entity_merge_canonical_founder_id_fkey",
        "entity_merge",
        "founder",
        ["canonical_founder_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. One person and one venture is one deal. `audit_identity` has asserted this since it was
    #    written with nothing in the database behind it, while `merge_founders` blind-UPDATEs
    #    founder_id onto the canonical row and can produce the second deal. Partial: company-less
    #    idea-stage deals may legitimately repeat.
    _assert_no_duplicates(
        bind,
        "SELECT founder_id, company_id, count(*) FROM opportunity WHERE company_id IS NOT NULL "
        "GROUP BY 1, 2 HAVING count(*) > 1",
        "two opportunities already exist for one (founder, company); merge them first",
    )
    op.create_index(
        "uq_opportunity_founder_company",
        "opportunity",
        ["founder_id", "company_id"],
        unique=True,
        postgresql_where=sa.text("company_id IS NOT NULL"),
    )

    # 4. Rewrite every identity value to its canonical form. BEFORE the indexes below: two rows
    #    holding `Ada` and `ada` for one founder are distinct today and the same identifier after,
    #    so the index must be built on the rewritten data or it would reject the rewrite.
    rows = (
        bind.execute(sa.text(f"SELECT id, {', '.join(_KINDS)} FROM identity ORDER BY id"))
        .mappings()
        .all()
    )
    rewritten = {kind: 0 for kind in _KINDS}
    cleared = {kind: 0 for kind in _KINDS}
    for row in rows:
        updates = {}
        for kind in _KINDS:
            raw = row[kind]
            if raw is None:
                continue
            value = _canonical(kind, raw)
            if value == raw:
                continue
            updates[kind] = value
            if value is None:
                cleared[kind] += 1
            else:
                rewritten[kind] += 1
        if updates:
            assignments = ", ".join(f"{kind} = :{kind}" for kind in updates)
            bind.execute(
                sa.text(f"UPDATE identity SET {assignments} WHERE id = :id"),
                {**updates, "id": row["id"]},
            )
    print(
        "[0016] identity canonicalized: "
        + ", ".join(f"{k} {rewritten[k]} rewritten/{cleared[k]} cleared" for k in _KINDS)
    )

    # 5. ORCID is globally unique; the handles are unique only per founder.
    _assert_no_duplicates(
        bind,
        "SELECT lower(orcid), count(*) FROM identity WHERE orcid IS NOT NULL "
        "GROUP BY 1 HAVING count(*) > 1",
        "one ORCID is on two founders — an ORCID identifies one researcher, so this is a bad merge",
    )
    op.create_index(
        "uq_identity_orcid",
        "identity",
        [sa.text("lower(orcid)")],
        unique=True,
        postgresql_where=sa.text("orcid IS NOT NULL"),
    )
    for kind in ("github", "linkedin", "twitter"):
        _assert_no_duplicates(
            bind,
            f"SELECT founder_id, {kind}, count(*) FROM identity WHERE {kind} IS NOT NULL "
            "GROUP BY 1, 2 HAVING count(*) > 1",
            f"one founder holds the same canonical {kind} on two identity rows",
        )
        op.create_index(
            f"uq_identity_founder_{kind}",
            "identity",
            ["founder_id", kind],
            unique=True,
            postgresql_where=sa.text(f"{kind} IS NOT NULL"),
        )


def downgrade() -> None:
    # The pre-canonical spellings are overwritten in place and the cleared values are gone.
    # Refusing beats pretending this is reversible.
    raise NotImplementedError(
        "0016 rewrites identity values in place and drops the non-identifying ones; the original "
        "spellings are not recoverable. Restore from a backup taken before the upgrade."
    )
