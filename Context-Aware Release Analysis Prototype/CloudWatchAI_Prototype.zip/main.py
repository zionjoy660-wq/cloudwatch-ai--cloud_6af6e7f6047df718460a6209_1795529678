import time

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import PERF, router
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME, description="AI-powered cloud service change analyst", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")
app.include_router(router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/dashboard")


@app.get("/health")
def health():
    return {"status": "healthy", "application": settings.PROJECT_NAME}


@app.middleware("http")
async def measure_response_time(request: Request, call_next):
    """Records how long each /api endpoint takes (shown on the Evaluation page)."""
    start = time.perf_counter()
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        ms = (time.perf_counter() - start) * 1000
        entry = PERF.setdefault(f"{request.method} {request.url.path}", {"count": 0, "total_ms": 0.0, "max_ms": 0.0})
        entry["count"] += 1
        entry["total_ms"] += ms
        entry["max_ms"] = max(entry["max_ms"], ms)
    return response
