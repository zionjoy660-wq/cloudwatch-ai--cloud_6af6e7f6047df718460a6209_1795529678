import sys
import types

from app.api import routes
from app.core.config import settings


def collect(client):
    return client.post("/api/collect").json()


# ---------- basic endpoints ----------
def test_health(client):
    assert client.get("/health").json()["status"] == "healthy"


def test_dashboard_page_loads(client):
    r = client.get("/dashboard")
    assert r.status_code == 200 and "CloudWatch AI" in r.text


def test_root_redirects_to_dashboard(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/dashboard"


def test_static_files_served(client):
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_status_before_collect(client):
    s = client.get("/api/status").json()
    assert s["mode"] == "not_collected" and s["demo_mode"] is True and s["analysis_mode"] == "local_fallback"


def test_sources(client):
    assert len(client.get("/api/sources").json()["sources"]) == 3


# ---------- demo mode ----------
def test_demo_collect_is_labelled_and_deterministic(client):
    first, second = collect(client), collect(client)
    assert first["mode"] == "demo" and first["count"] == 5
    assert all(u["is_demo"] for u in first["updates"])
    assert all(u["published_at"] == "" for u in first["updates"])          # no invented dates
    assert [u["id"] for u in first["updates"]] == [u["id"] for u in second["updates"]]
    assert "not live" in first["warnings"][0].lower()


def test_demo_analysis_is_marked_illustrative(client):
    updates = collect(client)["updates"]
    a = client.post("/api/analyze", json={"update_id": updates[0]["id"]}).json()
    assert a["is_demo"] is True and "Illustrative" in a["data_notice"] and a["analysis_mode"] == "local_fallback"


def test_updates_filtering(client):
    collect(client)
    assert client.get("/api/updates?provider=aws").json()["count"] == 2
    assert client.get("/api/updates?category=pricing").json()["count"] == 1
    assert client.get("/api/updates?search=retirement").json()["count"] == 1
    assert client.get("/api/updates?search=zzzz").json()["count"] == 0


# ---------- analysis and digest ----------
def test_analysis_has_all_fields(client):
    u = collect(client)["updates"][0]
    a = client.post("/api/analyze", json={"update_id": u["id"]}).json()
    for key in ["change_summary", "organizational_impact", "affected_services", "relevance_score", "priority",
                "confidence", "historical_context", "recommended_actions", "evidence", "team_matches", "source_url"]:
        assert key in a


def test_no_team_match_keeps_priority_low(client):
    updates = collect(client)["updates"]
    k8s = next(u for u in updates if "Kubernetes" in u["title"])
    profile = {"services": ["Oracle"], "projects": []}
    a = client.post("/api/analyze", json={"update_id": k8s["id"], "team_profile": profile}).json()
    assert a["priority"] == "Low" and a["team_matches"] == []


def test_digest_groups_and_does_not_duplicate_memory(client):
    collect(client)
    d1 = client.post("/api/digest", json={}).json()
    assert d1["generated_count"] == 5
    assert len(d1["high_priority"]) + len(d1["medium_priority"]) + len(d1["low_priority"]) == 5
    assert "illustrative" in d1["executive_summary"].lower()
    client.post("/api/digest", json={})
    assert client.get("/api/memory").json()["count"] == 5        # same 5 records, not 10


def test_memory_context_is_retrieved_in_analysis(client):
    updates = collect(client)["updates"]
    client.post("/api/memory", json={"title": "Container platform", "content": "Our Kubernetes clusters run production",
                                     "services": ["Kubernetes"]})
    k8s = next(u for u in updates if "Kubernetes" in u["title"])
    a = client.post("/api/analyze", json={"update_id": k8s["id"]}).json()
    assert any("Container platform" in h for h in a["historical_context"])


# ---------- memory endpoints ----------
def test_memory_validation(client):
    assert client.post("/api/memory", json={}).status_code == 422
    assert client.post("/api/memory", json={"content": "   "}).status_code == 422
    assert client.post("/api/memory", json={"content": 123, "title": None}).status_code == 422
    assert client.post("/api/memory", content="not json", headers={"content-type": "application/json"}).status_code == 422
    assert client.get("/api/memory").json()["count"] == 0


def test_memory_duplicate_context_not_stored_twice(client):
    body = {"title": "A", "content": "B", "services": ["EKS"]}
    assert client.post("/api/memory", json=body).json()["created"] is True
    assert client.post("/api/memory", json=body).json()["created"] is False
    assert client.get("/api/memory").json()["count"] == 1


def test_memory_with_string_services_is_rejected_not_stored(client):
    assert client.post("/api/memory", json={"content": "x", "services": "EKS"}).status_code == 422


def test_memory_persists_after_restart(client):
    client.post("/api/memory", json={"content": "persist me"})
    from app.services.memory import TeamMemory
    reopened = TeamMemory(settings.DB_PATH)          # a brand-new object reading the same file
    assert reopened.count() == 1 and reopened.all()[0]["content"] == "persist me"


# ---------- error handling ----------
def test_error_cases(client):
    assert client.post("/api/digest", json={}).status_code == 400
    assert client.post("/api/analyze", json={"update_id": "nope"}).status_code == 404
    assert client.post("/api/analyze", json={}).status_code == 422
    assert client.post("/api/digest", json={"days": 0}).status_code == 422
    assert client.post("/api/analyze", json={"update_id": "x", "team_profile": {"services": "AWS"}}).status_code == 422


def test_evaluation_endpoint(client):
    collect(client)
    e = client.get("/api/evaluation").json()
    assert e["collected_updates"] == 5 and e["demo_records"] == 5 and e["live_records"] == 0
    assert e["pipeline"]["raw_count"] == 5 and "do not measure" in e["notes"]


def test_evaluation_before_collect(client):
    assert client.get("/api/evaluation").json()["collected_updates"] == 0


# ---------- live mode with MOCKED services (no network, no real keys) ----------
def _fake_firecrawl(markdown_by_url, fail_urls=()):
    class Doc:
        def __init__(self, md, url):
            self.markdown = md
            self.metadata = types.SimpleNamespace(source_url=url)

    class Client:
        def __init__(self, api_key):
            pass

        def scrape(self, url, **kwargs):
            if url in fail_urls:
                raise RuntimeError("boom")
            return Doc(markdown_by_url.get(url, ""), url)

    module = types.ModuleType("firecrawl")
    module.Firecrawl = Client
    return module


def test_live_mode_without_key_falls_back_with_explanation(client):
    settings.DEMO_MODE = False
    r = collect(client)
    assert r["mode"] == "demo_fallback" and any("FIRECRAWL_API_KEY" in w for w in r["warnings"])


def test_live_collection_with_mocked_firecrawl(client, monkeypatch):
    settings.DEMO_MODE, settings.FIRECRAWL_API_KEY = False, "fc-test"
    pages = {s["url"]: f"# {s['provider']} page\nNew EC2 feature and pricing news" for s in settings.SOURCES}
    monkeypatch.setitem(sys.modules, "firecrawl", _fake_firecrawl(pages, fail_urls=[settings.SOURCES[1]["url"]]))
    r = collect(client)
    assert r["mode"] == "live" and r["count"] == 2
    assert all(u["is_demo"] is False and u["collection_type"] == "page_capture" and u["published_at"] == "" for u in r["updates"])
    assert any("Azure" in w for w in r["warnings"])                  # the failed source is reported
    a = client.post("/api/analyze", json={"update_id": r["updates"][0]["id"]}).json()
    assert "page" in a["data_notice"].lower() and a["confidence"] == "Low"


def test_live_total_failure_is_reported_not_hidden(client, monkeypatch):
    settings.DEMO_MODE, settings.FIRECRAWL_API_KEY = False, "fc-test"
    monkeypatch.setitem(sys.modules, "firecrawl", _fake_firecrawl({}, fail_urls=[s["url"] for s in settings.SOURCES]))
    r = collect(client)
    assert r["mode"] == "demo_fallback" and all(u["is_demo"] for u in r["updates"])
    assert any("NOT live" in w for w in r["warnings"])


def _fake_openai(content):
    class Completions:
        def create(self, **kwargs):
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content))])

    class Client:
        def __init__(self, **kwargs):
            self.chat = types.SimpleNamespace(completions=Completions())

    module = types.ModuleType("openai")
    module.OpenAI = Client
    return module


