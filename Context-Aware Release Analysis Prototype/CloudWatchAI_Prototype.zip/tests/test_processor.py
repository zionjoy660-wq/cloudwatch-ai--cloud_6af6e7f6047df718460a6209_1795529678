from app.services.processor import normalize_records, classify, extract_services


def test_pricing_classification():
    assert classify("price and billing change") == "pricing"


def test_service_detection():
    assert "EC2" in extract_services("Amazon EC2 update")


def test_record_id_created():
    df = normalize_records([{"provider": "AWS", "title": "Test", "content": "EC2 update", "url": "https://example.com"}])
    assert len(df) == 1 and df.iloc[0]["id"] and "EC2" in df.iloc[0]["services"]


def test_service_names_must_be_whole_words():
    assert extract_services("Several weeks of tasks and words") == []


def test_deprecation_wins_over_pricing():
    assert classify("Retirement of a feature, pricing page updated") == "deprecation"


def test_empty_records_removed_and_duplicates_removed():
    rows = [{"provider": "AWS", "title": "A", "content": "x", "url": "u"},
            {"provider": "aws", "title": "A", "content": "x", "url": "u"},
            {"provider": "AWS", "title": "", "content": ""}]
    df = normalize_records(rows)
    assert len(df) == 1
    assert df.attrs["stats"] == {"raw_count": 3, "empty_removed": 1, "duplicates_removed": 1, "processed_count": 1}


def test_missing_date_is_not_invented():
    df = normalize_records([{"provider": "AWS", "title": "A", "content": "x"}])
    assert df.iloc[0]["published_at"] == ""


def test_markdown_noise_removed():
    df = normalize_records([{"provider": "AWS", "title": "A", "content": "![img](http://x/y.png) see [docs](http://z) now"}])
    assert df.iloc[0]["content"] == "see docs now"
