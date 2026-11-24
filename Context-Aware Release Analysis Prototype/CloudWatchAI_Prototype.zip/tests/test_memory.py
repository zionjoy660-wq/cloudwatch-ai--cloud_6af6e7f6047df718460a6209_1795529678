from app.services.memory import memory


def test_memory_saves_and_reads_back():
    memory.store_context("EKS", "Production runs on EKS with Terraform", ["EKS"])
    assert memory.count() == 1
    assert memory.all()[0]["services"] == ["EKS"]


def test_identical_context_not_saved_twice():
    first = memory.store_context("T", "same text", [])
    second = memory.store_context("T", "same text", [])
    assert first[1] is True and second[1] is False and memory.count() == 1


def test_reanalysis_replaces_old_record():
    a = {"title": "X", "provider": "AWS", "priority": "High", "relevance_score": 80, "change_summary": "s",
         "organizational_impact": "i", "affected_services": ["EC2"], "source_url": "u", "is_demo": False}
    memory.remember_analysis(a)
    memory.remember_analysis({**a, "priority": "Low"})
    assert memory.count() == 1 and "Priority Low" in memory.all()[0]["content"]


def test_search_returns_related_only():
    memory.store_context("Kubernetes", "Container workloads run on Kubernetes clusters", ["Kubernetes"])
    memory.store_context("Billing", "Finance reviews invoices monthly", ["Billing"])
    found = memory.search("Kubernetes version support upgrade", services=["Kubernetes"])
    assert [m["title"] for m in found] == ["Kubernetes"]


def test_unrelated_query_returns_nothing():
    memory.store_context("Kubernetes", "Container workloads run on Kubernetes clusters", ["Kubernetes"])
    assert memory.search("pricing announcement for object storage") == []


def test_own_earlier_analysis_is_not_returned():
    memory.remember_analysis({"title": "Same update", "provider": "AWS", "priority": "Low", "relevance_score": 10,
                              "change_summary": "ec2 instance family", "organizational_impact": "", "affected_services": ["EC2"]})
    assert memory.search("ec2 instance family", services=["EC2"], exclude_title="Same update") == []


def test_sample_analyses_hidden_from_real_updates():
    memory.remember_analysis({"title": "Sample", "provider": "AWS", "priority": "Low", "relevance_score": 10,
                              "change_summary": "ec2 instance", "organizational_impact": "", "affected_services": ["EC2"],
                              "is_demo": True})
    assert memory.search("ec2 instance", services=["EC2"], exclude_demo=True) == []
    assert len(memory.search("ec2 instance", services=["EC2"], exclude_demo=False)) == 1
