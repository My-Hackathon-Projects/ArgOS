"""Make `company` the single source of truth for a venture.

Three defects this closes:
  - the market writer minted a fresh Company on every run -> the dev DB held two "Nimbus Edge",
  - `founder_company` was never written by any path (0 rows), so "which ventures has this founder
    been part of" — the question a Founder Score that follows a person depends on — had no answer,
  - four of five opportunities carried a `company_name` with no `company_id`, so a named venture
    could exist with nothing to point at.

Adds the two dedup keys (`name_key`, `domain`, unique where present), merges existing duplicates,
creates the missing company rows, backfills `founder_company` from deals that already know both
sides, and seals the rule that a *named* deal must point at a company.

The name normalization below is a FROZEN COPY of app.companies.company_name_key. Migrations must
keep reproducing the same result years from now; importing live application code would let a
later refactor silently change what this migration did.
"""

import re
import unicodedata

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels = None
depends_on = None

_LEGAL_SUFFIXES = frozenset(
    {
        "gmbh", "ug", "ag", "kg", "ohg", "mbh", "eg",
        "ltd", "limited", "llc", "lp", "llp", "plc",
        "inc", "incorporated", "corp", "corporation", "co", "company",
        "bv", "nv", "sa", "sas", "sarl", "srl", "spa", "oyj", "oy", "ab", "as", "aps",
        "pte", "pty", "kk", "kft", "sro", "doo", "zoo",
    }
)  # fmt: skip


def _name_key(name: str | None) -> str | None:
    """Frozen copy of app.companies.company_name_key — do not import the live one."""
    value = unicodedata.normalize("NFKD", (name or "").casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    tokens = re.findall(r"[a-z0-9]+", value)
    if not tokens:
        return None
    stripped = [t for t in tokens if t not in _LEGAL_SUFFIXES]
    return " ".join(stripped or tokens)


def _domain_key(website: str | None) -> str | None:
    from urllib.parse import urlsplit

    raw = (website or "").strip()
    if not raw:
        return None
    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    host = parsed.netloc.casefold().removeprefix("www.").rstrip(".")
    return host or None


def upgrade() -> None:
    op.add_column("company", sa.Column("name_key", sa.String(), nullable=True))
    op.add_column("company", sa.Column("domain", sa.String(), nullable=True))
    bind = op.get_bind()

    # 1. Backfill the dedup keys in Python so they match the application byte for byte.
    for cid, name, website in bind.execute(sa.text("SELECT id, name, website FROM company")).all():
        bind.execute(
            sa.text("UPDATE company SET name_key = :k, domain = :d WHERE id = :i"),
            {"k": _name_key(name), "d": _domain_key(website), "i": cid},
        )

    # 2. Merge duplicate ventures. Survivor = the one a deal already points at, else the oldest.
    ranked = """
        WITH ranked AS (
            SELECT c.id,
                   first_value(c.id) OVER w AS keep_id,
                   row_number()      OVER w AS rn
            FROM company c
            WHERE c.name_key IS NOT NULL
            WINDOW w AS (
                PARTITION BY c.name_key
                ORDER BY (EXISTS (SELECT 1 FROM opportunity o WHERE o.company_id = c.id)) DESC,
                         c.created_at ASC, c.id ASC
            )
        )
    """
    op.execute(
        ranked + "UPDATE opportunity o SET company_id = r.keep_id "
        "FROM ranked r WHERE o.company_id = r.id AND r.rn > 1"
    )
    # Repoint founder links, skipping any that would collide with an existing edge, then drop
    # whatever still hangs off a losing row.
    op.execute(
        ranked + "UPDATE founder_company fc SET company_id = r.keep_id FROM ranked r "
        "WHERE fc.company_id = r.id AND r.rn > 1 AND NOT EXISTS ("
        "SELECT 1 FROM founder_company x "
        "WHERE x.founder_id = fc.founder_id AND x.company_id = r.keep_id)"
    )
    op.execute(
        ranked + "DELETE FROM founder_company fc USING ranked r "
        "WHERE fc.company_id = r.id AND r.rn > 1"
    )
    op.execute(ranked + "DELETE FROM company c USING ranked r WHERE c.id = r.id AND r.rn > 1")

    # 3. Every named deal gets its venture row (reusing one when the name already resolves).
    for oid, cname, sector, geo, idea in bind.execute(
        sa.text(
            "SELECT id, company_name, sector, geo, idea FROM opportunity "
            "WHERE company_name IS NOT NULL AND company_id IS NULL"
        )
    ).all():
        key = _name_key(cname)
        if key is None:
            # A name that normalizes to nothing is not a name. Clear it so the CHECK holds
            # rather than inventing an unidentifiable venture.
            bind.execute(
                sa.text("UPDATE opportunity SET company_name = NULL WHERE id = :i"), {"i": oid}
            )
            continue
        existing = bind.execute(
            sa.text("SELECT id FROM company WHERE name_key = :k LIMIT 1"), {"k": key}
        ).scalar()
        if existing is None:
            existing = bind.execute(
                sa.text(
                    "INSERT INTO company (id, name, name_key, sector, geo, description) "
                    "VALUES (gen_random_uuid(), :n, :k, :s, :g, :d) RETURNING id"
                ),
                {"n": cname.strip(), "k": key, "s": sector, "g": geo, "d": idea},
            ).scalar_one()
        bind.execute(
            sa.text("UPDATE opportunity SET company_id = :c WHERE id = :i"),
            {"c": existing, "i": oid},
        )

    # 4. Record founder <-> venture for every deal that already knows both sides.
    op.execute(
        "INSERT INTO founder_company (id, founder_id, company_id, role) "
        "SELECT gen_random_uuid(), o.founder_id, o.company_id, 'founder' FROM opportunity o "
        "WHERE o.founder_id IS NOT NULL AND o.company_id IS NOT NULL "
        "ON CONFLICT ON CONSTRAINT uq_founder_company DO NOTHING"
    )

    # 5. Seal the rules.
    op.create_index(
        "uq_company_name_key",
        "company",
        ["name_key"],
        unique=True,
        postgresql_where=sa.text("name_key IS NOT NULL"),
    )
    op.create_index(
        "uq_company_domain",
        "company",
        ["domain"],
        unique=True,
        postgresql_where=sa.text("domain IS NOT NULL"),
    )
    op.create_check_constraint(
        "ck_opportunity_named_company",
        "opportunity",
        "company_name IS NULL OR company_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_opportunity_named_company", "opportunity", type_="check")
    op.drop_index("uq_company_domain", table_name="company")
    op.drop_index("uq_company_name_key", table_name="company")
    op.drop_column("company", "domain")
    op.drop_column("company", "name_key")
