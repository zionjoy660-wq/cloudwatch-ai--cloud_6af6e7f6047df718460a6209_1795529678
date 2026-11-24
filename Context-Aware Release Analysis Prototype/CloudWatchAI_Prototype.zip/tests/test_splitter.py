from app.services.splitter import split_release_notes, parse_date

GOOGLE_STYLE = """# Google Cloud release notes
Skip to main content
## October 28, 2026
### AlloyDB for PostgreSQL
#### Feature
The following AlloyDB AI and vector search features are generally available (GA): the alloydb_scann extension supports four-level tree indexes for very large tables.
#### Announcement
AlloyDB now supports horizontal autoscaling for read pool instances. This feature is available in Preview. See [docs](https://cloud.google.com/alloydb/docs/x).
## October 20, 2026
### Compute Engine
#### Issue
C4 machine type VM instances running on sole tenant nodes might encounter unexpected VM terminations due to host errors.
### Cloud Run
Short.
"""

AWS_STYLE = """### [Amazon EC2 launches new M9 instances](https://aws.amazon.com/about-aws/whats-new/2026/11/ec2-m9/)
Posted on: Nov 20, 2026
Amazon EC2 M9 instances are now generally available in additional regions with improved price performance for workloads.
### [AWS Lambda ends support for a runtime](https://evil.example.com/x)
Posted on: Nov 18, 2026
AWS Lambda will end support for an older runtime; customers should migrate functions before the deprecation date for patches.
### Cookie preferences
We use cookies and similar tools to improve your experience and show relevant content to you on this site always.
"""


def official(url):
    return "amazon.com" in url or "google.com" in url


def test_parse_date_formats():
    assert parse_date("October 28, 2026") == "2026-10-28"
    assert parse_date("28 Oct 2026") == "2026-10-28"
    assert parse_date("Posted on: Nov 20, 2026") == "2026-11-20"
    assert parse_date("590.0.0 (2026-10-20)") == "2026-10-20"
    assert parse_date("no date here") is None
    assert parse_date("February 31, 2026") is None          # impossible date is not accepted


def test_google_style_dates_products_and_short_entries():
    rows = split_release_notes(GOOGLE_STYLE, "https://cloud.google.com/release-notes", "Google Cloud", "GC", official)
    assert len(rows) == 3                                     # the one-word "Short." entry is dropped
    assert rows[0]["published_at"] == "2026-10-28" and rows[2]["published_at"] == "2026-10-20"
    assert rows[0]["title"].startswith("AlloyDB for PostgreSQL:")
    assert rows[1]["url"] == "https://cloud.google.com/alloydb/docs/x"
    assert all(r["collection_type"] == "release_note" and r["is_demo"] is False for r in rows)


def test_aws_style_date_under_heading_and_link_handling():
    rows = split_release_notes(AWS_STYLE, "https://aws.amazon.com/new/", "AWS", "AWS", official)
    assert [r["title"] for r in rows] == ["Amazon EC2 launches new M9 instances", "AWS Lambda ends support for a runtime"]
    assert [r["published_at"] for r in rows] == ["2026-11-20", "2026-11-18"]
    assert rows[0]["url"].startswith("https://aws.amazon.com/about-aws/")
    assert rows[1]["url"] == "https://aws.amazon.com/new/"     # non-official link replaced by the page URL


def test_boilerplate_removed():
    rows = split_release_notes(AWS_STYLE, "u", "AWS", "AWS", official)
    assert not any("cookie" in r["title"].lower() for r in rows)


def test_page_without_headings_gives_no_entries():
    assert split_release_notes("plain text without any headings " * 10, "u", "AWS", "AWS") == []
    assert split_release_notes("", "u", "AWS", "AWS") == []
