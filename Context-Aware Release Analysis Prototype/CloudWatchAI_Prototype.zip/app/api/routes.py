"""FastAPI endpoints for CloudWatch AI."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.models.schemas import AnalyzeRequest, AskRequest, DigestRequest, MemoryCreate
from app.services.analyzer import analyze_update, validate_analysis
from app.services.collector import collect_updates
from app.services.digest import generate_digest
from app.services.memory import memory
from app.services.processor import normalize_records
from app.services.qa import answer_question

router = APIRouter()
templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))

# Collected data lives in memory for the running server (team memory is in SQLite).
STATE = {"updates": [], "mode": "not_collected", "warnings": [], "stats": {}, "analyses": {}}

# Response times of the API endpoints, measured for real while the app runs (see main.py).
PERF = {}


def analysis_mode():
    """The analysis method that will really be used right now."""
    return "llm" if settings.OPENAI_API_KEY and not settings.DEMO_MODE else "local_fallback"


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request):
    return templates.TemplateResponse(request, "index.html")


@router.get("/api/status")
def status():
    return {
        "application": settings.PROJECT_NAME,
        "mode": STATE["mode"],
        "warnings": STATE["warnings"],
        "updates": len(STATE["updates"]),
        "memory_records": memory.count(),
        "demo_mode": settings.DEMO_MODE,
        "firecrawl_configured": bool(settings.FIRECRAWL_API_KEY),
        "llm_configured": bool(settings.OPENAI_API_KEY),
        "analysis_mode": analysis_mode(),
        "memory_backend": "Local SQLite file (not an external Memento service)",
    }


@router.post("/api/collect")
def collect():
    result = collect_updates()
    df = normalize_records(result["records"])
    STATE["updates"] = df.to_dict(orient="records")
    STATE["mode"] = result["mode"]
    STATE["warnings"] = result["warnings"]
    STATE["stats"] = df.attrs.get("stats", {})
    STATE["analyses"] = {}          # earlier analyses belong to the old collection
    return {"count": len(STATE["updates"]), "mode": STATE["mode"], "warnings": STATE["warnings"],
            "stats": STATE["stats"], "updates": STATE["updates"]}


@router.get("/api/updates")
def updates(provider: str | None = None, category: str | None = None, search: str | None = None):
    data = STATE["updates"]
    if provider:
        data = [u for u in data if u.get("provider", "").lower() == provider.lower()]
    if category:
        data = [u for u in data if u.get("category", "").lower() == category.lower()]
    if search:
        q = search.lower()
        data = [u for u in data if q in (u.get("title", "") + " " + u.get("summary", "") + " " + u.get("content", "")).lower()]
    return {"count": len(data), "mode": STATE["mode"], "updates": data}


@router.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    update = next((u for u in STATE["updates"] if u.get("id") == req.update_id), None)
    if not update:
        raise HTTPException(404, "Update not found. Collect updates first.")
    result = analyze_update(update, req.team_profile.model_dump())
    memory.remember_analysis(result)
    STATE["analyses"][update["id"]] = result
    return result


@router.post("/api/digest")
def digest(req: DigestRequest):
    if not STATE["updates"]:
        raise HTTPException(400, "Collect updates first.")
    result = generate_digest(STATE["updates"], req.team_profile.model_dump(), req.days)
    for analysis in result["analyses"]:
        memory.remember_analysis(analysis)
        STATE["analyses"][analysis["update_id"]] = analysis
    return result


@router.post("/api/ask")
def ask(req: AskRequest):
    if not STATE["updates"]:
        raise HTTPException(400, "Collect updates first.")
    return answer_question(req.question, STATE["updates"], req.team_profile.model_dump())


@router.get("/api/memory")
def get_memory():
    return {"count": memory.count(), "records": memory.all(100)}


@router.post("/api/memory")
def add_memory(payload: MemoryCreate):
    memory_id, created = memory.store_context(payload.title, payload.content, payload.services)
    message = "Team context saved." if created else "This context is already saved."
    return {"id": memory_id, "created": created, "message": message}


@router.get("/api/evaluation")
def evaluation():
    items = STATE["updates"]
    categories, providers = {}, {}
    for u in items:
        categories[u.get("category", "other")] = categories.get(u.get("category", "other"), 0) + 1
        providers[u.get("provider", "Unknown")] = providers.get(u.get("provider", "Unknown"), 0) + 1
    demo = sum(bool(u.get("is_demo")) for u in items)
    with_services = sum(bool(u.get("services")) for u in items)
    records = memory.all(500)

    # Output validation and context usage over the analyses generated for this collection.
    analyses = list(STATE["analyses"].values())
    problems = {a["title"]: validate_analysis(a) for a in analyses}
    problems = {title: p for title, p in problems.items() if p}
    analysis_summary = {
        "analyses_generated": len(analyses),
        "llm_analyses": sum(a.get("analysis_mode") == "llm" for a in analyses),
        "local_analyses": sum(a.get("analysis_mode") != "llm" for a in analyses),
        "used_memory_context": sum(bool(a.get("historical_context")) for a in analyses),
        "with_team_match": sum(bool(a.get("team_matches")) for a in analyses),
        "llm_failures": sum(bool(a.get("llm_error")) for a in analyses),
        "passed_output_checks": len(analyses) - len(problems),
        "output_check_problems": problems,
    }

    # Average response time per endpoint (milliseconds), measured by the timing middleware.
    performance = {path: {"calls": v["count"], "avg_ms": round(v["total_ms"] / v["count"], 1),
                          "max_ms": round(v["max_ms"], 1)} for path, v in PERF.items() if v["count"]}
    return {
        "collected_updates": len(items),
        "mode": STATE["mode"],
        "demo_records": demo,
        "live_records": len(items) - demo,
        "category_distribution": categories,
        "provider_distribution": providers,
        "records_with_services": with_services,
        "pipeline": STATE["stats"],
        "memory_records": len(records),
        "team_context_records": sum(1 for m in records if m["memory_type"] == "team_context"),
        "analysis_records": sum(1 for m in records if m["memory_type"] == "reviewed_analysis"),
        "analysis_mode": analysis_mode(),
        "analysis_summary": analysis_summary,
        "performance": performance,
        "notes": "These are workflow metrics only. They do not measure the factual accuracy of the impact analysis, "
                 "which needs a human-labelled test set and checking against official sources "
                 "(see scripts/evaluate.py).",
    }


@router.get("/api/sources")
def sources():
    return {"sources": settings.SOURCES}
