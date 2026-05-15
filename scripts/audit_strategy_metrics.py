#!/usr/bin/env python3
"""Audit strategy metric outputs for reconciliation and duplicate safety."""

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

SUMMARY_CSV = DATA_DIR / "rush_researcher_h_index.csv"
AUTHORSHIP_WORKS_CSV = DATA_DIR / "faculty_authorship_works.csv"
WORK_METRICS_CSV = DATA_DIR / "work_strategy_metrics.csv"
DEPT_STRATEGY_CSV = DATA_DIR / "department_strategy_metrics.csv"
TOPIC_STRATEGY_CSV = DATA_DIR / "topic_strategy_metrics.csv"
TEAM_SCIENCE_CSV = DATA_DIR / "department_team_science.csv"
TEAM_PAIRS_CSV = DATA_DIR / "department_team_science_pairs.csv"
NIH_AWARDS_CSV = DATA_DIR / "nih_reporter_awards.csv"
NIH_DEPT_CSV = DATA_DIR / "department_nih_funding.csv"
REPORT_PATH = DATA_DIR / "strategy_quality_audit.json"
FLAGS_PATH = DATA_DIR / "strategy_quality_flags.csv"


def read_csv(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def int_field(row, key):
    try:
        return int(float(row.get(key) or 0))
    except ValueError:
        return 0


def float_field(row, key):
    try:
        return float(row.get(key) or 0)
    except ValueError:
        return 0.0


def add_flag(flags, severity, check, detail, row=None):
    flags.append({
        "severity": severity,
        "check": check,
        "detail": detail,
        "faculty_name": (row or {}).get("name") or (row or {}).get("faculty_name", ""),
        "rush_dept": (row or {}).get("rush_dept", ""),
        "work_id": (row or {}).get("work_id", ""),
        "project_num": (row or {}).get("project_num", ""),
    })


def main():
    summary = read_csv(SUMMARY_CSV)
    authorship = read_csv(AUTHORSHIP_WORKS_CSV)
    work_metrics = read_csv(WORK_METRICS_CSV)
    dept_strategy = read_csv(DEPT_STRATEGY_CSV)
    topics = read_csv(TOPIC_STRATEGY_CSV)
    team = read_csv(TEAM_SCIENCE_CSV)
    pairs = read_csv(TEAM_PAIRS_CSV)
    nih_awards = read_csv(NIH_AWARDS_CSV)
    nih_dept = read_csv(NIH_DEPT_CSV)
    flags = []

    unique_authorship_works = {row["work_id"] for row in authorship}
    metric_work_ids = [row["work_id"] for row in work_metrics]
    if len(metric_work_ids) != len(set(metric_work_ids)):
        add_flag(flags, "blocker", "duplicate_work_metric_rows", "work_strategy_metrics.csv contains duplicate work IDs")
    if set(metric_work_ids) != unique_authorship_works:
        add_flag(
            flags,
            "blocker",
            "work_metric_set_mismatch",
            f"metric works={len(set(metric_work_ids))}, authorship unique works={len(unique_authorship_works)}",
        )

    missing_topic = sum(1 for row in work_metrics if not row.get("primary_topic"))
    missing_fwci = sum(1 for row in work_metrics if row.get("fwci", "") == "")
    if missing_topic:
        add_flag(flags, "review", "missing_openalex_topic", f"{missing_topic} work rows lack OpenAlex primary topic")
    if missing_fwci:
        add_flag(flags, "review", "missing_openalex_fwci", f"{missing_fwci} work rows lack OpenAlex FWCI")

    summary_names = [row["name"] for row in summary]
    if len(summary_names) != len(set(summary_names)):
        add_flag(flags, "blocker", "duplicate_faculty_names", "faculty summary contains duplicate names")

    metric_by_work = {row["work_id"]: row for row in work_metrics}
    rows_by_faculty = defaultdict(list)
    for row in authorship:
        rows_by_faculty[row["faculty_name"]].append(row)

    for row in summary:
        seen = {work["work_id"] for work in rows_by_faculty.get(row["name"], [])}
        expected_top10 = sum(1 for work_id in seen if metric_by_work.get(work_id, {}).get("is_top10_impact") == "true")
        observed_top10 = int_field(row, "top10_impact_works_5yr")
        if expected_top10 != observed_top10:
            add_flag(flags, "blocker", "faculty_top10_reconciliation", f"expected={expected_top10}, observed={observed_top10}", row)

    dept_names = {row["rush_dept"] for row in summary}
    for path_name, rows in [
        ("department_strategy_metrics.csv", dept_strategy),
        ("department_team_science.csv", team),
        ("department_nih_funding.csv", nih_dept),
    ]:
        depts = [row["rush_dept"] for row in rows]
        if len(depts) != len(set(depts)):
            add_flag(flags, "blocker", "duplicate_department_rows", f"{path_name} has duplicate department rows")
        unexpected = sorted(set(depts) - dept_names)
        if unexpected:
            add_flag(flags, "review", "unexpected_department_labels", f"{path_name}: {unexpected[:10]}")

    pair_keys = [(row["department_a"], row["department_b"]) for row in pairs]
    if len(pair_keys) != len(set(pair_keys)):
        add_flag(flags, "blocker", "duplicate_team_pair_rows", "department_team_science_pairs.csv contains duplicate pairs")

    nih_project_pi_keys = [
        (row.get("appl_id", ""), row.get("subproject_id", ""), row["pi_full_name"], row["fiscal_year"], row["project_num"], row["faculty_name"])
        for row in nih_awards
    ]
    if len(nih_project_pi_keys) != len(set(nih_project_pi_keys)):
        add_flag(flags, "blocker", "duplicate_nih_pi_project_year_rows", "NIH award audit contains duplicate PI/project/year rows")

    nih_match_counts = Counter(row["pi_match_type"] for row in nih_awards)
    active_nih_dept = sum(int_field(row, "nih_active_projects") for row in nih_dept)
    active_nih_summary = sum(int_field(row, "nih_active_projects") for row in summary)
    if active_nih_dept > active_nih_summary:
        add_flag(flags, "blocker", "nih_active_project_reconciliation", f"department={active_nih_dept}, faculty={active_nih_summary}")
    elif active_nih_dept != active_nih_summary:
        add_flag(
            flags,
            "review",
            "nih_active_project_denominator_difference",
            f"department unique active projects={active_nih_dept}, summed faculty active project attributions={active_nih_summary}",
        )

    report = {
        "timestamp": datetime.now().isoformat(),
        "blocking_issue_count": sum(1 for flag in flags if flag["severity"] == "blocker"),
        "review_issue_count": sum(1 for flag in flags if flag["severity"] == "review"),
        "row_counts": {
            "faculty_summary": len(summary),
            "faculty_work_rows": len(authorship),
            "unique_authorship_works": len(unique_authorship_works),
            "work_strategy_metrics": len(work_metrics),
            "department_strategy_metrics": len(dept_strategy),
            "topic_strategy_metrics": len(topics),
            "department_team_science": len(team),
            "department_team_science_pairs": len(pairs),
            "nih_reporter_awards": len(nih_awards),
            "department_nih_funding": len(nih_dept),
        },
        "openalex_metadata_missingness": {
            "missing_primary_topic_rows": missing_topic,
            "missing_fwci_rows": missing_fwci,
            "missing_primary_topic_share": round(missing_topic / len(work_metrics), 4) if work_metrics else 0,
            "missing_fwci_share": round(missing_fwci / len(work_metrics), 4) if work_metrics else 0,
        },
        "nih_match_counts": dict(nih_match_counts),
        "reconciliation": {
            "faculty_top10_mismatches": sum(1 for flag in flags if flag["check"] == "faculty_top10_reconciliation"),
            "active_nih_department_sum": active_nih_dept,
            "active_nih_faculty_sum": active_nih_summary,
        },
    }

    with REPORT_PATH.open("w") as f:
        json.dump(report, f, indent=2)
    with FLAGS_PATH.open("w", newline="") as f:
        fieldnames = ["severity", "check", "detail", "faculty_name", "rush_dept", "work_id", "project_num"]
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(flags)

    print(json.dumps(report, indent=2))
    if report["blocking_issue_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
