"""Tests for the relevance rules of the Ask a question feature."""
import sys
import types

from app.core.config import settings
from app.services.qa import question_tokens, stem

NO_MATCH = "No relevant updates were found in the collected data for this question."


def collect(client):
    return client.post("/api/collect").json()


def ask(client, question):
    return client.post("/api/ask", json={"question": question}).json()


def titles(result):
    return [s["title"] for s in result["sources"]]


# ---------- the reported problem: broad words must not make unrelated updates relevant ----------
def test_oracle_question_returns_no_match(client):
    collect(client)
    r = ask(client, "Tell me about Oracle Database 27c and its migration requirements")
    assert r["mode"] == "no_match" and r["sources"] == [] and r["answer"] == NO_MATCH


def test_oracle_question_variants_return_no_match(client):
    collect(client)
    for question in ["oracle database migration", "Oracle Database 27c", "What are the requirements for Oracle 27c?",
                     "Is there a migration path for Oracle?"]:
        assert ask(client, question)["mode"] == "no_match", question


def test_no_match_does_not_call_the_llm(client, monkeypatch):
    collect(client)
    settings.OPENAI_API_KEY, settings.DEMO_MODE = "sk-test", False
    module = types.ModuleType("openai")

    class Boom:
        def __init__(self, **kwargs):
            raise AssertionError("the LLM must not be called when nothing matches")

    module.OpenAI = Boom
    monkeypatch.setitem(sys.modules, "openai", module)
    assert ask(client, "Tell me about Oracle Database 27c")["mode"] == "no_match"


# ---------- real questions still work ----------
def test_specific_questions_still_match(client):
    collect(client)
    assert [t[14:] for t in titles(ask(client, "Which updates affect our Kubernetes work?"))] == ["Kubernetes platform version notice"]
    assert [t[14:] for t in titles(ask(client, "Tell me about EC2 pricing"))] == ["Amazon EC2 instance family update"]
    assert [t[14:] for t in titles(ask(client, "Any Azure database maintenance?"))] == ["Azure database maintenance notice"]


def test_plural_words_match_singular_text(client):
    collect(client)
    r = ask(client, "Are there any deprecations or retirements?")
    assert sorted(t[14:] for t in titles(r)) == ["Kubernetes platform version notice", "Service retirement warning"]


def test_general_question_with_filler_word_is_ranked_not_rejected(client):
    collect(client)
    r = ask(client, "What should we worry about first?")
    assert r["mode"] == "local_fallback" and len(r["sources"]) == 5 and "Kubernetes" in r["sources"][0]["title"]


def test_question_with_only_broad_words_is_accepted_when_half_match(client):
    collect(client)
    r = ask(client, "database migration")
    assert len(r["sources"]) >= 1 and all(s["is_demo"] for s in r["sources"])


def test_partly_matching_specific_words_are_not_enough(client):
    collect(client)
    # "Kubernetes" matches, "Oracle" does not: only 1 of 2 specific words -> below the 60% rule
    assert ask(client, "Kubernetes and Oracle")["mode"] == "no_match"


def test_category_word_matches_category(client):
    collect(client)
    r = ask(client, "pricing")
    assert "Cloud pricing information updated" in titles(r)[0] or any("pricing" in t.lower() for t in titles(r))


# ---------- small helpers ----------
def test_stem_and_tokens():
    assert stem("retirements") == "retirement" and stem("policies") == "policy" and stem("status") == "status"
    assert question_tokens("Which updates affect our Kubernetes work?") == ["kubernete"]
    assert "27c" in question_tokens("Oracle 27c") and "s3" in question_tokens("What about S3?")
    assert question_tokens("What should we worry about first?") == []
