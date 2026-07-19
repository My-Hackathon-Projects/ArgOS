"""initial

Clean baseline. No tables yet — add your models to app/models.py, then
`alembic revision --autogenerate -m "add <model>"`.

Revision ID: 0001
Revises:
Create Date: 2026-07-19 00:00:00.000000

"""
from alembic import op  # noqa
import sqlalchemy as sa  # noqa
import sqlmodel.sql.sqltypes  # noqa

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
