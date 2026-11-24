"""Pandas preprocessing: turns raw collected records into a clean, consistent table.

Raw records (data/raw/*.json) are saved exactly as collected.
Processed records (data/processed/cloud_updates.csv) are the cleaned versions
that the rest of the application uses.
"""
import hashlib
import re

import pandas as pd

from app.core.config import settings

COLUMNS = [
    "id", "provider", "title", "summary", "content", "url", "published_at",
    "category", "services", "is_demo", "source", "collected_at", "collection_type",
]

# Order matters: the first rule that matches wins, so the changes that need the
# most attention (deprecations, security) are checked before the general ones.
RULES = {
    "deprecation": ["deprecated", "deprecation", "retire", "retired", "retirement", "end of support", "end-of-life", "sunset"],
    "security": ["security", "vulnerability", "encryption", "patch", "cve"],
    "pricing": ["price", "prices", "pricing", "cost", "costs", "billing", "discount"],
    "maintenance": ["maintenance", "outage", "scheduled"],
    "availability": ["available", "availability", "region", "regions", "general availability", "preview"],
    "service_update": ["launch", "launches", "new", "update", "updated", "feature", "release", "released"],
}

# Services we can recognise by name in the text.
SERVICES = ["EC2", "S3", "Lambda", "RDS", "EKS", "GKE", "AKS", "Azure", "Kubernetes",
            "Terraform", "Cloud Run", "BigQuery", "Compute Engine", "IAM", "CloudWatch"]

PROVIDER_NAMES = {"aws": "AWS", "amazon": "AWS", "azure": "Azure", "microsoft azure": "Azure",
                  "google cloud": "Google Cloud", "gcp": "Google Cloud", "google": "Google Cloud"}

MAX_CONTENT_CHARS = 20000  # keeps very long page captures manageable


def _word_pattern(word):
    """Regex that matches `word` only as a whole word (so 'weeks' does not match 'EKS')."""
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(word) + r"(?![A-Za-z0-9])", re.IGNORECASE)


_RULE_PATTERNS = {cat: [_word_pattern(w) for w in words] for cat, words in RULES.items()}
_SERVICE_PATTERNS = [(s, _word_pattern(s)) for s in SERVICES]


def classify(text):
    """Keyword-based category. Returns 'other' when nothing matches."""
    text = str(text)
    for category, patterns in _RULE_PATTERNS.items():
        if any(p.search(text) for p in patterns):
            return category
    return "other"


def extract_services(text):
    """Names of known cloud services that appear in the text."""
    text = str(text)
    return [name for name, pattern in _SERVICE_PATTERNS if pattern.search(text)]


def clean_text(text):
    """Remove markdown noise (images, link URLs) and collapse whitespace."""
    text = str(text or "")
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)          # ![alt](image-url)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)       # [text](url) -> text
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_provider(name):
    name = str(name or "").strip()
    return PROVIDER_NAMES.get(name.lower(), name or "Unknown")


def _empty_frame():
    df = pd.DataFrame(columns=COLUMNS)
    df.attrs["stats"] = {"raw_count": 0, "empty_removed": 0, "duplicates_removed": 0, "processed_count": 0}
    return df


def normalize_records(records):
    """Clean, classify, de-duplicate and export the collected records.

    Returns a DataFrame. Pipeline statistics are available in df.attrs["stats"].
    """
    if not records:
        return _empty_frame()

    df = pd.DataFrame(records)
    raw_count = len(df)
    for col in COLUMNS:
        if col not in df:
            df[col] = None

    # 1. Basic cleaning of text fields.
    df["provider"] = df["provider"].apply(normalize_provider)
    df["title"] = df["title"].apply(clean_text)
    df["content"] = df["content"].apply(clean_text).str[:MAX_CONTENT_CHARS]
    df["url"] = df["url"].fillna("").astype(str).str.strip()
    df["summary"] = df["summary"].apply(clean_text)
    df["summary"] = df.apply(lambda r: r["summary"] or r["content"][:300], axis=1)
    df["source"] = df["source"].fillna("").astype(str)
    df["collection_type"] = df["collection_type"].fillna("").astype(str)
    df["collected_at"] = df["collected_at"].fillna("").astype(str)
    df["published_at"] = df["published_at"].where(df["published_at"].notna(), None)

    # 2. Filter out records that carry no information at all.
    has_info = (df["title"] != "") | (df["content"] != "")
    empty_removed = int((~has_info).sum())
    df = df[has_info].copy()
    df["title"] = df["title"].replace("", "Untitled update")

    # 3. Category and services: keep the collector's value, otherwise detect from text.
    def pick_category(row):
        given = row["category"]
        if isinstance(given, str) and given and given != "other":
            return given
        return classify(row["title"] + " " + row["content"])

    def pick_services(row):
        if isinstance(row["services"], list) and row["services"]:
            return row["services"]
        return extract_services(row["title"] + " " + row["content"])

    df["category"] = df.apply(pick_category, axis=1)
    df["services"] = df.apply(pick_services, axis=1)
    df["is_demo"] = df["is_demo"].fillna(False).astype(bool)

    # 4. Stable id, then remove duplicates.
    df["id"] = df.apply(
        lambda r: hashlib.sha1((r["provider"] + r["title"] + r["url"] + r["content"][:200]).encode()).hexdigest()[:12], axis=1)
    before = len(df)
    df = df.drop_duplicates(subset="id").reset_index(drop=True)
    duplicates_removed = before - len(df)

    # 5. Dates: keep a real publish date if one was provided, never invent one.
    parsed = pd.to_datetime(df["published_at"], errors="coerce", utc=True)
    df["published_at"] = parsed.dt.strftime("%Y-%m-%dT%H:%M:%SZ").fillna("")

    df = df[COLUMNS]
    df.attrs["stats"] = {"raw_count": raw_count, "empty_removed": empty_removed,
                         "duplicates_removed": duplicates_removed, "processed_count": len(df)}

    # 6. Export the processed table (lists are written as "a; b").
    settings.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    export = df.copy()
    export["services"] = export["services"].apply(lambda s: "; ".join(s))
    export.to_csv(settings.PROCESSED_DIR / "cloud_updates.csv", index=False)
    return df
