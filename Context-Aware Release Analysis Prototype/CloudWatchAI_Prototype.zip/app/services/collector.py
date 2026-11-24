"""Collects cloud updates.

Demo mode  -> returns the illustrative sample records (no network, no keys).
Live mode  -> scrapes the official pages listed in settings.SOURCES with Firecrawl and
              cuts each page into individual release-note entries (see splitter.py).
If live collection is not possible, the samples are returned instead and the
result says clearly WHY, so demo data is never passed off as live data.
"""
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.core.config import settings
from app.services.demo_data import sample_updates
from app.services.splitter import split_release_notes


def save_raw(records, pages=None):
    """Save the collected data before any Pandas cleaning: the page markdown and the records cut from it."""
    settings.RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = settings.RAW_DIR / f"collection_{stamp}.json"
    path.write_text(json.dumps({"pages": pages or {}, "records": records}, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def is_official_url(url):
    host = (urlparse(url or "").hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in settings.OFFICIAL_DOMAINS)


def _fallback(reason, warnings=None):
    return {
        "records": sample_updates(),
        "mode": "demo_fallback",
        "warnings": (warnings or []) + [reason, "Showing illustrative sample data. These are NOT live announcements."],
    }


def collect_updates(use_demo=None):
    demo = settings.DEMO_MODE if use_demo is None else use_demo

    if demo:
        return {"records": sample_updates(), "mode": "demo",
                "warnings": ["Demo mode: illustrative sample data loaded. These are not live announcements."]}

    if not settings.FIRECRAWL_API_KEY:
        return _fallback("Live mode is selected (DEMO_MODE=false) but FIRECRAWL_API_KEY is not set.")

    try:
        from firecrawl import Firecrawl
        client = Firecrawl(api_key=settings.FIRECRAWL_API_KEY)
    except Exception as e:  # package missing or client could not be created
        return _fallback(f"Firecrawl could not be started: {type(e).__name__}: {e}")

    records, warnings, pages = [], [], {}
    for source in settings.SOURCES:
        try:
            doc = client.scrape(source["url"], formats=["markdown"], only_main_content=True)
            markdown = getattr(doc, "markdown", "") or ""
            metadata = getattr(doc, "metadata", None)
            final_url = (getattr(metadata, "source_url", None) if metadata else None) or source["url"]
            if not markdown.strip():
                warnings.append(f"{source['provider']}: extraction returned empty content (skipped).")
                continue
            if not is_official_url(final_url):
                warnings.append(f"{source['provider']}: page URL {final_url} is not on an official domain; please verify.")
            pages[source["provider"]] = markdown
            entries = split_release_notes(markdown, final_url, source["provider"], source["name"], is_official_url)
            if len(entries) >= 2:
                if len(entries) > settings.MAX_ENTRIES_PER_SOURCE:
                    warnings.append(f"{source['provider']}: {len(entries)} release-note entries found; "
                                    f"the first {settings.MAX_ENTRIES_PER_SOURCE} are kept.")
                    entries = entries[:settings.MAX_ENTRIES_PER_SOURCE]
                collected_at = datetime.now(timezone.utc).isoformat()
                for entry in entries:
                    entry["collected_at"] = collected_at
                records.extend(entries)
            else:
                # The page could not be split reliably: keep it whole and say so.
                warnings.append(f"{source['provider']}: could not split the page into individual release notes; "
                                "kept as one whole-page capture.")
                records.append({
                    "provider": source["provider"],
                    "title": source["name"] + " page capture",
                    "summary": markdown[:600].replace("\n", " "),
                    "content": markdown,
                    "url": final_url,
                    "published_at": None,   # a page capture has no single publish date
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                    "category": "source_collection",
                    "services": [],
                    "is_demo": False,
                    "source": source["name"],
                    "collection_type": "page_capture",
                })
        except Exception as e:
            warnings.append(f"{source['provider']}: {type(e).__name__}: {str(e)[:200]}")

    if records:
        save_raw(records, pages)
        return {"records": records, "mode": "live", "warnings": warnings}
    return _fallback("Live collection failed for every source.", warnings)
