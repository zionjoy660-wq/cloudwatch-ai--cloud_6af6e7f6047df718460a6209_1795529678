"""Splits the markdown of a provider page into individual release-note entries.

Provider pages are long lists of announcements. This module cuts the page into one
record per entry so that each announcement can be classified and analysed separately.

How it works (simple rules, no AI):
  * A markdown heading (#, ##, ###, ####) starts a new entry.
  * A heading or line that is only a date (e.g. "October 28, 2026") sets the date for the
    entries that follow it; it is not an entry itself.
  * Very short entries and page boilerplate (cookie notices, navigation) are dropped.
  * If fewer than 2 entries are found the caller keeps the whole page instead.
These rules are heuristics: real pages differ, so entry boundaries can be imperfect.
"""
import re
from datetime import datetime

MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
_MONTH = rf"(?:{MONTHS})[a-z]*\.?"
DATE_PATTERNS = [
    re.compile(rf"\b({_MONTH})\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.IGNORECASE),   # October 28, 2026
    re.compile(rf"\b(\d{{1,2}})\s+({_MONTH}),?\s+(\d{{4}})\b", re.IGNORECASE),   # 28 October 2026
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),                                    # 2026-10-28
]
# Heading that is only a date, optionally with "Posted on:" in front.
DATE_ONLY = re.compile(rf"^(?:posted on:?\s*|updated:?\s*)?(?:{_MONTH}\s+\d{{1,2}},?\s+\d{{4}}|\d{{1,2}}\s+{_MONTH},?\s+\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})$",
                       re.IGNORECASE)

# Headings that only describe the TYPE of a note; the real topic is the product above or the first sentence.
GENERIC_HEADINGS = {"feature", "announcement", "changed", "change", "fixed", "fix", "issue", "known issue",
                    "breaking", "breaking change", "deprecated", "libraries", "security", "update",
                    "resolved", "non-breaking", "preview", "general availability"}
BOILERPLATE = re.compile(r"cookie|privacy|terms of (use|service)|sign in|log in|skip to|subscribe|feed reader|"
                         r"all rights reserved|follow us|newsletter|back to top|table of contents", re.IGNORECASE)

MIN_BODY_CHARS = 60
MAX_TITLE_CHARS = 140


def parse_date(text):
    """Return 'YYYY-MM-DD' for the first date found in the text, or None."""
    for index, pattern in enumerate(DATE_PATTERNS):
        match = pattern.search(text or "")
        if not match:
            continue
        a, b, c = match.groups()
        try:
            if index == 0:
                return datetime.strptime(f"{a[:3]} {b} {c}", "%b %d %Y").strftime("%Y-%m-%d")
            if index == 1:
                return datetime.strptime(f"{b[:3]} {a} {c}", "%b %d %Y").strftime("%Y-%m-%d")
            return datetime(int(a), int(b), int(c)).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _strip_markdown(text):
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_`]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _first_link(text):
    match = re.search(r"\[[^\]]*\]\((https?://[^)\s]+)\)", text or "")
    return match.group(1) if match else ""


def _first_sentence(text):
    text = _strip_markdown(text)
    match = re.match(r"(.{20,%d}?[.!?])(\s|$)" % MAX_TITLE_CHARS, text)
    return (match.group(1) if match else text[:MAX_TITLE_CHARS]).strip()


def split_release_notes(markdown, page_url, provider, source_name, official_check=None):
    """Return a list of record dicts, one per release-note entry found in the markdown."""
    entries = []
    state = {"current": None, "product": "", "page_date": None}

    def flush():
        """Finish the entry being built and keep it if it contains real text."""
        entry, state["current"] = state["current"], None
        if entry is None:
            return
        body = _strip_markdown("\n".join(entry["body"]))
        heading = _strip_markdown(entry["heading"])
        if len(body) < MIN_BODY_CHARS:
            # A heading with no real text is probably a product name for the entries below it.
            if heading and heading.lower() not in GENERIC_HEADINGS and len(heading) < 80:
                state["product"] = heading
            return
        if BOILERPLATE.search(body[:200]) and len(body) < 300:
            return
        if heading.lower() in GENERIC_HEADINGS or not heading:
            title = _first_sentence(body)
            if state["product"]:
                title = f"{state['product']}: {title}"[:MAX_TITLE_CHARS]
        else:
            title = heading[:MAX_TITLE_CHARS]
            state["product"] = ""
        link = _first_link(entry["heading"]) or _first_link("\n".join(entry["body"]))
        date = parse_date(heading) or entry["date"] or parse_date(body[:300]) or entry["page_date"]
        entries.append({"title": title, "body": body, "link": link, "date": date})

    for line in str(markdown or "").splitlines():
        stripped = line.strip()
        heading = re.match(r"^#{1,4}\s+(.*)$", stripped)
        plain = _strip_markdown(stripped)
        is_date_heading = bool(heading) and bool(DATE_ONLY.match(_strip_markdown(heading.group(1))))
        is_date_line = not heading and 0 < len(plain) < 40 and bool(DATE_ONLY.match(plain))

        if is_date_heading or is_date_line:
            found = parse_date(heading.group(1) if heading else plain)
            current = state["current"]
            if is_date_line and current is not None and not "".join(current["body"]).strip():
                current["date"] = found          # "Posted on: ..." directly under an entry heading
            else:
                flush()
                state["page_date"] = found       # a date heading that applies to the entries below it
        elif heading:
            flush()
            state["current"] = {"heading": heading.group(1), "body": [], "date": None, "page_date": state["page_date"]}
        elif state["current"] is not None:
            state["current"]["body"].append(line)
    flush()

    records = []
    for entry in entries:
        link_ok = entry["link"] and (official_check is None or official_check(entry["link"]))
        records.append({
            "provider": provider,
            "title": entry["title"],
            "summary": entry["body"][:400],
            "content": entry["body"],
            "url": entry["link"] if link_ok else page_url,
            "published_at": entry["date"],
            "category": None,           # decided later by the Pandas rules
            "services": [],
            "is_demo": False,
            "source": source_name,
            "collection_type": "release_note",
        })
    return records
