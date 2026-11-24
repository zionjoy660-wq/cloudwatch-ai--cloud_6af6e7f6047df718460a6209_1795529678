"""Persistent team memory stored in a local SQLite file.

This is a simple local memory layer written for this project. It is NOT the
external Memento MCP server. Two kinds of records are stored:
  * team_context      - facts the user typed in (architecture, decisions, constraints)
  * reviewed_analysis - short summaries of analyses this app generated earlier
Retrieval is keyword based (no embeddings).
"""
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from app.core.config import settings

TEAM_CONTEXT = "team_context"
REVIEWED_ANALYSIS = "reviewed_analysis"

# Very common words are ignored when matching, otherwise everything would match.
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "will", "may", "can", "has", "have",
    "not", "you", "your", "our", "new", "update", "updated", "updates", "service", "services", "cloud",
    "illustrative", "sample", "demo", "record", "review", "before", "using", "use", "plan", "official",
    "documentation", "notice", "announcement", "change", "changes", "feature", "page", "capture",
}


def keywords(text, limit=60):
    """Meaningful lower-case words from a text (length >= 3, no stopwords)."""
    words = re.findall(r"[a-zA-Z0-9+#]{3,}", str(text).lower())
    result = []
    for w in words:
        if w not in STOPWORDS and w not in result:
            result.append(w)
    return result[:limit]


class TeamMemory:
    def __init__(self, db_path=None):
        self.db = str(db_path or settings.DB_PATH)
        settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def conn(self):
        return closing(sqlite3.connect(self.db))

    def init(self):
        with self.conn() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS memories("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, memory_type TEXT, title TEXT, content TEXT, "
                "services TEXT, provider TEXT, source_url TEXT, created_at TEXT)")
            columns = [row[1] for row in c.execute("PRAGMA table_info(memories)")]
            if "is_demo" not in columns:  # added later; keeps older database files working
                c.execute("ALTER TABLE memories ADD COLUMN is_demo INTEGER DEFAULT 0")
            c.commit()

    # ---------- writing ----------
    def _insert(self, c, kind, title, content, services, provider, url, is_demo):
        cur = c.execute(
            "INSERT INTO memories(memory_type,title,content,services,provider,source_url,created_at,is_demo) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (kind, title, content, json.dumps(services or []), provider, url,
             datetime.now(timezone.utc).isoformat(), int(is_demo)))
        return cur.lastrowid

    def store_context(self, title, content, services=None):
        """Save team context. An identical record is not saved twice. Returns (id, created)."""
        with self.conn() as c:
            row = c.execute("SELECT id FROM memories WHERE memory_type=? AND title=? AND content=?",
                            (TEAM_CONTEXT, title, content)).fetchone()
            if row:
                return row[0], False
            new_id = self._insert(c, TEAM_CONTEXT, title, content, services, "", "", False)
            c.commit()
            return new_id, True

    def remember_analysis(self, analysis):
        """Save a short summary of an analysis. Re-analysing the same update replaces the old record."""
        title = str(analysis.get("title") or "Review")
        provider = str(analysis.get("provider") or "")
        is_demo = bool(analysis.get("is_demo"))
        content = (f"Priority {analysis.get('priority')}, relevance {analysis.get('relevance_score')}%. "
                   f"Summary: {str(analysis.get('change_summary') or '')[:300]} "
                   f"Impact: {str(analysis.get('organizational_impact') or '')[:300]}")
        services = analysis.get("affected_services") or []
        with self.conn() as c:
            c.execute("DELETE FROM memories WHERE memory_type=? AND title=? AND provider=?",
                      (REVIEWED_ANALYSIS, title, provider))
            self._insert(c, REVIEWED_ANALYSIS, title, content, services, provider,
                         str(analysis.get("source_url") or ""), is_demo)
            c.commit()

    # ---------- reading ----------
    def all(self, limit=100):
        with self.conn() as c:
            rows = c.execute(
                "SELECT id,memory_type,title,content,services,provider,source_url,created_at,is_demo "
                "FROM memories ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self.row(r) for r in rows]

    def count(self):
        with self.conn() as c:
            return c.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    def search(self, query, limit=5, services=None, exclude_title=None, exclude_demo=False):
        """Return the memories most related to the query.

        A memory must share at least 2 meaningful keywords with the query, or
        mention one of the given services, otherwise it is not returned.
        """
        tokens = set(keywords(query))
        wanted = {s.lower() for s in (services or [])}
        scored = []
        for m in self.all(500):
            if exclude_title and m["memory_type"] == REVIEWED_ANALYSIS and m["title"] == exclude_title:
                continue                      # do not feed an update its own earlier analysis
            if exclude_demo and m["is_demo"]:
                continue                      # sample data must not influence real analyses
            text = (m["title"] + " " + m["content"] + " " + " ".join(m["services"])).lower()
            keyword_hits = sum(1 for t in tokens if t in text)
            service_hits = len(wanted & {s.lower() for s in m["services"]})
            if keyword_hits >= 2 or service_hits:
                scored.append((service_hits * 3 + keyword_hits, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    @staticmethod
    def row(r):
        try:
            services = json.loads(r[4] or "[]")
        except ValueError:
            services = []
        return {"id": r[0], "memory_type": r[1], "title": r[2] or "", "content": r[3] or "",
                "services": services if isinstance(services, list) else [],
                "provider": r[5] or "", "source_url": r[6] or "", "created_at": r[7] or "",
                "is_demo": bool(r[8])}


memory = TeamMemory()
