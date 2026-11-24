"""Evaluation script: compares the app's output with YOUR human labels.

Usage (from the project folder):
    python scripts/evaluate.py

It collects updates with the current .env settings (demo mode by default), runs the same
analysis as the app, and reports:
  * category agreement   (Pandas keyword rules vs your expected_category)
  * priority agreement   (analysis priority vs your expected_priority)
  * automatic output checks and time per analysis
Only items where you filled in a label are scored. Nothing is invented: with no labels
the script says so instead of printing accuracy.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.analyzer import analyze_update, validate_analysis  # noqa: E402
from app.services.collector import collect_updates                    # noqa: E402
from app.services.processor import normalize_records                  # noqa: E402

LABEL_FILE = ROOT / "data" / "evaluation" / "labelled_set.json"


def main():
    labelled = json.loads(LABEL_FILE.read_text(encoding="utf-8"))
    profile = labelled["team_profile"]

    result = collect_updates()
    updates = normalize_records(result["records"]).to_dict(orient="records")
    print(f"Collection mode: {result['mode']}  |  records: {len(updates)}")
    for warning in result["warnings"]:
        print("  warning:", warning)
    by_title = {u["title"]: u for u in updates}

    category_total = category_hits = priority_total = priority_hits = checks_passed = 0
    timings = []
    print("\n{:<52} {:<13} {:<13} {}".format("Title", "category", "priority", "output checks"))
    for item in labelled["items"]:
        update = by_title.get(item["title"])
        if update is None:
            print(f"{item['title'][:50]:<52} (not in the current collection - skipped)")
            continue
        start = time.perf_counter()
        analysis = analyze_update(update, profile)       # same function the API uses (does not write memory)
        timings.append((time.perf_counter() - start) * 1000)
        problems = validate_analysis(analysis)
        checks_passed += not problems

        cat_mark = prio_mark = "-"
        if item.get("expected_category"):
            category_total += 1
            ok = update["category"] == item["expected_category"]
            category_hits += ok
            cat_mark = "OK" if ok else f"{update['category']}!={item['expected_category']}"
        if item.get("expected_priority"):
            priority_total += 1
            ok = analysis["priority"] == item["expected_priority"]
            priority_hits += ok
            prio_mark = "OK" if ok else f"{analysis['priority']}!={item['expected_priority']}"
        print(f"{item['title'][:50]:<52} {cat_mark:<13} {prio_mark:<13} {'pass' if not problems else '; '.join(problems)}")

    print("\n--- Summary ---")
    if category_total:
        print(f"Category agreement: {category_hits}/{category_total}")
    else:
        print("Category agreement: no expected_category labels filled in yet")
    if priority_total:
        print(f"Priority agreement: {priority_hits}/{priority_total}")
    else:
        print("Priority agreement: no expected_priority labels filled in yet")
    if timings:
        print(f"Output checks passed: {checks_passed}/{len(timings)}")
        print(f"Analysis time per update: avg {sum(timings) / len(timings):.1f} ms, max {max(timings):.1f} ms "
              f"(mode: {'LLM' if analysis['analysis_mode'] == 'llm' else 'local fallback'})")
    print("Small label sets only show tendencies; they do not prove accuracy.")


if __name__ == "__main__":
    main()
