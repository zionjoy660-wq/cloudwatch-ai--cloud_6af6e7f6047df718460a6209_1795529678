# CloudWatch AI – Cloud Service Change Analyst

A GenAI-assisted tool that helps cloud engineers follow public updates from cloud providers
(service updates, pricing, maintenance, deprecations) and judge which ones may matter to their team.

## What it does
1. **Collects** updates with Firecrawl from official AWS, Azure and Google Cloud pages (live mode) or loads clearly labelled illustrative samples (demo mode).
2. **Prepares** the data with Pandas: cleaning, provider/category/service detection, empty-record filtering, de-duplication, CSV export.
3. **Remembers** team context and earlier analyses in a local SQLite file.
4. **Analyses** each update with an LLM (OpenAI) or, without a key, a transparent local rule-based fallback, using the team profile and related memory.
5. **Generates** a personalised digest grouped by priority, through a FastAPI backend and a dark web dashboard.
6. **Answers questions** typed by the user (Ask a question page), using only the collected updates and saved team context, with numbered sources.

## Quick start (demo mode needs no API keys)
```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                  # keep DEMO_MODE=true for the demo
uvicorn main:app --reload
```
Open http://127.0.0.1:8000 (API docs: http://127.0.0.1:8000/docs).

## Demo mode vs live mode
| Setting | Collection | Analysis |
|---|---|---|
| `DEMO_MODE=true` (default) | 5 fixed illustrative samples, no network | local rule-based fallback |
| `DEMO_MODE=false` + `FIRECRAWL_API_KEY` | scrapes the 3 official pages | local fallback unless `OPENAI_API_KEY` is also set |
| `DEMO_MODE=false` + both keys | live Firecrawl capture | OpenAI model (`OPENAI_MODEL`, default `gpt-4o-mini`) |

* Demo records are **made up**: titles start with "Illustrative:", they have no publish date, links go only to the provider's general updates page, and every card, analysis and digest says so.
* If live collection is impossible (no key, SDK error, every page fails) the app falls back to the samples, shows a warning banner explaining why, and labels the mode `demo_fallback`. It never presents samples as live data.
* Live collection scrapes each official page with Firecrawl and **cuts it into individual release-note entries** (`app/services/splitter.py`: headings start entries, date lines give publish dates, boilerplate and tiny entries are dropped, at most 15 entries per source). Entries are labelled `release_note (auto-split)`. If a page cannot be split into at least 2 entries, it is kept as one `page_capture` record with a warning, and analysed with low confidence. The splitter uses simple rules, so entry boundaries can be imperfect; the raw page markdown is saved in `data/raw/` for checking.
* If an LLM call fails, the local analysis is used and the card shows the error.

## Project structure
```
main.py                      FastAPI app, /health, static files
app/api/routes.py            all endpoints
app/models/schemas.py        request validation (Pydantic)
app/services/collector.py    Firecrawl collection + demo/fallback logic
app/services/demo_data.py    illustrative sample records
app/services/processor.py    Pandas preprocessing
app/services/memory.py       SQLite team memory
app/services/analyzer.py     LLM prompt, local fallback, output normalisation
app/services/digest.py       priority digest
app/services/splitter.py     cuts a provider page into release-note entries
app/services/qa.py           question answering over collected updates + memory
app/templates, app/static    dashboard (HTML / CSS / JavaScript)
data/raw, data/processed     raw captures (JSON) and cleaned table (CSV)
tests/                       pytest tests
scripts/evaluate.py          compares app output with your own human labels
data/evaluation/             labelled_set.json (template to fill in)
```

## API endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | health check |
| GET | `/api/status` | mode, counts, keys configured, analysis method |
| POST | `/api/collect` | collect + preprocess updates |
| GET | `/api/updates?provider=&category=&search=` | list/filter collected updates |
| POST | `/api/analyze` | analyse one update `{update_id, team_profile}` |
| POST | `/api/digest` | analyse all updates `{team_profile, days}` |
| POST | `/api/ask` | answer a question `{question, team_profile}` |
| GET / POST | `/api/memory` | list memory / add team context |
| GET | `/api/evaluation` | workflow metrics, output checks, memory-context use, API response times |
| GET | `/api/sources` | official source pages used |

## Ask a question
The **Ask a question** page answers free-text questions such as "Which updates affect our Kubernetes work?".
1. The question is matched against the collected updates by keywords (a general question such as "What should we worry about?" ranks updates by relevance to the team profile).
2. Related team memory is looked up.
3. With an LLM, the model answers using **only** those updates and team context and must cite them as [1], [2]. The app checks the citations and warns if there are none or if a number was not provided.
4. Without an LLM, the app shows the matching updates and says clearly that this is a keyword search, not a generated answer.
5. An update counts as relevant only if it contains enough of the question's **specific** words (names such as Oracle or Kubernetes, or a category such as retirements). Broad words like "database" or "migration" help the ranking but are never enough on their own.
6. If no update is relevant, the answer is "No relevant updates were found in the collected data for this question." and no LLM call is made. Questions are not saved to memory.

## Memory
Local SQLite file `memory/cloudwatch_memory.sqlite3`, kept after restarts. It holds two kinds of records, shown separately on the Team memory page:
* **Team context** – facts you enter (not saved twice if identical).
* **Past analyses** – short summaries of analyses the app generated (one record per update; re-analysing replaces it). These are *not* verified facts.

Retrieval is keyword based: a memory is used only if it shares at least two meaningful keywords with the update or names one of its services. An update never receives its own earlier analysis, and sample-data analyses are not used for real updates. **This is not the external Memento MCP server;** the instructor confirmed that a Python library or SQLite is acceptable for the course.

## Tests
```bash
pip install pytest httpx
python -m pytest
```
The tests use temporary folders, never call the internet, and replace Firecrawl and OpenAI with mocks. They do **not** test the real Firecrawl or OpenAI services.

## Evaluation
* **Evaluation page** (measured from your own session): collected / cleaned / duplicate counts, automatic output checks on each analysis (all fields present, verification reminder, samples labelled, no High priority without a team match), how many analyses used memory context, and average/maximum response time per API endpoint.
* **`python scripts/evaluate.py`**: fill `expected_category` and `expected_priority` in `data/evaluation/labelled_set.json` yourselves, then run the script to get category and priority agreement and time per analysis. It prints no accuracy until labels exist.
* Digest quality and relevance still need human review of the generated text against the official pages.

## Limitations
* The team profile is stored in the browser (localStorage), not on the server.
* Collected updates are kept in server memory; restarting the server requires collecting again (memory records persist).
* Category and service detection use simple keyword rules; memory retrieval is keyword based, not semantic.
* Live collection (real Firecrawl and OpenAI calls) has not been tested against the real services. In particular, the splitter was tested only on sample markdown modelled on the AWS and Google Cloud page layouts, so check the real result and adjust `splitter.py` if a page splits badly.
* Question answering is limited to the 5 best-matching updates and uses keyword matching, not semantic search.
* Priority and relevance are estimates, not a formal risk score. LLM output can be wrong; always check the official provider documentation.
* There is no accuracy benchmark; the Evaluation page shows workflow counts only.
