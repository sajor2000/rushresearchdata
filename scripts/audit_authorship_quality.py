#!/usr/bin/env python3
"""Audit authorship-enrichment data quality and attribution confidence."""

import csv
import json
import re
import subprocess
import io
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SUMMARY_CSV = REPO_ROOT / "data" / "rush_researcher_h_index.csv"
WORK_CSV = REPO_ROOT / "data" / "faculty_authorship_works.csv"
REPORT_PATH = REPO_ROOT / "data" / "authorship_quality_audit.json"
FLAGS_PATH = REPO_ROOT / "data" / "authorship_quality_flags.csv"

SUMMARY_COUNT_FIELDS = {
    "recent_author_works_5yr": ("first", "middle", "last", "single", "ambiguous"),
    "senior_author_5yr": ("last",),
    "first_author_5yr": ("first",),
    "contributing_author_5yr": ("middle",),
    "ambiguous_author_5yr": ("single", "ambiguous"),
}

LOWER_CONFIDENCE_MATCH_MARKERS = (
    "api_search",
    "wrong_person",
    "collision",
)

BASELINE_FIELDS = [
    "name",
    "h_index",
    "i10_index",
    "works_count",
    "cited_by_count",
    "rush_works_5yr",
    "two_year_mean_citedness",
    "rush_dept",
    "college",
    "match_type",
    "orcid",
    "openalex_id",
]


def norm_name(value):
    return re.sub(r"[^a-z ]+", "", (value or "").lower()).strip()


def int_field(row, key):
    try:
        return int(float(row.get(key) or 0))
    except ValueError:
        return 0


