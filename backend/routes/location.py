"""Location API routes.

POST /api/location        - store one consented browser fix
GET  /api/locations       - list recent fixes (newest first)
GET  /api/location/{id}   - fetch one fix
DELETE /api/location/{id} - delete one fix
GET  /api/stats           - dashboard aggregates (convenience)
"""
import json
import time
import urllib.request
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

try:
    from backend.database import get_db
    from backend.models import Location
    from backend.schemas import LocationCreate, LocationResponse, StatsResponse
except ImportError:  # running as top-level `main` with cwd=backend/
    from database import get_db  # type: ignore
    from models import Location  # type: ignore
    from schemas import LocationCreate, LocationResponse, StatsResponse  # type: ignore

router = APIRouter(prefix="/api", tags=["locations"])

# ---- Simple in-memory rate limiting (prototype-grade) ----
# POST /api/location: max 10 requests / 60s per client IP.
_RATE: dict[str, list[float]] = defaultdict(list)
POST_LIMIT = 10
POST_WINDOW_S = 60.0


def _check_post_rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window_start = now - POST_WINDOW_S
    hits = [t for t in _RATE[client] if t > window_start]
    if len(hits) >= POST_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: max {POST_LIMIT} submissions per minute.",
        )
    hits.append(now)
    _RATE[client] = hits


def _to_response(loc: Location) -> LocationResponse:
    created = loc.created_at.isoformat() if loc.created_at else None
    return LocationResponse(
        id=loc.id,
        session_id=loc.session_id,
        latitude=loc.latitude,
        longitude=loc.longitude,
        accuracy=loc.accuracy,
        timestamp=loc.timestamp,
        created_at=created,
        address=loc.address,
    )


def reverse_geocode(lat: float, lon: float, timeout_s: float = 4.0) -> Optional[str]:
    """Turn coordinates into a readable address via Nominatim (OSM).

    Returns e.g. "12, MG Road, Robosiddhi, Jaipur, Rajasthan".
    Returns None when offline or the lookup fails — never raises.
    """
    try:
        url = (
            "https://nominatim.openstreetmap.org/reverse"
            f"?format=jsonv2&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
        )
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "EmpireSecurityDemo/1.0 (college demo project)",
                "Accept-Language": "en",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None
    addr = data.get("address") or {}
    parts: list[str] = []
    for key in (
        "house_number", "building", "residential", "road",
        "suburb", "neighbourhood", "city_district", "city",
        "town", "village", "county", "state", "postcode", "country",
    ):
        value = addr.get(key)
        if value and value not in parts:
            parts.append(value)
    if parts:
        return ", ".join(parts[:8])
    return data.get("display_name")


@router.post(
    "/location",
    response_model=LocationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Store a user-consented location fix",
)
def create_location(
    payload: LocationCreate, request: Request, db: Session = Depends(get_db)
):
    _check_post_rate_limit(request)
    address = reverse_geocode(payload.latitude, payload.longitude)
    loc = Location(
        session_id=payload.session_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy=payload.accuracy,
        timestamp=payload.timestamp,
        address=address,
    )
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return _to_response(loc)


@router.get(
    "/locations",
    response_model=list[LocationResponse],
    summary="List recent locations, newest first",
)
def list_locations(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Location)
        .order_by(desc(Location.id))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_to_response(r) for r in rows]


@router.get(
    "/location/{location_id}",
    response_model=LocationResponse,
    summary="Fetch a single location by id",
)
def get_location(location_id: int, db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    return _to_response(loc)


@router.delete(
    "/location/{location_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a single location by id",
)
def delete_location(location_id: int, db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    db.delete(loc)
    db.commit()
    return None


@router.get("/stats", response_model=StatsResponse, summary="Dashboard aggregates")
def get_stats(db: Session = Depends(get_db)):
    total: int = db.query(func.count(Location.id)).scalar() or 0
    latest_row = db.query(Location).order_by(desc(Location.id)).first()
    avg_acc = db.query(func.avg(Location.accuracy)).scalar()
    active = db.query(func.count(func.distinct(Location.session_id))).scalar() or 0

    latest = _to_response(latest_row) if latest_row else None
    last_received = latest.created_at if latest else None
    return StatsResponse(
        total=total,
        latest=latest,
        last_received_at=last_received,
        avg_accuracy=float(avg_acc) if avg_acc is not None else None,
        active_sessions=int(active),
    )
