"""Pluggable storage for locations.

- Local (default): SQLite via SQLAlchemy (laptop demo, full features).
- Cloud (Vercel): a private GitHub Gist holding one JSON doc, so data
  survives serverless restarts. Enabled when GIST_ID + GH_TOKEN env exist.

Both stores expose the same record dicts:
{id, session_id, latitude, longitude, accuracy, timestamp, created_at, address}
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

try:
    from backend.database import SessionLocal
    from backend.models import Location
except ImportError:  # cwd=backend/ top-level mode
    from database import SessionLocal  # type: ignore
    from models import Location  # type: ignore


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(loc) -> dict:
    created = loc.created_at
    if isinstance(created, datetime):
        created = created.isoformat()
    return {
        "id": loc.id,
        "session_id": loc.session_id,
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "accuracy": loc.accuracy,
        "timestamp": loc.timestamp,
        "created_at": created,
        "address": getattr(loc, "address", None),
    }


class SQLiteStore:
    def create(self, *, session_id, latitude, longitude, accuracy, timestamp, address):
        db = SessionLocal()
        try:
            loc = Location(
                session_id=session_id,
                latitude=latitude,
                longitude=longitude,
                accuracy=accuracy,
                timestamp=timestamp,
                address=address,
            )
            db.add(loc)
            db.commit()
            db.refresh(loc)
            return _row_to_dict(loc)
        finally:
            db.close()

    def list(self, limit=100, offset=0):
        from sqlalchemy import desc as _desc

        db = SessionLocal()
        try:
            rows = (
                db.query(Location)
                .order_by(_desc(Location.id))
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [_row_to_dict(r) for r in rows]
        finally:
            db.close()

    def get(self, location_id):
        db = SessionLocal()
        try:
            loc = db.query(Location).filter(Location.id == location_id).first()
            return _row_to_dict(loc) if loc else None
        finally:
            db.close()

    def delete(self, location_id):
        db = SessionLocal()
        try:
            loc = db.query(Location).filter(Location.id == location_id).first()
            if not loc:
                return False
            db.delete(loc)
            db.commit()
            return True
        finally:
            db.close()

    def stats(self):
        from sqlalchemy import func as _func

        db = SessionLocal()
        try:
            items = self.list(limit=500, offset=0)
            total = db.query(_func.count(Location.id)).scalar() or 0
            avg_acc = db.query(_func.avg(Location.accuracy)).scalar()
            active = db.query(_func.count(_func.distinct(Location.session_id))).scalar() or 0
        finally:
            db.close()
        latest = items[0] if items else None
        return {
            "total": int(total),
            "latest": latest,
            "last_received_at": latest["created_at"] if latest else None,
            "avg_accuracy": float(avg_acc) if avg_acc is not None else None,
            "active_sessions": int(active),
        }


class GistStore:
    """JSON-doc store in a private gist: {"locations": [...], "seq": N}."""

    def __init__(self, gist_id: str, token: str):
        self.gist_id = gist_id
        self.token = token

    def _request(self, method: str, body: dict | None = None):
        url = f"https://api.github.com/gists/{self.gist_id}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "User-Agent": "EmpireSecurityDemo/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _read(self) -> dict:
        gist = self._request("GET")
        content = gist["files"]["db.json"]["content"]
        doc = json.loads(content or '{"locations": [], "seq": 0}')
        doc.setdefault("locations", [])
        doc.setdefault("seq", 0)
        return doc

    def _write(self, doc: dict) -> None:
        self._request(
            "PATCH", {"files": {"db.json": {"content": json.dumps(doc)}}}
        )

    def create(self, *, session_id, latitude, longitude, accuracy, timestamp, address):
        doc = self._read()
        doc["seq"] = int(doc.get("seq", 0)) + 1
        record = {
            "id": doc["seq"],
            "session_id": session_id,
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": accuracy,
            "timestamp": timestamp,
            "created_at": _utcnow_iso(),
            "address": address,
        }
        doc["locations"].append(record)
        self._write(doc)
        return record

    def list(self, limit=100, offset=0):
        doc = self._read()
        items = sorted(doc["locations"], key=lambda r: r["id"], reverse=True)
        return items[offset : offset + limit]

    def get(self, location_id):
        doc = self._read()
        for r in doc["locations"]:
            if r["id"] == location_id:
                return r
        return None

    def delete(self, location_id):
        doc = self._read()
        before = len(doc["locations"])
        doc["locations"] = [r for r in doc["locations"] if r["id"] != location_id]
        if len(doc["locations"]) == before:
            return False
        self._write(doc)
        return True

    def stats(self):
        items = self.list(limit=500, offset=0)
        sessions = {r["session_id"] for r in items if r.get("session_id")}
        accs = [r["accuracy"] for r in items if isinstance(r.get("accuracy"), (int, float))]
        latest = items[0] if items else None
        return {
            "total": len(items),
            "latest": latest,
            "last_received_at": latest["created_at"] if latest else None,
            "avg_accuracy": (sum(accs) / len(accs)) if accs else None,
            "active_sessions": len(sessions),
        }


_store = None


def get_store():
    """Singleton: GistStore on Vercel (env set), SQLiteStore otherwise."""
    global _store
    if _store is None:
        gist_id = os.environ.get("GIST_ID", "")
        token = os.environ.get("GH_TOKEN", "")
        if gist_id and token:
            _store = GistStore(gist_id, token)
        else:
            _store = SQLiteStore()
    return _store


def is_cloud_mode() -> bool:
    return bool(os.environ.get("GIST_ID") and os.environ.get("GH_TOKEN"))
