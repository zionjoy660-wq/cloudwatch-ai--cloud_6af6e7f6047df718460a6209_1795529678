"""Builds the personalized release digest from the collected updates."""
from datetime import datetime, timedelta, timezone

from app.services.analyzer import analyze_update

PRIORITY_ORDER = {"High": 3, "Medium": 2, "Low": 1}


def _within_window(update, days):
    """Updates without a known publish date are always kept."""
    published = update.get("published_at")
    if not published:
        return True
    try:
        when = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
    except ValueError:
        return True
    return when >= datetime.now(timezone.utc) - timedelta(days=days)


def generate_digest(updates, profile, days=30):
    selected = [u for u in updates if _within_window(u, days)]
    analyses = [analyze_update(u, profile) for u in selected]
    analyses.sort(key=lambda a: (PRIORITY_ORDER.get(a["priority"], 0), a["relevance_score"]), reverse=True)
    groups = {k: [a for a in analyses if a["priority"] == k] for k in ["High", "Medium", "Low"]}
    team = profile.get("team_name", "the team")
    demo_count = sum(1 for a in analyses if a["is_demo"])
    summary = (f"Reviewed {len(analyses)} updates for {team}: {len(groups['High'])} high, "
               f"{len(groups['Medium'])} medium, {len(groups['Low'])} low priority. "
               "Priorities are estimates; validate findings against official sources.")
    skipped = len(updates) - len(selected)
    if skipped:
        summary += f" {skipped} older than {days} days were skipped."
    if demo_count:
        summary += f" {demo_count} of these are illustrative sample records, not real announcements."
    return {
        "team_name": team,
        "generated_count": len(analyses),
        "skipped_outside_window": len(updates) - len(selected),
        "high_priority": groups["High"],
        "medium_priority": groups["Medium"],
        "low_priority": groups["Low"],
        "executive_summary": summary,
        "analyses": analyses,
    }
