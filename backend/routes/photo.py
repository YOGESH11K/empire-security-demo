"""Selfie API routes (explicit consent only).

The landing page shows a live camera preview and uploads ONLY when the
user taps the separate "Send My Photo" button. Files are stored under
backend/uploads/ with random names; metadata lives in the photos table.

POST   /api/photo          - upload one selfie (multipart: session_id + file)
GET    /api/photos         - list recent selfies, newest first (metadata + url)
GET    /api/photos/{id}/file - download the image bytes
DELETE /api/photo/{id}     - delete record + file
"""
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

try:
    from backend.database import SessionLocal, get_db
    from backend.models import Photo
    from backend.schemas import PhotoResponse
except ImportError:  # running as top-level `main` with cwd=backend/
    from database import SessionLocal, get_db  # type: ignore
    from models import Photo  # type: ignore
    from schemas import PhotoResponse  # type: ignore

router = APIRouter(prefix="/api", tags=["photos"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_BYTES = 3 * 1024 * 1024  # 3 MB
ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def _sniff(data: bytes, content_type: str) -> bool:
    if content_type == "image/jpeg":
        return data[:3] == b"\xff\xd8\xff"
    if content_type == "image/png":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    if content_type == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def _to_response(photo: Photo) -> PhotoResponse:
    return PhotoResponse(
        id=photo.id,
        session_id=photo.session_id,
        created_at=photo.created_at.isoformat() if photo.created_at else None,
        content_type=photo.content_type,
        url=f"/api/photos/{photo.id}/file",
    )


@router.post(
    "/photo",
    response_model=PhotoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload one explicitly-consented selfie",
)
async def upload_photo(session_id: str = Form(...), file: UploadFile = File(...)):
    if not SESSION_RE.match(session_id or ""):
        raise HTTPException(status_code=422, detail="Invalid session_id")
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED:
        raise HTTPException(
            status_code=415,
            detail="Only JPEG, PNG or WEBP photos are accepted",
        )
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Photo too large (max 3 MB)")
    if not data or not _sniff(data, content_type):
        raise HTTPException(status_code=400, detail="File is not a valid image")
    filename = uuid.uuid4().hex + ALLOWED[content_type]
    (UPLOAD_DIR / filename).write_bytes(data)

    db = SessionLocal()
    try:
        photo = Photo(
            session_id=session_id, filename=filename, content_type=content_type
        )
        db.add(photo)
        db.commit()
        db.refresh(photo)
        resp = _to_response(photo)
    finally:
        db.close()
    return resp


@router.get("/photos", response_model=list[PhotoResponse], summary="List recent selfies")
def list_photos(
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Photo).order_by(desc(Photo.id)).offset(offset).limit(limit).all()
    )
    return [_to_response(r) for r in rows]


@router.get("/photos/{photo_id}/file", summary="Download one selfie")
def get_photo_file(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    path = UPLOAD_DIR / photo.filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Photo file missing")
    return FileResponse(str(path), media_type=photo.content_type)


@router.delete(
    "/photo/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one selfie (record + file)",
)
def delete_photo(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    path = UPLOAD_DIR / photo.filename
    db.delete(photo)
    db.commit()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return None
