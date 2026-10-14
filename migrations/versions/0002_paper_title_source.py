"""Retain paper title provenance so filename aliases cannot replace real titles."""
from alembic import op
from sqlalchemy import inspect, text

revision = '0002'
down_revision = '0001'


def upgrade():
    connection = op.get_bind()
    if 'title_source' not in {column['name'] for column in inspect(connection).get_columns('papers')}:
        connection.execute(text("ALTER TABLE papers ADD COLUMN title_source TEXT NOT NULL DEFAULT 'unknown'"))


def downgrade():
    raise RuntimeError('Destructive schema rollback is disabled; restore a reviewed backup')
