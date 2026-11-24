"""Answers a free-text question using the collected updates and the saved team memory.

Steps: (1) find the updates that match the question, (2) look up related team memory,
(3) let the LLM write a short answer that only uses those items, or - without an LLM -
list the matching updates. If nothing matches, no answer is invented.
"""
import json
import re

from app.core.config import settings
from app.services.analyzer import find_team_matches, local_analysis, data_notice, context_labels
from app.services.memory import memory, STOPWORDS
from app.services.processor import RULES

MAX_SOURCES = 5
MAX_CONTENT_FOR_LLM = 1500   # characters of each update sent to the model

# Words that only make the sentence a question; they say nothing about the topic.
QUESTION_WORDS = {"what", "which", "who", "when", "where", "why", "how", "does", "did", "should", "would", "could",
                  "about", "any", "there", "tell", "show", "give", "list", "affect", "affects", "affected",
                  "impact", "impacts", "worry", "important", "need", "our", "ours", "team", "most", "latest",
                  "recent", "anything", "something", "know", "were", "been", "being", "than", "then", "them"}

QA_PROMPT = """You answer questions for a cloud engineering team. Use ONLY the numbered updates and the team context in the JSON you receive.

RULES
1. Never invent dates, versions, prices, regions, deadlines or technical details.
2. Cite the updates you use as [1], [2] ... Every statement about an update needs a citation.
3. If the updates do not answer the question, say so plainly instead of guessing.
4. Keep what an update states apart from what you infer for this team; word inferences with "may" or "could".
5. Team context entries are facts entered by the team. Use them only when they are clearly related.
6. If an update has is_demo true, say that it is an illustrative sample and not a real announcement.
7. Write 60 to 150 words in plain English and end with a reminder to verify details in the official provider documentation."""


# More words that only belong to the sentence, not to the topic.
QUESTION_WORDS |= {"its", "first", "also", "just", "please", "like", "want", "work", "works", "working", "use",
                   "used", "using", "related", "regarding", "into", "over", "only", "other", "some", "many",
                   "much", "very", "more", "less", "get", "gets", "make", "makes"}

# Broad words that appear in many cloud updates. They are not enough on their own to say that an
# update is about the question (e.g. "database" or "migration" must not match an Oracle question).
GENERIC_WORDS = {"database", "databases", "migration", "migrate", "requirement", "requirements", "support",
                 "supported", "version", "versions", "feature", "features", "upgrade", "upgrades", "instance",
                 "instances", "resource", "resources", "data", "system", "systems", "application",
                 "applications", "configuration", "setting", "settings", "plan", "planning", "platform",
                 "product", "release", "releases", "service", "services", "cloud", "change", "changes",
                 "notice", "notices", "announcement", "announcements", "information", "info", "detail", "details"}

# At least this share of the question's specific words must be found in an update for it to count.
# If the question has only broad words (e.g. "database migration") there is no name to anchor on,
# so half of the words are enough.
MIN_COVERAGE = 0.6
MIN_COVERAGE_BROAD_ONLY = 0.5


def stem(word):
    """Very simple plural handling so that 'retirements' matches 'retirement'."""
    word = word.lower()
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith(("ss", "us", "is")) and len(word) > 3:
        return word[:-1]
    return word


GENERIC_STEMS = {stem(w) for w in GENERIC_WORDS}

# Question words that name a whole category of update (e.g. "retirements" -> deprecation).
CATEGORY_WORDS = {}
for _category in ("deprecation", "security", "pricing", "maintenance"):
    for _word in RULES[_category]:
        if _word.isalpha():
            CATEGORY_WORDS[stem(_word)] = _category


def question_tokens(question):
    """The topic words of the question: no stop words, no question words, plurals simplified."""
    tokens = []
    for word in re.findall(r"[a-z0-9+#]{2,}", question.lower()):
        if word in STOPWORDS or word in QUESTION_WORDS:
            continue
        if len(word) == 2 and not any(ch.isdigit() for ch in word):
            continue                      # drop short words like "is" or "of", keep names like "s3"
        token = stem(word)
        if token not in tokens:
            tokens.append(token)
    return tokens


def update_words(update):
    """All words of an update (simplified), used to check which question words it contains."""
    text = " ".join([update.get("title", ""), " ".join(update.get("services") or []), update.get("summary", ""),
                     str(update.get("content", ""))[:3000], update.get("provider", ""), update.get("category", "")])
    return {stem(w) for w in re.findall(r"[a-z0-9+#]{2,}", text.lower())}


