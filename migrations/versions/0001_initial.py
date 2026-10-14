"""Initial schema, immutable identities, fact revisions and job fencing."""
from alembic import op
from sqlalchemy import text
from robotlit.db import metadata

revision = "0001"
down_revision = None


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    metadata.create_all(connection)
    connection.execute(text("INSERT INTO revisions(id, watermark) VALUES (1, 0) ON CONFLICT(id) DO NOTHING"))
    if connection.dialect.name == "postgresql":
        connection.execute(text("CREATE INDEX IF NOT EXISTS chunks_fts ON chunks USING gin(search_vector)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS summaries_fts ON summaries USING gin(search_vector)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS chunks_vector ON chunks USING hnsw(vector vector_cosine_ops)"))


def downgrade():
    raise RuntimeError("Destructive schema rollback is disabled; restore a reviewed backup")