def test_llm_output_is_normalised_and_cannot_fake_provenance(client, monkeypatch):
    settings.OPENAI_API_KEY, settings.DEMO_MODE = "sk-test", False
    bad = '{"relevance_score": "999", "priority": "urgent", "is_demo": false, "source_url": "javascript:alert(1)", "recommended_actions": "check docs"}'
    monkeypatch.setitem(sys.modules, "openai", _fake_openai(bad))
    routes.STATE["updates"] = [{"id": "u1", "provider": "AWS", "title": "T", "content": "c", "summary": "s",
                                "category": "pricing", "services": [], "url": "https://aws.amazon.com/new/", "is_demo": True}]
    a = client.post("/api/analyze", json={"update_id": "u1"}).json()
    assert a["analysis_mode"] == "llm" and a["relevance_score"] == 100 and a["priority"] == "High"
    assert a["is_demo"] is True and a["source_url"] == "https://aws.amazon.com/new/"
    assert a["recommended_actions"] == ["check docs"] and a["data_notice"]


def test_llm_failure_falls_back_to_local(client, monkeypatch):
    settings.OPENAI_API_KEY, settings.DEMO_MODE = "sk-test", False
    monkeypatch.setitem(sys.modules, "openai", _fake_openai("this is not json"))
    routes.STATE["updates"] = [{"id": "u1", "provider": "AWS", "title": "T", "content": "c", "summary": "s",
                                "category": "pricing", "services": [], "url": "", "is_demo": False}]
    a = client.post("/api/analyze", json={"update_id": "u1"}).json()
    assert a["analysis_mode"] == "local_fallback" and a["llm_error"]


