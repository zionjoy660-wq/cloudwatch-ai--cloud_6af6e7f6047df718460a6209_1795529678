"""Analyses one cloud update for one team.

Two ways to analyse:
  * LLM (OpenAI)   - used when DEMO_MODE=false and OPENAI_API_KEY is set.
  * Local fallback - a transparent keyword/rule analysis, used otherwise or if the LLM call fails.
Every result is passed through normalize_analysis() so the output always has the same structure.
"""
import json
import re

from app.core.config import settings
from app.services.memory import memory, REVIEWED_ANALYSIS

MAX_CONTENT_FOR_LLM = 6000   # characters of the announcement sent to the model
HIGH_IMPACT_CATEGORIES = {"deprecation", "security", "pricing"}

SYSTEM_PROMPT = """You are a cloud change analyst helping an engineering team decide which public cloud updates matter to them.

RULES
1. Use ONLY the information in the JSON you receive. Never invent dates, versions, prices, regions, deadlines, service names or technical details.
2. Keep facts and inferences apart. "evidence" lists only things the announcement text actually states. "organizational_impact" is your reasoning about the team and must be worded as a possibility ("may", "could"), never as certain.
3. Do not say a service or project is affected unless the announcement or the team context gives evidence. If there is no evidence, say the impact is unclear.
4. "historical_context" memories are optional background. Mention a memory only if it is clearly related to this update; otherwise return an empty list. Distinguish memories of type team_context (facts entered by the team) from reviewed_analysis (earlier generated analyses, which are not facts).
5. If update.collection_type is "page_capture", the text is a captured web page that may contain many announcements; say so and keep confidence Low.
6. If update.collection_type is "release_note", the text is one entry that was cut automatically from an official provider page; the cut may be imperfect, so keep confidence at most Medium and mention that the entry should be checked at the source.
7. If update.is_demo is true, the record is an illustrative sample, not a real announcement; say so in change_summary.
8. Be honest about uncertainty and do not exaggerate risk. Use priority High only when the evidence and the team profile both support it.
9. recommended_actions must be practical and must include verifying the details in the official provider documentation.

Return ONLY a JSON object with these keys:
title (string), provider (string), change_summary (string), change_type (string),
evidence (array of short strings taken from the announcement),
team_matches (array of team services/projects that the announcement actually mentions),
affected_services (array of services named in the announcement),
relevance_score (integer 0-100), priority ("Low" | "Medium" | "High"),
organizational_impact (string), historical_context (array of strings),
recommended_actions (array of strings), confidence ("Low" | "Medium" | "High")."""


def _word_in(term, text):
    pattern = r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def find_team_matches(update, profile):
    """Team services/projects that are actually mentioned in the update (word match)."""
    text = " ".join([str(update.get("provider", "")), str(update.get("title", "")),
                     str(update.get("summary", "")), str(update.get("content", "")),
                     " ".join(update.get("services") or [])]).lower()
    terms = list(profile.get("services", [])) + list(profile.get("projects", []))
    matches = []
    for term in terms:
        if term and _word_in(term, text) and term not in matches:
            matches.append(term)
    return matches


def priority_from_score(score):
    return "High" if score >= 70 else ("Medium" if score >= 45 else "Low")


def context_labels(context):
    """Readable labels that separate team facts from earlier generated analyses."""
    return [("[Past analysis] " if m["memory_type"] == REVIEWED_ANALYSIS else "[Team context] ") + m["title"]
            for m in context]


def data_notice(update):
    if update.get("is_demo"):
        return "Illustrative sample data - this is not a real cloud announcement."
    if update.get("collection_type") == "page_capture":
        return "Based on a captured provider web page, not a single verified announcement. Check the official page."
    if update.get("collection_type") == "release_note":
        return "Entry cut automatically from an official provider page; the boundaries may be imperfect. Check the source link."
    return ""


def local_analysis(update, context, profile):
    """Rule-based analysis. Simple on purpose: every number can be explained."""
    category = update.get("category", "other")
    matches = find_team_matches(update, profile)
    score = 35 + 15 * min(len(matches), 3) + (20 if category in HIGH_IMPACT_CATEGORIES else 0)
    if not matches:
        score = min(score, 40)   # no evidence the team is involved -> keep relevance low
    is_capture = update.get("collection_type") == "page_capture"  # whole page: very uncertain

    if matches:
        impact = (f"This update mentions {', '.join(matches)} from your team profile, so it may be relevant. "
                  f"The possible impact is inferred only from the category ('{category}') and keyword matches.")
    else:
        impact = ("No service or project from your team profile is mentioned, so there is no evidence of impact. "
                  "Keep it for awareness only.")
    impact += " Verify against the official documentation and your own architecture."

    return {
        "title": update.get("title", "Untitled"),
        "provider": update.get("provider", "Unknown"),
        "change_summary": update.get("summary") or str(update.get("content", ""))[:400],
        "change_type": category,
        "evidence": [str(update.get("summary") or update.get("content", ""))[:250]],
        "team_matches": matches,
        "affected_services": update.get("services") or [],
        "relevance_score": score,
        "priority": priority_from_score(score),
        "organizational_impact": impact,
        "historical_context": context_labels(context),
        "recommended_actions": [
            "Read the official announcement and confirm the scope.",
            "Check whether the team actually uses the affected services.",
            "If relevant, assign an owner and a review date.",
        ],
        "confidence": "Low" if (is_capture or not matches) else "Medium",
    }


