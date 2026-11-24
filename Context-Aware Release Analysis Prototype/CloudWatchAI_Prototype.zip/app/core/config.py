"""Central settings for CloudWatch AI.

All values come from environment variables (or a .env file in the project root),
so no secret is ever written in the source code.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Project root = the folder that contains main.py (two levels above this file).
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


class Settings:
    PROJECT_NAME = os.getenv("PROJECT_NAME", "CloudWatch AI")

    # DEMO_MODE=true  -> always use the built-in illustrative sample records.
    # DEMO_MODE=false -> try live Firecrawl collection (needs FIRECRAWL_API_KEY)
    #                    and use the OpenAI model (needs OPENAI_API_KEY).
    DEMO_MODE = os.getenv("DEMO_MODE", "true").strip().lower() in {"1", "true", "yes"}
    FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "").strip()
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Folders (absolute paths, so the app works no matter where it is started from).
    TEMPLATES_DIR = ROOT / "app" / "templates"
    STATIC_DIR = ROOT / "app" / "static"
    DB_PATH = ROOT / "memory" / "cloudwatch_memory.sqlite3"
    RAW_DIR = ROOT / "data" / "raw"
    PROCESSED_DIR = ROOT / "data" / "processed"

    # Official provider pages that are scraped in live mode.
    SOURCES = [
        {"provider": "AWS", "name": "AWS What's New", "url": "https://aws.amazon.com/new/"},
        {"provider": "Azure", "name": "Azure Updates", "url": "https://azure.microsoft.com/en-us/updates/"},
        {"provider": "Google Cloud", "name": "Google Cloud Release Notes", "url": "https://cloud.google.com/release-notes"},
    ]

    # Domains we treat as official. A captured page from any other domain is
    # still kept, but flagged with a warning so the user can check it.
    # At most this many release-note entries are kept per source page (keeps analysis time and cost small).
    MAX_ENTRIES_PER_SOURCE = 15

    OFFICIAL_DOMAINS = ("aws.amazon.com", "azure.microsoft.com", "cloud.google.com")


settings = Settings()
