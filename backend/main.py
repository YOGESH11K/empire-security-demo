"""FastAPI entrypoint for Empire Security Demo.

Run (from empire-security/backend):
    uvicorn main:app --reload --host 127.0.0.1 --port 8000

HTTPS-ready: terminate TLS with a reverse proxy (nginx/Caddy) or pass
    --ssl-keyfile / --ssl-certfile to uvicorn in production.
"""
from pathlib import Path
import sys

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Allow `uvicorn main:app` when cwd is backend/, and
# `uvicorn backend.main:app` when cwd is empire-security/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from backend.database import init_db  # type: ignore
    from backend.routes.location import router as location_router  # type: ignore
    from backend.routes.photo import router as photo_router  # type: ignore
except ImportError:  # fallback when imported as top-level `main`
    from database import init_db  # type: ignore
    from routes.location import router as location_router  # type: ignore
    from routes.photo import router as photo_router  # type: ignore

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Empire Security Demo API",
    description=(
        "College demonstration project for the browser Geolocation API, "
        "FastAPI, SQLite, and a Leaflet map dashboard. "
        "Location is stored ONLY after the user clicks the button and "
        "grants the browser's native permission."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: permissive for classroom demo (phone + laptop on same LAN).
# Tighten allow_origins for any public deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(location_router)
app.include_router(photo_router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "empire-security-demo"}


# Serve the landing page and dashboard from the same origin when present,
# so file:// CORS issues disappear during the college demo.
# NOTE: /dashboard must be mounted BEFORE the "/" frontend static mount,
# otherwise "/" swallows /dashboard/* requests and returns 404.
if DASHBOARD_DIR.exists():
    app.mount(
        "/dashboard", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard"
    )

if FRONTEND_DIR.exists():

    @app.get("/", include_in_schema=False)
    def _root():
        index = FRONTEND_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"status": "ok"}

    # Serves /app.js, /style.css (and /app/* alias) for the landing page.
    # Mounted AFTER the API routes + _root, so /api/* and exact "/" still win.
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=False), name="frontend-root")
