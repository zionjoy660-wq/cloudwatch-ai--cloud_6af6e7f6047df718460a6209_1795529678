# CloudWatch AI Project Report

## Abstract
CloudWatch AI is a GenAI-assisted cloud change analyst prototype. It collects provider announcements, processes them into structured records, retrieves historical team context, and generates impact-oriented summaries and personalized digests.

## Problem Statement
Cloud engineers monitor releases, pricing, maintenance, and deprecation notices across providers. Manual monitoring is time-consuming and makes it difficult to relate changes to services and prior decisions.

## Objectives
Monitor cloud service updates; collect official source information; preprocess with Pandas; maintain historical memory; integrate LLM analysis; identify potential impacts; generate team-specific digest.

## Technologies
Python, Firecrawl, Pandas, FastAPI, Uvicorn, SQLite team memory, optional OpenAI API, HTML/CSS/JavaScript.

## Architecture and Workflow
Source collection -> raw capture -> preprocessing -> normalized dataset -> historical context retrieval -> LLM/local analysis -> priority digest -> dashboard.

## Implementation
Firecrawl scrapes source pages when configured. Pandas fills/normalizes fields, categorizes using keyword rules, detects selected services, generates stable IDs, removes duplicates and exports CSV. SQLite memory stores team context and reviewed analyses. Analyzer uses OpenAI when configured, otherwise transparent local heuristic fallback. FastAPI exposes collection, update, analysis, digest, memory, status and evaluation endpoints.

## Evaluation
Collection quality: raw, empty-removed, duplicate-removed and processed record counts plus the share of records with detected services (Evaluation page). Output validation: automatic checks on every analysis (required fields, verification reminder, illustrative label for samples, no High priority without a team match). Historical context usage: number of analyses that retrieved memory. API performance: average and maximum response time per endpoint, measured during use. Relevance and priority agreement: `scripts/evaluate.py` against a human-labelled set (record the real results and the number of items here). These measures do not prove factual accuracy; digest text must still be reviewed against official sources.

## Question answering
The Ask a question page lets a user type a question. The system retrieves the best-matching collected updates and related team memory, then either asks the LLM to answer using only that material with numbered citations (citations are checked in code) or, without an LLM, lists the matching updates. When nothing matches, no answer is produced.

## Testing
Automated pytest suite (endpoints, preprocessing, memory, error cases) with mocked Firecrawl and OpenAI. Write the exact counts from your own run here before submission. These tests do not use the real Firecrawl or OpenAI services and do not measure analysis accuracy.

## Limitations and Responsible Use
Source pages may be incomplete; keyword classification can be imperfect; memory retrieval is lexical; LLM output can hallucinate; impact is a hypothesis requiring engineering validation; demo records are illustrative.

## Conclusion
The prototype demonstrates an end-to-end monitoring workflow. Future work includes source-specific extraction, semantic memory, MCP integration, scheduled collection, alerts, authentication, deployment and a labelled evaluation benchmark.
