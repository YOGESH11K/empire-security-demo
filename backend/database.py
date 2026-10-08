"""SQLite setup for Empire Security Demo.

College demo project: explicit, user-consented geolocation only.
No background tracking. Only stores what POST /api/location receives.
"""
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# DB file lives next to this module: backend/empire_security.db
DB_PATH = Path(__file__).resolve().parent / "empire_security.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    import os

    if os.environ.get("GIST_ID") and os.environ.get("GH_TOKEN"):
        return  # cloud mode (Vercel): gist store, no local SQLite writes
    try:
        from backend import models  # noqa: F401  (package mode)
    except ImportError:
        import models  # noqa: F401  (cwd=backend/ top-level mode)

    Base.metadata.create_all(bind=engine)
    # Lightweight migration for DB files created before `address` existed.
    try:
        with engine.begin() as conn:
            cols = [
                row[1]
                for row in conn.exec_driver_sql(
                    "PRAGMA table_info(locations)"
                ).fetchall()
            ]
            if "address" not in cols:
                conn.exec_driver_sql(
                    "ALTER TABLE locations ADD COLUMN address VARCHAR(512)"
                )
    except Exception:
        pass  # fresh DB already has the column
