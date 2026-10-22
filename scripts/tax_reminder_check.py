#!/usr/bin/env python3
"""
tax_reminder_check.py - checks data/uk_tax_deadlines.yaml for any deadline
that falls exactly LEAD_TIMES days from today, and builds the reminder
email content for it.

Unlike weekly_digest.py (which diffs git history), this is a point-in-time
date check against a fixed, recurring calendar -- no git history needed.

Uses Europe/London for "today", not UTC: the whole calendar is UK-specific,
and checking in UTC would occasionally be a day off during BST.

Usage:
  python3 scripts/tax_reminder_check.py

Prints {"subject": ..., "text": ..., "count": N} as JSON on stdout. count is
the number of deadlines due today; the caller (the daily GitHub Actions
workflow) skips sending when count is 0.
"""
import datetime as dt
import json
import pathlib

import yaml
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEADLINES_FILE = ROOT / "data" / "uk_tax_deadlines.yaml"

# A heads-up and a last-call, not a barrage -- easy to tune later.
LEAD_TIMES = [14, 1]

LANDING_PAGE = "https://whichcryptoexchange.com/tax-reminders/"


def next_occurrence(today, month, day):
    """This year's month/day, or next year's if already passed."""
    candidate = dt.date(today.year, month, day)
    if candidate < today:
        candidate = dt.date(today.year + 1, month, day)
    return candidate


def main():
    today = dt.datetime.now(ZoneInfo("Europe/London")).date()
    deadlines = yaml.safe_load(DEADLINES_FILE.read_text()) or []

    due = []
    for d in deadlines:
        occurrence = next_occurrence(today, d["month"], d["day"])
        days_until = (occurrence - today).days
        if days_until in LEAD_TIMES:
            due.append((d, occurrence, days_until))

    count = len(due)
    if count == 0:
        text = "No reminders due today."
        subject = "UK crypto tax reminders: nothing due today"
    else:
        lines = [
            f"{count} UK tax deadline{'s' if count != 1 else ''} coming up, relevant to crypto holders:",
        ]
        for d, occurrence, days_until in due:
            lines.append("")
            lines.append(f"-- {d['label']} ({occurrence.isoformat()}, {days_until} day{'s' if days_until != 1 else ''} away) --")
            if d.get("detail"):
                lines.append(d["detail"])
            lines.append(f"Source: {d['source']}")
        lines += [
            "",
            "This is not personalised tax advice -- just a dated, sourced reminder of what's coming up.",
            f"Full calendar: {LANDING_PAGE}",
        ]
        text = "\n".join(lines)
        subject = f"UK crypto tax reminder: {due[0][0]['label']} in {due[0][2]} day{'s' if due[0][2] != 1 else ''}"
        if count > 1:
            subject = f"UK crypto tax reminders: {count} deadlines coming up"

    print(json.dumps({"subject": subject, "text": text, "count": count}))


if __name__ == "__main__":
    main()
