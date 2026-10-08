"""SQLAlchemy models."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

try:
    from backend.database import Base
except ImportError:  # cwd=backend/ top-level mode
    from database import Base  # type: ignore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    accuracy: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Client-supplied ISO-8601 timestamp (when the browser fix was taken).
    timestamp: Mapped[str] = mapped_column(String(64), nullable=False)
    # Server-side receipt time.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    # Human-readable address from reverse geocoding (may be None offline).
    address: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True, default=None
    )
