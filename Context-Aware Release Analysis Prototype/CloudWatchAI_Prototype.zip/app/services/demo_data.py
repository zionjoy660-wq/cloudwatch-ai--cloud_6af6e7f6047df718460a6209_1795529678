"""Illustrative sample records used in demo mode.

IMPORTANT: these are made-up examples written for demonstration. They are NOT
real cloud-provider announcements. The URLs point to each provider's general
updates page only, and the records carry no publish date on purpose.
The list is fixed, so demo results are the same every time.
"""

DEMO_SOURCE = "Illustrative sample (not a real announcement)"


def _sample(provider, title, summary, content, url, category, services):
    return {
        "provider": provider,
        "title": title,
        "summary": summary,
        "content": content,
        "url": url,
        "published_at": None,          # no date: we must not invent one
        "category": category,
        "services": services,
        "is_demo": True,
        "source": DEMO_SOURCE,
        "collection_type": "demo_sample",
    }


def sample_updates():
    return [
        _sample(
            "AWS",
            "Illustrative: Amazon EC2 instance family update",
            "Sample announcement about an EC2 instance family. Review compatibility, pricing and availability.",
            "Illustrative demo record. A new EC2 instance family is announced. Engineers should review workload "
            "compatibility, pricing, regional availability, and deployment configuration before adoption.",
            "https://aws.amazon.com/new/", "service_update", ["EC2"]),
        _sample(
            "Azure",
            "Illustrative: Azure database maintenance notice",
            "Sample managed database maintenance and configuration notice.",
            "Illustrative demo record. A managed database maintenance change may affect configuration, maintenance "
            "windows, and runbooks. Review official documentation before making changes.",
            "https://azure.microsoft.com/en-us/updates/", "maintenance", ["Azure Database"]),
        _sample(
            "Google Cloud",
            "Illustrative: Kubernetes platform version notice",
            "Sample platform update requiring supported-version review.",
            "Illustrative demo record. A Kubernetes platform notice highlights version support and upgrade planning. "
            "Review workloads, deprecated APIs, compatibility, and tests.",
            "https://cloud.google.com/release-notes", "deprecation", ["GKE", "Kubernetes"]),
        _sample(
            "AWS",
            "Illustrative: Cloud pricing information updated",
            "Sample pricing announcement requiring cost review.",
            "Illustrative demo record. Pricing information for a service is updated. Cost owners should compare "
            "usage and verify pricing details using official documentation.",
            "https://aws.amazon.com/new/", "pricing", ["AWS Billing"]),
        _sample(
            "Azure",
            "Illustrative: Service retirement warning",
            "Sample retirement notice with migration planning requirement.",
            "Illustrative demo record. A feature is scheduled for retirement. Identify dependencies, evaluate "
            "replacement options, and plan migration using official guidance.",
            "https://azure.microsoft.com/en-us/updates/", "deprecation", ["Azure"]),
    ]
