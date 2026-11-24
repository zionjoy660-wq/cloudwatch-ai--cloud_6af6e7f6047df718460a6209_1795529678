"""Test setup: use temporary folders so tests never touch real data or memory."""
import tempfile
from pathlib import Path

import pytest

from app.core.config import settings

_tmp = Path(tempfile.mkdtemp(prefix="cloudwatch_tests_"))
settings.DB_PATH = _tmp / "memory.sqlite3"        # must be set before memory.py is imported
settings.RAW_DIR = _tmp / "raw"
settings.PROCESSED_DIR = _tmp / "processed"
settings.DEMO_MODE = True
settings.FIRECRAWL_API_KEY = ""
settings.OPENAI_API_KEY = ""

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402
from app.api import routes  # noqa: E402
from app.services.memory import memory  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state():
    """Every test starts with an empty database and nothing collected."""
    with memory.conn() as c:
        c.execute("DELETE FROM memories")
        c.commit()
    routes.STATE.update({"updates": [], "mode": "not_collected", "warnings": [], "stats": {}, "analyses": {}})
    routes.PERF.clear()
    settings.DEMO_MODE, settings.FIRECRAWL_API_KEY, settings.OPENAI_API_KEY = True, "", ""
    yield


@pytest.fixture
def client():
    return TestClient(app)
