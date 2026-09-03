from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema_migrations():
    """No Alembic history yet (Base.metadata.create_all only creates missing
    tables, not missing columns) — apply small idempotent column additions
    here so existing rows survive model changes."""
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE threads ADD COLUMN IF NOT EXISTS extraction_result JSONB"
        ))
        conn.execute(text(
            "ALTER TABLE threads ADD COLUMN IF NOT EXISTS extraction_status VARCHAR"
        ))
