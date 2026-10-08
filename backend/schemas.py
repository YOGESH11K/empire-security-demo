"""Pydantic schemas with strict validation.

Only the minimum consented fields are accepted. No names, emails,
phone numbers, or device fingerprints.
"""
import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class LocationCreate(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    accuracy: float = Field(default=0.0, ge=0.0, le=100000.0)
    timestamp: str = Field(..., min_length=10, max_length=64)
    session_id: str = Field(..., min_length=8, max_length=64)

    @field_validator("session_id")
    @classmethod
    def _valid_session(cls, v: str) -> str:
        if not SESSION_RE.match(v):
            raise ValueError(
                "session_id must be 8-64 chars: letters, numbers, '-' or '_'"
            )
        return v

    @field_validator("timestamp")
    @classmethod
    def _valid_timestamp(cls, v: str) -> str:
        text = v.strip()
        # Accept ISO-8601 (e.g. 2026-10-08T12:00:00.000Z) or numeric epoch ms/s.
        if text.replace(".", "", 1).replace("-", "", 1).replace("+", "", 1).replace(
            ":", "", 2
        ).replace("T", "", 1).replace("Z", "", 1).strip().isdigit():
            pass  # looks numeric-ish; length check below still applies
        else:
            try:
                datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(
                    "timestamp must be ISO-8601 or epoch string"
                ) from exc
        return text


class LocationResponse(BaseModel):
    id: int
    session_id: str
    latitude: float
    longitude: float
    accuracy: float
    timestamp: str
    created_at: Optional[str] = None
    address: Optional[str] = None

    model_config = {"from_attributes": True}


class StatsResponse(BaseModel):
    total: int
    latest: Optional[LocationResponse] = None
    last_received_at: Optional[str] = None
    avg_accuracy: Optional[float] = None
    active_sessions: int = 0
