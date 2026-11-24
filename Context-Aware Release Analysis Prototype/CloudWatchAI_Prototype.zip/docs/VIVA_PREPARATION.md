# Viva Notes

## 30-second explanation
CloudWatch AI collects public cloud updates using Firecrawl, processes them using Pandas, retrieves historical team context from persistent memory, and uses an LLM or fallback analyzer to summarize changes, estimate relevance, identify potential impact and create a personalized digest through FastAPI.

## Pipeline
Official sources -> Firecrawl -> raw capture -> Pandas -> structured records -> memory retrieval -> LLM analysis -> impact/priority -> digest -> API/dashboard.

## Questions and answers
1. **Why this project?** Cloud teams monitor many release channels; manual review is slow. Context helps prioritize.
2. **Firecrawl?** Web extraction API/SDK that returns web content in AI-friendly formats such as Markdown.
3. **Why official sources?** They are primary references and let engineers validate claims.
4. **Pandas?** Data analysis library used to organize records, clean missing values, classify, deduplicate and export.
5. **Raw vs processed?** Raw is preserved source capture; processed is normalized data used downstream.
6. **Metadata?** Descriptive fields like provider, URL, collection time and category.
7. **Why deduplicate?** Avoid redundant processing and inflated counts.
8. **Memory?** Persisted team context, reviewed updates, services, decisions and previous impacts.
9. **Memory in this package?** A local SQLite memory with keyword retrieval (team context + earlier analyses). It is not the Memento MCP server; be accurate about this distinction. If asked why: the instructor confirmed a Python library or SQLite is enough.
10. **LLM?** Large language model that analyzes natural-language input; here it receives update and context.
11. **Why context?** It grounds relevance in team services and previous reviews.
12. **Hallucination?** Plausible but unsupported output; source links, uncertainty and human validation mitigate it.
13. **Personalization?** Team profile supplies services, projects and context to the analyzer.
14. **Priority?** Prototype estimate based on categories, matches, or model output; not a formal risk score.
15. **FastAPI?** Python framework for APIs, request validation, and interactive documentation.
16. **Uvicorn?** ASGI server that runs FastAPI.
17. **Endpoint?** URL/method exposing a feature, e.g. POST `/api/collect`.
18. **JSON?** Lightweight structured data interchange format.
19. **SQLite?** Embedded database; no separate DB server required.
20. **Demo mode?** Deterministic illustrative data for reproducible presentation without API credentials.
21. **Evaluation?** Collection/data-quality metrics plus manual review against labelled ground truth for accuracy.
22. **Limitations?** Scraping errors, heuristic classification, lexical retrieval, hallucinations, incomplete pages, no rigorous labelled benchmark.
23. **How is the LLM kept honest?** The prompt allows only supplied facts, separates `evidence` (stated) from `organizational_impact` (inferred), asks for uncertainty and official-doc verification; the code then forces provenance fields (`is_demo`, `source_url`) and validates score and priority.
24. **How is local priority computed?** 35 base + 15 per team match (max 3) + 20 for deprecation/security/pricing; capped at 40 with no team match; High >= 70, Medium >= 45.
25. **How are individual release notes found?** `splitter.py`: headings start an entry, a date-only line sets the date, short entries and cookie/navigation text are dropped; at most 15 entries per source; whole-page fallback if fewer than 2 entries. These are simple rules and can be wrong on real pages.
26. **How does question answering avoid made-up answers?** It only sends the best-matching collected updates and related memory to the model, requires numbered citations, checks them in code, and gives no answer when nothing matches. Without an LLM it only lists matching updates.
27. **Future work?** Semantic retrieval, source-specific parsers, MCP memory connection, scheduling, alerts, authentication and deployment.

## Demo honesty
Never claim sample records are live; never call local fallback an LLM result; never claim an impact is verified; explicitly explain local memory adapter versus external Memento MCP if asked.
