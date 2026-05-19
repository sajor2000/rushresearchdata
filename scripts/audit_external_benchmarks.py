#!/usr/bin/env python3
"""Audit external benchmark inputs and generated dashboard summaries."""

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

AUTHORSHIP_WORKS_CSV = DATA_DIR / "faculty_authorship_works.csv"
IDENTITY_OVERRIDES_CSV = DATA_DIR / "faculty_identity_overrides.csv"
WORK_ALTMETRICS_CSV = DATA_DIR / "work_altmetrics.csv"
EXTERNAL_FUNDING_CSV = DATA_DIR / "external_funding_benchmarks.csv"
BRIMR_RANKINGS_CSV = DATA_DIR / "brimr_department_rankings.csv"
FACULTY_ALTMETRICS_CSV = DATA_DIR / "faculty_altmetric_summary.csv"
DEPT_ALTMETRICS_CSV = DATA_DIR / "department_altmetric_summary.csv"
TOP_ALTMETRIC_WORKS_CSV = DATA_DIR / "top_altmetric_works.csv"
IDENTITY_QUEUE_CSV = DATA_DIR / "identity_review_queue.csv"
REPORT_JSON = DATA_DIR / "external_benchmark_report.json"
AUDIT_JSON = DATA_DIR / "external_benchmark_quality_audit.json"
FLAGS_CSV = DATA_DIR / "external_benchmark_quality_flags.csv"

ALLOWED_OVERRIDE_STATUSES = {"confirmed_primary", "split_profile_review", "wrong_person_review", "do_not_merge"}


def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def num_value(row, key):
    try:
        return float(row.get(key) or 0)
    except ValueError:
        return None


