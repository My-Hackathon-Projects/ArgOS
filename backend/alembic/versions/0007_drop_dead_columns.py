"""Drop never-used columns: signal.embedding/features, claim.embedding, opportunity.thesis_match.

Audit 2026-07-19: no code path ever wrote or queried these. As-built, founder resolution is
strong-ID + normalized-name match, claim matching is dedup_key + LLM adjudication, and the NL
compound query is a one-pass LLM ranking over the full roster (scales to ~10k founders).
Re-add an embedding tier only when a real kNN path ships with it.
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels = None
depends_on = None

EMBED_DIM = 1536


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_signal_embedding")
    op.execute("DROP INDEX IF EXISTS ix_claim_embedding")
    op.drop_column("signal", "embedding")
    op.drop_column("signal", "features")
    op.drop_column("claim", "embedding")
    op.drop_column("opportunity", "thesis_match")


def downgrade() -> None:
    op.add_column("opportunity", sa.Column("thesis_match", sa.Float()))
    op.add_column("claim", sa.Column("embedding", Vector(EMBED_DIM)))
    op.add_column("signal", sa.Column("features", JSONB))
    op.add_column("signal", sa.Column("embedding", Vector(EMBED_DIM)))
    op.execute(
        "CREATE INDEX ix_signal_embedding ON signal USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX ix_claim_embedding ON claim USING hnsw (embedding vector_cosine_ops)")
