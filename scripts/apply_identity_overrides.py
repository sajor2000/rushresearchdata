#!/usr/bin/env python3
"""Apply manual faculty identity override caveats to the faculty summary CSV."""

import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SUMMARY_CSV = REPO_ROOT / "data" / "rush_researcher_h_index.csv"
OVERRIDES_CSV = REPO_ROOT / "data" / "faculty_identity_overrides.csv"

REVIEW_STATUSES = {
    "split_profile_review",
    "wrong_person_review",
    "do_not_merge",
}


def read_rows(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_rows(path, rows, fieldnames):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    summary_rows = read_rows(SUMMARY_CSV)
    override_rows = read_rows(OVERRIDES_CSV) if OVERRIDES_CSV.exists() else []

    overrides_by_faculty = {
        (row.get("faculty_name", ""), row.get("rush_dept", "")): row
        for row in override_rows
        if row.get("status") in REVIEW_STATUSES
    }

    applied = 0
    for row in summary_rows:
        override = overrides_by_faculty.get((row.get("name", ""), row.get("rush_dept", "")))
        if not override:
            continue
        review_match_type = override.get("review_match_type", "").strip()
        if not review_match_type:
            continue
        row["match_type"] = review_match_type
        applied += 1

    write_rows(SUMMARY_CSV, summary_rows, summary_rows[0].keys())
    print(f"Applied {applied} faculty identity override caveat(s).")


if __name__ == "__main__":
    main()