def norm_doi(value):
    value = (value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if value.startswith(prefix):
            value = value[len(prefix):]
    return value


def add_flag(flags, severity, check, detail, row=None):
    row = row or {}
    flags.append({
        "severity": severity,
        "check": check,
        "detail": detail,
        "faculty_name": row.get("faculty_name", ""),
        "rush_dept": row.get("rush_dept", "") or row.get("department_or_category", ""),
        "work_id": row.get("work_id", ""),
        "source": row.get("source", ""),
    })


def duplicate_count(keys):
    counts = Counter(keys)
    return sum(1 for count in counts.values() if count > 1)


def main():
    authorship = read_csv(AUTHORSHIP_WORKS_CSV)
    overrides = read_csv(IDENTITY_OVERRIDES_CSV)
    altmetrics = read_csv(WORK_ALTMETRICS_CSV)
    external_funding = read_csv(EXTERNAL_FUNDING_CSV)
    brimr = read_csv(BRIMR_RANKINGS_CSV)
    faculty_alt = read_csv(FACULTY_ALTMETRICS_CSV)
    dept_alt = read_csv(DEPT_ALTMETRICS_CSV)
    top_alt = read_csv(TOP_ALTMETRIC_WORKS_CSV)
    identity_queue = read_csv(IDENTITY_QUEUE_CSV)
    flags = []

    faculty_keys = {(row.get("faculty_name", ""), row.get("rush_dept", "")) for row in authorship}
    work_ids = {row.get("work_id", "") for row in authorship}
    dois = {norm_doi(row.get("doi", "")) for row in authorship if norm_doi(row.get("doi", ""))}

    override_keys = []
    for row in overrides:
        override_keys.append((row.get("faculty_name", ""), row.get("rush_dept", ""), row.get("primary_openalex_id", ""), row.get("status", "")))
        if row.get("status") not in ALLOWED_OVERRIDE_STATUSES:
            add_flag(flags, "blocker", "invalid_identity_override_status", row.get("status", ""), row)
        if (row.get("faculty_name", ""), row.get("rush_dept", "")) not in faculty_keys:
            add_flag(flags, "blocker", "identity_override_not_in_authorship_data", "override faculty/dept not found in faculty-work rows", row)
        if row.get("status") == "split_profile_review" and not row.get("alternate_openalex_ids"):
            add_flag(flags, "blocker", "split_profile_missing_alternate_ids", "split-profile override needs alternate OpenAlex IDs", row)
        if row.get("status") != "confirmed_primary" and not row.get("source_urls"):
            add_flag(flags, "blocker", "identity_override_missing_source_urls", "review override needs source URLs", row)
    if duplicate_count(override_keys):
        add_flag(flags, "blocker", "duplicate_identity_override_keys", f"{duplicate_count(override_keys)} duplicate override key(s)")

    altmetric_keys = []
    matched_altmetrics = 0
    for row in altmetrics:
        doi = norm_doi(row.get("doi", ""))
        work_id = row.get("work_id", "")
        altmetric_keys.append((doi, work_id, row.get("source", "")))
        if not doi and not work_id:
            add_flag(flags, "blocker", "altmetric_missing_join_key", "row needs DOI or OpenAlex work ID", row)
        if work_id and work_id not in work_ids:
            add_flag(flags, "review", "altmetric_work_id_not_in_authorship_data", "OpenAlex work ID did not match faculty-work rows", row)
        if doi and doi not in dois and not work_id:
            add_flag(flags, "review", "altmetric_doi_not_in_authorship_data", "DOI did not match faculty-work rows", row)
        if (work_id and work_id in work_ids) or (doi and doi in dois):
            matched_altmetrics += 1
        for numeric_field in ["altmetric_score", "news_mentions", "policy_mentions", "social_mentions", "mendeley_readers"]:
            value = num_value(row, numeric_field)
            if value is None or value < 0:
                add_flag(flags, "blocker", "invalid_altmetric_numeric_value", f"{numeric_field}={row.get(numeric_field, '')}", row)
    if altmetrics and duplicate_count(altmetric_keys):
        add_flag(flags, "blocker", "duplicate_altmetric_rows", f"{duplicate_count(altmetric_keys)} duplicate DOI/work/source key(s)")
    if not altmetrics:
        add_flag(flags, "review", "no_altmetric_rows_imported", "work_altmetrics.csv has headers only; dashboard will show no imported attention data")

    funding_keys = []
    for row in external_funding:
        funding_keys.append((row.get("year", ""), row.get("source", ""), row.get("organization", ""), row.get("department_or_category", "")))
        for numeric_field in ["nih_dollars", "rank", "active_projects", "r01_count"]:
            value = num_value(row, numeric_field)
            if value is None or value < 0:
                add_flag(flags, "blocker", "invalid_external_funding_numeric_value", f"{numeric_field}={row.get(numeric_field, '')}", row)
        if not row.get("source_url"):
            add_flag(flags, "blocker", "external_funding_missing_source_url", "benchmark rows need source URLs", row)
    if external_funding and duplicate_count(funding_keys):
        add_flag(flags, "blocker", "duplicate_external_funding_rows", f"{duplicate_count(funding_keys)} duplicate benchmark key(s)")
    if not external_funding:
        add_flag(flags, "review", "no_external_funding_rows_imported", "external_funding_benchmarks.csv has headers only")

    brimr_keys = []
    for row in brimr:
        brimr_keys.append((row.get("year", ""), row.get("organization", ""), row.get("brimr_category", "")))
        for numeric_field in ["rank", "total_nih_funding", "peer_count"]:
            value = num_value(row, numeric_field)
            if value is None or value < 0:
                add_flag(flags, "blocker", "invalid_brimr_numeric_value", f"{numeric_field}={row.get(numeric_field, '')}", row)
        if not row.get("source_url"):
            add_flag(flags, "blocker", "brimr_missing_source_url", "BRIMR rows need source URLs", row)
    if brimr and duplicate_count(brimr_keys):
        add_flag(flags, "blocker", "duplicate_brimr_rows", f"{duplicate_count(brimr_keys)} duplicate BRIMR key(s)")
    if not brimr:
        add_flag(flags, "review", "no_brimr_rows_imported", "brimr_department_rankings.csv has headers only")

    report = {}
    if REPORT_JSON.exists():
        report = json.loads(REPORT_JSON.read_text())
    if int(report.get("identity_review_queue_rows", 0)) != len(identity_queue):
        add_flag(flags, "blocker", "identity_queue_report_mismatch", f"report={report.get('identity_review_queue_rows')}, csv={len(identity_queue)}")
    if int(report.get("top_altmetric_work_rows", 0)) != len(top_alt):
        add_flag(flags, "blocker", "top_altmetric_report_mismatch", f"report={report.get('top_altmetric_work_rows')}, csv={len(top_alt)}")

    audit = {
        "timestamp": datetime.now().isoformat(),
        "blocking_issue_count": sum(1 for flag in flags if flag["severity"] == "blocker"),
        "review_issue_count": sum(1 for flag in flags if flag["severity"] == "review"),
        "row_counts": {
            "identity_overrides": len(overrides),
            "identity_review_queue": len(identity_queue),
            "work_altmetrics": len(altmetrics),
            "faculty_altmetric_summary": len(faculty_alt),
            "department_altmetric_summary": len(dept_alt),
            "top_altmetric_works": len(top_alt),
            "external_funding_benchmarks": len(external_funding),
            "brimr_department_rankings": len(brimr),
        },
        "duplicate_checks": {
            "duplicate_identity_override_keys": duplicate_count(override_keys),
            "duplicate_altmetric_keys": duplicate_count(altmetric_keys) if altmetrics else 0,
            "duplicate_external_funding_keys": duplicate_count(funding_keys) if external_funding else 0,
            "duplicate_brimr_keys": duplicate_count(brimr_keys) if brimr else 0,
        },
        "join_coverage": {
            "altmetric_rows_matched_to_faculty_work": matched_altmetrics,
            "altmetric_rows_unmatched_to_faculty_work": max(len(altmetrics) - matched_altmetrics, 0),
        },
        "source_mode": "csv_import",
    }

    AUDIT_JSON.write_text(json.dumps(audit, indent=2))
    with FLAGS_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["severity", "check", "detail", "faculty_name", "rush_dept", "work_id", "source"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(flags)

    print(json.dumps(audit, indent=2))
    if audit["blocking_issue_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