def normalize_analysis(out, update, context):
    """Make sure the result has every field, in the right type, and the right provenance."""
    def as_list(value):
        if isinstance(value, list):
            return [str(v) for v in value if str(v).strip()]
        return [str(value)] if value else []

    try:
        score = max(0, min(100, int(float(out.get("relevance_score", 0)))))
    except (TypeError, ValueError):
        score = 0
    priority = str(out.get("priority", "")).strip().capitalize()
    if priority not in {"Low", "Medium", "High"}:
        priority = priority_from_score(score)
    confidence = str(out.get("confidence", "")).strip().capitalize()
    if confidence not in {"Low", "Medium", "High"}:
        confidence = "Low"

    result = {
        "update_id": update.get("id", ""),
        "title": update.get("title", "Untitled"),                 # always taken from the real record
        "provider": update.get("provider", "Unknown"),
        "change_summary": str(out.get("change_summary", "")),
        "change_type": str(out.get("change_type") or update.get("category", "other")),
        "evidence": as_list(out.get("evidence")),
        "team_matches": as_list(out.get("team_matches")),
        "affected_services": as_list(out.get("affected_services")),
        "relevance_score": score,
        "priority": priority,
        "organizational_impact": str(out.get("organizational_impact", "")),
        "historical_context": as_list(out.get("historical_context")),
        "recommended_actions": as_list(out.get("recommended_actions")),
        "confidence": confidence,
        "source_url": update.get("url", ""),                      # never trust the model for these
        "is_demo": bool(update.get("is_demo", False)),
        "collection_type": update.get("collection_type", ""),
        "data_notice": data_notice(update),
    }
    return result


def _trim_update_for_llm(update):
    keep = ["provider", "title", "summary", "content", "category", "services", "url",
            "published_at", "source", "collection_type", "is_demo"]
    data = {k: update.get(k) for k in keep}
    data["content"] = str(data["content"] or "")[:MAX_CONTENT_FOR_LLM]
    return data


def analyze_update(update, profile):
    matches = find_team_matches(update, profile)
    query = " ".join([str(update.get("title", "")), " ".join(update.get("services") or []),
                      str(update.get("content", ""))[:1500]])
    memory_note = ""
    try:
        context = memory.search(query, 5, services=(update.get("services") or []) + matches,
                                exclude_title=update.get("title"), exclude_demo=not update.get("is_demo"))
    except Exception as e:   # a memory problem must never stop the analysis
        context, memory_note = [], f"Memory could not be read: {type(e).__name__}"

    llm_error = ""
    if settings.OPENAI_API_KEY and not settings.DEMO_MODE:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=45)
            payload = {
                "update": _trim_update_for_llm(update),
                "team_profile": profile,
                "historical_context": [
                    {"type": m["memory_type"], "title": m["title"], "content": m["content"][:500],
                     "services": m["services"]} for m in context],
            }
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL, temperature=0.2, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
            raw = json.loads(response.choices[0].message.content)
            if not isinstance(raw, dict):
                raise ValueError("model did not return a JSON object")
            result = normalize_analysis(raw, update, context)
            result["analysis_mode"] = "llm"
            if memory_note:
                result["memory_warning"] = memory_note
            return result
        except Exception as e:
            llm_error = f"{type(e).__name__}: {str(e)[:200]}"

    result = normalize_analysis(local_analysis(update, context, profile), update, context)
    result["analysis_mode"] = "local_fallback"
    if llm_error:
        result["llm_error"] = llm_error
    if memory_note:
        result["memory_warning"] = memory_note
    return result


REQUIRED_FIELDS = ["title", "provider", "change_summary", "change_type", "evidence", "team_matches",
                   "affected_services", "relevance_score", "priority", "organizational_impact",
                   "historical_context", "recommended_actions", "confidence", "source_url", "is_demo"]


def validate_analysis(a):
    """Automatic output checks. Returns a list of problems (empty list = all checks passed)."""
    problems = [f"missing field: {f}" for f in REQUIRED_FIELDS if f not in a]
    if problems:
        return problems
    if not a["change_summary"].strip():
        problems.append("empty summary")
    if not a["recommended_actions"]:
        problems.append("no recommended actions")
    if not any("official" in x.lower() or "verify" in x.lower() for x in a["recommended_actions"]) \
            and "official" not in a["organizational_impact"].lower():
        problems.append("no reminder to verify against official documentation")
    if a["is_demo"] and not a.get("data_notice"):
        problems.append("sample record not labelled illustrative")
    if a["priority"] == "High" and not a["team_matches"]:
        problems.append("High priority without any team match")
    return problems