# ---------- evaluation: output checks, context usage, performance ----------
def test_evaluation_reports_output_checks_and_context_use(client):
    updates = collect(client)["updates"]
    client.post("/api/memory", json={"title": "Container platform", "content": "Kubernetes clusters run production",
                                     "services": ["Kubernetes"]})
    client.post("/api/digest", json={})
    s = client.get("/api/evaluation").json()["analysis_summary"]
    assert s["analyses_generated"] == 5 and s["passed_output_checks"] == 5 and s["output_check_problems"] == {}
    assert s["used_memory_context"] >= 1 and s["local_analyses"] == 5 and s["llm_analyses"] == 0


def test_evaluation_before_any_analysis(client):
    collect(client)
    assert client.get("/api/evaluation").json()["analysis_summary"]["analyses_generated"] == 0


def test_performance_is_measured(client):
    collect(client)
    perf = client.get("/api/evaluation").json()["performance"]
    assert perf["POST /api/collect"]["calls"] == 1 and perf["POST /api/collect"]["avg_ms"] >= 0


def test_validate_analysis_catches_problems():
    from app.services.analyzer import validate_analysis
    assert validate_analysis({})[0].startswith("missing field")
    bad = {"title": "t", "provider": "p", "change_summary": "s", "change_type": "c", "evidence": [], "team_matches": [],
           "affected_services": [], "relevance_score": 90, "priority": "High", "organizational_impact": "x",
           "historical_context": [], "recommended_actions": ["do a thing"], "confidence": "Low",
           "source_url": "", "is_demo": True, "data_notice": ""}
    problems = validate_analysis(bad)
    assert "High priority without any team match" in problems
    assert "sample record not labelled illustrative" in problems
    assert "no reminder to verify against official documentation" in problems


# ---------- live collection split into individual release notes (mocked Firecrawl) ----------
def test_live_collection_splits_pages_into_release_notes(client, monkeypatch):
    from tests.test_splitter import AWS_STYLE, GOOGLE_STYLE
    settings.DEMO_MODE, settings.FIRECRAWL_API_KEY = False, "fc-test"
    pages = {settings.SOURCES[0]["url"]: AWS_STYLE, settings.SOURCES[2]["url"]: GOOGLE_STYLE,
             settings.SOURCES[1]["url"]: "# Only one heading\nNot enough structure to split into several entries at all here."}
    monkeypatch.setitem(sys.modules, "firecrawl", _fake_firecrawl(pages))
    r = collect(client)
    types_found = {u["collection_type"] for u in r["updates"]}
    assert r["mode"] == "live" and types_found == {"release_note", "page_capture"}
    assert r["count"] == 2 + 3 + 1                            # AWS 2, Google 3, Azure kept as one page
    assert any("could not split" in w and "Azure" in w for w in r["warnings"])
    note = next(u for u in r["updates"] if "Lambda" in u["title"])
    assert note["category"] == "deprecation" and note["published_at"].startswith("2026-11-18")
    assert note["is_demo"] is False
    a = client.post("/api/analyze", json={"update_id": note["id"]}).json()
    assert "automatically" in a["data_notice"] and a["confidence"] in ("Low", "Medium")


def test_entry_limit_per_source(client, monkeypatch):
    settings.DEMO_MODE, settings.FIRECRAWL_API_KEY = False, "fc-test"
    monkeypatch.setattr(settings, "MAX_ENTRIES_PER_SOURCE", 2)
    many = "\n".join(f"### Entry number {i}\nThis is the body of entry number {i} with enough text to be kept as an entry." for i in range(6))
    monkeypatch.setitem(sys.modules, "firecrawl", _fake_firecrawl({settings.SOURCES[0]["url"]: many}))
    r = collect(client)
    assert r["count"] == 2 and any("first 2 are kept" in w for w in r["warnings"])