def rank_updates(question, updates, profile):
    """Most relevant updates first. Returns a list of (update, score).

    An update is relevant only if it contains enough of the question's SPECIFIC words
    (names such as Oracle or Kubernetes, or a category such as retirements). Broad words like
    "database" or "migration" help the ranking but are never enough on their own.
    """
    tokens = question_tokens(question)
    scored = []
    if not tokens:
        # A general question such as "What should we worry about?": rank by relevance to the team.
        for u in updates:
            scored.append((u, local_analysis(u, [], profile)["relevance_score"]))
    else:
        specific = [t for t in tokens if t not in GENERIC_STEMS]
        min_coverage = MIN_COVERAGE if specific else MIN_COVERAGE_BROAD_ONLY
        specific = specific or tokens
        for u in updates:
            words = update_words(u)
            title_words = {stem(w) for w in re.findall(r"[a-z0-9+#]{2,}", (u.get("title", "") + " " + " ".join(u.get("services") or [])).lower())}
            category = u.get("category", "")

            def found(token):
                return token in words or CATEGORY_WORDS.get(token) == category

            matched = [t for t in specific if found(t)]
            coverage = len(matched) / len(specific)
            if coverage < min_coverage:
                continue                  # not enough of the specific words: not relevant
            broad_hits = sum(1 for t in tokens if t not in specific and found(t))
            title_hits = sum(1 for t in matched if t in title_words)
            score = 10 * coverage + 3 * title_hits + 0.3 * broad_hits + 0.5 * len(find_team_matches(u, profile))
            scored.append((u, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:MAX_SOURCES]


def _source_info(number, update):
    return {"n": number, "title": update.get("title", ""), "provider": update.get("provider", ""),
            "category": update.get("category", ""), "url": update.get("url", ""),
            "published_at": update.get("published_at", ""), "is_demo": bool(update.get("is_demo")),
            "collection_type": update.get("collection_type", "")}


def _notice(ranked):
    notices = {data_notice(u) for u, _ in ranked if data_notice(u)}
    return " ".join(sorted(notices))


def _local_answer(ranked, profile):
    lines = ["No LLM is configured, so this is a keyword search, not a generated answer. "
             "The most relevant collected updates are:"]
    for number, (u, _) in enumerate(ranked, start=1):
        matches = find_team_matches(u, profile)
        extra = f" Mentions your team's: {', '.join(matches)}." if matches else ""
        lines.append(f"[{number}] {u.get('title', '')} ({u.get('provider', '')}, {u.get('category', '')}): "
                     f"{(u.get('summary') or u.get('content', ''))[:220]}{extra}")
    lines.append("Verify details in the official provider documentation.")
    return "\n".join(lines)


def _check_citations(answer, source_count):
    """Simple output validation: the answer must cite only sources that were provided."""
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
    if not cited:
        return "The answer has no source citations; treat it with caution."
    if any(n < 1 or n > source_count for n in cited):
        return "The answer cites a source number that was not provided; treat it with caution."
    return ""


def answer_question(question, updates, profile):
    ranked = rank_updates(question, updates, profile)
    if not ranked:
        return {"question": question, "mode": "no_match", "sources": [], "team_context": [], "notice": "",
                "answer": "No relevant updates were found in the collected data for this question."}

    sources = [_source_info(i, u) for i, (u, _) in enumerate(ranked, start=1)]
    all_demo = all(s["is_demo"] for s in sources)
    query = question + " " + " ".join(u.get("title", "") for u, _ in ranked)
    services = [s for u, _ in ranked for s in (u.get("services") or [])]
    try:
        context = memory.search(query, 3, services=services, exclude_demo=not all_demo)
    except Exception:
        context = []   # a memory problem must not stop the answer

    result = {"question": question, "sources": sources, "team_context": context_labels(context),
              "notice": _notice(ranked)}

    llm_error = ""
    if settings.OPENAI_API_KEY and not settings.DEMO_MODE:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=45)
            payload = {
                "question": question,
                "team_profile": profile,
                "updates": [dict(_source_info(i, u), summary=u.get("summary", ""),
                                 content=str(u.get("content", ""))[:MAX_CONTENT_FOR_LLM],
                                 services=u.get("services") or [])
                            for i, (u, _) in enumerate(ranked, start=1)],
                "team_context": [{"type": m["memory_type"], "title": m["title"], "content": m["content"][:400]}
                                 for m in context],
            }
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL, temperature=0.2,
                messages=[{"role": "system", "content": QA_PROMPT},
                          {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
            answer = (response.choices[0].message.content or "").strip()
            if not answer:
                raise ValueError("the model returned an empty answer")
            result.update(answer=answer, mode="llm")
            warning = _check_citations(answer, len(sources))
            if warning:
                result["llm_warning"] = warning
            return result
        except Exception as e:
            llm_error = f"{type(e).__name__}: {str(e)[:200]}"

    result.update(answer=_local_answer(ranked, profile), mode="local_fallback")
    if llm_error:
        result["llm_error"] = llm_error
    return result
