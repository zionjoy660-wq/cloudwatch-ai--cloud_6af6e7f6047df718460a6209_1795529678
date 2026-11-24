# Memory implementation note
The project's memory is a **local SQLite database** (`app/services/memory.py`, class `TeamMemory`), used as a Python-library style memory layer.
It is **not** the Memento MCP server and does not connect to any external memory service.

**Instructor confirmation:** when asked which Memento to use, the instructor replied that a Python library is fine and that SQLite is also enough (WhatsApp reply, 21 Nov 2026). Keep a screenshot of this reply with your submission.

* Stores two record types: `team_context` (entered by the user) and `reviewed_analysis` (summaries of generated analyses).
* Retrieves by keyword overlap (at least two meaningful keywords, or a shared service name); there are no embeddings.
* Persists in `memory/cloudwatch_memory.sqlite3` across restarts.
