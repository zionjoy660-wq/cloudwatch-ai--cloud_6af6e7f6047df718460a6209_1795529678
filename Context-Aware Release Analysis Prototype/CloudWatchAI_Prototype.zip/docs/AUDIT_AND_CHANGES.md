# Audit and changes

## Critical problems found in the original upload
1. `app/static/app.js` had a syntax error (`}async function` with no separator), so no button, menu item or form worked.
2. `/dashboard` returned HTTP 500 on current Starlette (old `TemplateResponse` call style).

## Other fixes (high / medium)
* `POST /api/memory` accepted any JSON; one bad record could make analyze and digest crash afterwards. Now validated.
* Every digest saved duplicate analyses, which were fed back as "history". Now one record per update; an update never receives its own analysis; sample analyses are kept away from real updates.
* Memory search matched almost everything (substring + stop words, missing space in query). Now needs 2 meaningful keywords or a shared service.
* Local analysis marked every deprecation/security item High even with no link to the team. Now uses team matches as evidence.
* LLM output was trusted as-is (it could overwrite `is_demo` and `source_url`). Now validated and provenance forced by code. Prompt rewritten (facts vs inference, no invented details, uncertainty, official-doc verification).
* Service detection used substrings (`weeks` -> EKS). Now whole-word matching; deprecations are classified before pricing.
* Demo dates changed every run and looked real; live page captures received an invented publish date. Dates are no longer invented.
* Frontend: no `response.ok` checks, collection warnings only in the console, duplicate clicks possible, corrupt localStorage crashed everything, unsafe link handling. All fixed; mode banner added.
* "Memento" naming removed where it implied an external service. SQLite connections are now closed. Paths no longer depend on the working directory.

## Cosmetic
Font fallbacks, contrast, focus/disabled styles, mobile stacking, separate Team context / Past analyses lists, readable Evaluation page.

## Added to meet the course brief
* **Individual release notes:** live pages are split into one record per entry (`app/services/splitter.py`) with real publish dates where the page shows them; whole-page capture remains as a labelled fallback.
* **Question answering:** `POST /api/ask` and the Ask a question page (`app/services/qa.py`), grounded in collected updates and team memory, with citations and a fallback that never invents an answer.
* **Evaluation:** output checks, memory-context use and API timing on the Evaluation page, and `scripts/evaluate.py` for scoring against your own labels.
* **Memory:** the instructor confirmed that a Python library / SQLite is sufficient.
