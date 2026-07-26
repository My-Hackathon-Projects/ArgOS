"""Store the canonical place id for a founder's location.

`city` and `city_key` are derived: a display name and a folded bucket. Neither is an identity.
The matcher compared `city` — the *rendered* string — so "Zürich" and "Zurich", one place with
one GeoNames id, counted as a city mismatch and weakened founder resolution.

`city_geonameid` is the shared identifier every spelling of a place resolves to. It is left
NULL for free text the gazetteer cannot resolve, which stays queryable via city/city_key.

No backfill here: the value comes from re-running reconcile_founders, which recomputes the whole
location block (city, key, country, quality, id) from raw_location through one code path. Doing
it in SQL would mean a second, drifting copy of the resolver.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("founder", sa.Column("city_geonameid", sa.Integer(), nullable=True))
    op.create_index("ix_founder_city_geonameid", "founder", ["city_geonameid"])


def downgrade() -> None:
    op.drop_index("ix_founder_city_geonameid", table_name="founder")
    op.drop_column("founder", "city_geonameid")