def read_csv(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def compare_to_git_baseline(current_rows):
    try:
        old_text = subprocess.check_output(
            ["git", "show", "HEAD:data/rush_researcher_h_index.csv"],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
        ).decode("utf-8-sig")
    except Exception:
        return {"available": False}

    old_rows = list(csv.DictReader(io.StringIO(old_text)))
    changed = []
    if len(old_rows) != len(current_rows):
        changed.append({"row": "", "field": "row_count", "old": len(old_rows), "new": len(current_rows)})
    for row_idx, (old_row, current_row) in enumerate(zip(old_rows, current_rows), start=2):
        for field in BASELINE_FIELDS:
            if (old_row.get(field, "") or "") != (current_row.get(field, "") or ""):
                changed.append({
                    "row": row_idx,
                    "field": field,
                    "old": old_row.get(field, ""),
                    "new": current_row.get(field, ""),
                })
    return {
        "available": True,
        "baseline_fields_checked": BASELINE_FIELDS,
        "pre_existing_field_changes": len(changed),
        "example_changes": changed[:20],
    }


def add_flag(flags, severity, check, detail, row=None):
    flags.append({
        "severity": severity,
        "check": check,
        "detail": detail,
        "faculty_name": (row or {}).get("name") or (row or {}).get("faculty_name", ""),
        "rush_dept": (row or {}).get("rush_dept", ""),
        "openalex_id": (row or {}).get("openalex_id") or (row or {}).get("openalex_author_id", ""),
        "work_id": (row or {}).get("work_id", ""),
    })


def main():
    summary = read_csv(SUMMARY_CSV)
    works = read_csv(WORK_CSV)
    flags = []

    by_name = defaultdict(list)
    by_name_dept = defaultdict(list)
    by_openalex = defaultdict(list)
    for idx, row in enumerate(summary, start=2):
        by_name[norm_name(row["name"])].append((idx, row))
        by_name_dept[(norm_name(row["name"]), row["rush_dept"])].append((idx, row))
        if row.get("openalex_id", "").strip():
            by_openalex[row["openalex_id"].strip()].append((idx, row))

    for key, values in by_name.items():
        if len(values) > 1:
            add_flag(flags, "blocker", "duplicate_faculty_name", f"{key}: {len(values)} rows")
    for key, values in by_name_dept.items():
        if len(values) > 1:
            add_flag(flags, "blocker", "duplicate_faculty_name_department", f"{key}: {len(values)} rows")
    for openalex_id, values in by_openalex.items():
        if len(values) > 1:
            add_flag(flags, "blocker", "duplicate_openalex_author_id", f"{openalex_id}: {len(values)} faculty rows")

    faculty_author_work_keys = [(w["faculty_name"], w["openalex_author_id"], w["work_id"]) for w in works]
    duplicate_work_rows = len(faculty_author_work_keys) - len(set(faculty_author_work_keys))
    if duplicate_work_rows:
        add_flag(flags, "blocker", "duplicate_faculty_author_work", f"{duplicate_work_rows} duplicate rows")

    for row in summary:
        if not row.get("openalex_id", "").strip():
            enriched = sum(int_field(row, field) for field in SUMMARY_COUNT_FIELDS)
            if enriched:
                add_flag(flags, "blocker", "unmatched_faculty_has_authorship_metrics", "missing OpenAlex ID but nonzero authorship fields", row)

    work_position_by_faculty = defaultdict(Counter)
    work_rows_by_faculty = defaultdict(list)
    for row in works:
        if not row.get("work_id"):
            add_flag(flags, "blocker", "blank_work_id", "work audit row has blank work_id", row)
        if not row.get("openalex_author_id"):
            add_flag(flags, "blocker", "blank_author_id", "work audit row has blank OpenAlex author ID", row)
        position = row.get("author_position", "")
        if position not in {"first", "middle", "last", "single", "ambiguous"}:
            add_flag(flags, "blocker", "invalid_author_position", f"invalid position: {position}", row)
        work_position_by_faculty[row["faculty_name"]][position] += 1
        work_rows_by_faculty[row["faculty_name"]].append(row)

    for row in summary:
        counts = work_position_by_faculty[row["name"]]
        for field, positions in SUMMARY_COUNT_FIELDS.items():
            expected = sum(counts[position] for position in positions)
            observed = int_field(row, field)
            if observed != expected:
                add_flag(flags, "blocker", "summary_work_audit_mismatch", f"{field}: summary={observed}, audit={expected}", row)

        recent = int_field(row, "recent_author_works_5yr")
        senior = int_field(row, "senior_author_5yr")
        observed_ratio = float(row.get("leadership_ratio_5yr") or 0)
        expected_ratio = round((senior / recent) if recent else 0, 3)
        if abs(observed_ratio - expected_ratio) > 0.001:
            add_flag(flags, "blocker", "leadership_ratio_mismatch", f"summary={observed_ratio}, expected={expected_ratio}", row)

    lower_confidence_faculty = []
    lower_confidence_authorship_rows = 0
    for row in summary:
        match_type = (row.get("match_type") or "").lower()
        recent = int_field(row, "recent_author_works_5yr")
        if recent and any(marker in match_type for marker in LOWER_CONFIDENCE_MATCH_MARKERS):
            lower_confidence_faculty.append(row)
            lower_confidence_authorship_rows += recent
            add_flag(flags, "review", "lower_confidence_author_match_inherits_to_authorship", row.get("match_type", ""), row)

    same_work_counts = Counter(w["work_id"] for w in works)
    multi_faculty_works = sum(1 for count in same_work_counts.values() if count > 1)
    max_faculty_per_work = max(same_work_counts.values()) if same_work_counts else 0

    position_totals = Counter(w["author_position"] for w in works)
    first_last_total = position_totals["first"] + position_totals["last"]
    high_confidence_first_last = first_last_total
    if duplicate_work_rows or any(len(values) > 1 for values in by_openalex.values()):
        high_confidence_first_last = 0

    report = {
        "timestamp": datetime.now().isoformat(),
        "summary_rows": len(summary),
        "work_rows": len(works),
        "blocking_issue_count": sum(1 for f in flags if f["severity"] == "blocker"),
        "review_issue_count": sum(1 for f in flags if f["severity"] == "review"),
        "duplicate_checks": {
            "duplicate_normalized_faculty_names": sum(1 for values in by_name.values() if len(values) > 1),
            "duplicate_normalized_faculty_name_department": sum(1 for values in by_name_dept.values() if len(values) > 1),
            "duplicate_openalex_author_ids": sum(1 for values in by_openalex.values() if len(values) > 1),
            "duplicate_faculty_author_work_rows": duplicate_work_rows,
        },
        "reconciliation": {
            "summary_recent_author_works_5yr": sum(int_field(row, "recent_author_works_5yr") for row in summary),
            "work_audit_rows": len(works),
            "position_total_rows": sum(position_totals.values()),
            "summary_mismatches": sum(1 for f in flags if f["check"] == "summary_work_audit_mismatch"),
            "leadership_ratio_mismatches": sum(1 for f in flags if f["check"] == "leadership_ratio_mismatch"),
        },
        "author_position_confidence": {
            "basis": "OpenAlex authorship rows matched by exact OpenAlex author ID; author_position is taken directly from the work authorship object.",
            "first_author_rows": position_totals["first"],
            "last_author_rows": position_totals["last"],
            "first_or_last_rows": first_last_total,
            "high_confidence_first_or_last_rows": high_confidence_first_last,
            "single_author_or_ambiguous_rows": position_totals["single"] + position_totals["ambiguous"],
        },
        "known_review_caveats": {
            "lower_confidence_faculty_matches_with_recent_authorship_rows": len(lower_confidence_faculty),
            "authorship_rows_inherited_from_lower_confidence_matches": lower_confidence_authorship_rows,
            "multi_faculty_same_work_is_expected_not_duplicate": multi_faculty_works,
            "max_faculty_rows_for_one_work": max_faculty_per_work,
        },
        "source_dataset_preservation": compare_to_git_baseline(summary),
    }

    with REPORT_PATH.open("w") as f:
        json.dump(report, f, indent=2)

    with FLAGS_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["severity", "check", "detail", "faculty_name", "rush_dept", "openalex_id", "work_id"])
        writer.writeheader()
        writer.writerows(flags)

    print(json.dumps(report, indent=2))
    if report["blocking_issue_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