def test_old_entries_skipped_by_digest_window(client, monkeypatch):
    settings.DEMO_MODE, settings.FIRECRAWL_API_KEY = False, "fc-test"
    old = ("### Old note\nPosted on: Jan 5, 2020\nAn old announcement with enough text to be kept as its own entry here.\n"
           "### Another\nPosted on: Jan 6, 2020\nAnother old announcement dated in 2020 with enough text to be kept as an entry too.")
    monkeypatch.setitem(sys.modules, "firecrawl", _fake_firecrawl({settings.SOURCES[0]["url"]: old}))
    collect(client)
    d = client.post("/api/digest", json={"days": 30}).json()
    assert d["generated_count"] == 0 and d["skipped_outside_window"] >= 1 and "skipped" in d["executive_summary"]


# ---------- ask a question ----------
def test_ask_requires_collected_updates_and_valid_question(client):
    assert client.post("/api/ask", json={"question": "What changed?"}).status_code == 400
    collect(client)
    assert client.post("/api/ask", json={}).status_code == 422
    assert client.post("/api/ask", json={"question": "  a "}).status_code == 422
    assert client.post("/api/ask", json={"question": "x" * 501}).status_code == 422


def test_ask_specific_question_returns_matching_source(client):
    collect(client)
    r = client.post("/api/ask", json={"question": "Which updates affect our Kubernetes work?"}).json()
    assert r["mode"] == "local_fallback" and len(r["sources"]) == 1 and "Kubernetes" in r["sources"][0]["title"]
    assert "not a generated answer" in r["answer"] and "Illustrative sample" in r["notice"]


def test_ask_general_question_ranks_by_team_relevance(client):
    collect(client)
    r = client.post("/api/ask", json={"question": "What should we worry about?"}).json()
    assert len(r["sources"]) == 5 and "Kubernetes" in r["sources"][0]["title"]


def test_ask_unrelated_question_gives_no_answer(client):
    collect(client)
    r = client.post("/api/ask", json={"question": "Tell me about Oracle databases"}).json()
    assert r["mode"] == "no_match" and r["sources"] == []
    assert r["answer"] == "No relevant updates were found in the collected data for this question."


def test_ask_uses_saved_team_context(client):
    collect(client)
    client.post("/api/memory", json={"title": "Container platform", "content": "Kubernetes clusters run production",
                                     "services": ["Kubernetes"]})
    r = client.post("/api/ask", json={"question": "Which updates affect our Kubernetes work?"}).json()
    assert any("Container platform" in x for x in r["team_context"])


def _fake_openai_text(text):
    class Completions:
        def create(self, **kwargs):
            _fake_openai_text.last = kwargs
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=text))])

    class Client:
        def __init__(self, **kwargs):
            self.chat = types.SimpleNamespace(completions=Completions())

    module = types.ModuleType("openai")
    module.OpenAI = Client
    return module


def test_ask_with_mocked_llm_checks_citations(client, monkeypatch):
    collect(client)
    settings.OPENAI_API_KEY, settings.DEMO_MODE = "sk-test", False
    monkeypatch.setitem(sys.modules, "openai", _fake_openai_text("The Kubernetes notice may matter [1]. Verify in official docs."))
    ok = client.post("/api/ask", json={"question": "Which updates affect our Kubernetes work?"}).json()
    assert ok["mode"] == "llm" and "llm_warning" not in ok
    sent = _fake_openai_text.last["messages"][1]["content"]
    assert "Kubernetes platform version notice" in sent and "Oracle" not in sent   # only matching updates are sent
    monkeypatch.setitem(sys.modules, "openai", _fake_openai_text("It is definitely affected [9]."))
    bad = client.post("/api/ask", json={"question": "Which updates affect our Kubernetes work?"}).json()
    assert "not provided" in bad["llm_warning"]
    monkeypatch.setitem(sys.modules, "openai", _fake_openai_text("It is definitely affected."))
    nocite = client.post("/api/ask", json={"question": "Which updates affect our Kubernetes work?"}).json()
    assert "no source citations" in nocite["llm_warning"]


def test_ask_llm_failure_falls_back(client, monkeypatch):
    collect(client)
    settings.OPENAI_API_KEY, settings.DEMO_MODE = "sk-test", False
    monkeypatch.setitem(sys.modules, "openai", _fake_openai_text(""))
    r = client.post("/api/ask", json={"question": "Which updates affect our Kubernetes work?"}).json()
    assert r["mode"] == "local_fallback" and r["llm_error"]
