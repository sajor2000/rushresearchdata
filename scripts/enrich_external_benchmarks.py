#!/usr/bin/env python3
"""Build external benchmark summary files for the Rush dashboard.

The V1 path is CSV-first: Altmetric, BRIMR, and external funding rows can be
filled from institutional exports without requiring credentials or scraping.
"""

import csv
import json
from collections import Counter, defaultdict
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
REPORT_PATH = DATA_DIR / "external_benchmark_report.json"


def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def num_field(row, key):
    try:
        return float(row.get(key) or 0)
    except ValueError:
        return 0.0


def int_field(row, key):
    return int(round(num_field(row, key)))


def norm_doi(value):
    value = (value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if value.startswith(prefix):
            value = value[len(prefix):]
    return value


def by_key(rows, key):
    out = defaultdict(list)
    for row in rows:
        if row.get(key):
            out[row[key]].append(row)
    return out


def build_identity_queue(overrides):
    rows = []
    for row in overrides:
        status = row.get("status", "")
        if status in {"split_profile_review", "wrong_person_review", "do_not_merge"}:
            rows.append({
                "faculty_name": row.get("faculty_name", ""),
                "rush_dept": row.get("rush_dept", ""),
                "status": status,
                "confidence": row.get("confidence", ""),
                "primary_openalex_id": row.get("primary_openalex_id", ""),
                "alternate_openalex_ids": row.get("alternate_openalex_ids", ""),
                "source_urls": row.get("source_urls", ""),
                "last_checked": row.get("last_checked", ""),
                "notes": row.get("notes", ""),
            })
    return rows


def build_altmetric_summaries(authorship_rows, altmetric_rows):
    authorship_by_work = by_key(authorship_rows, "work_id")
    authorship_by_doi = defaultdict(list)
    for row in authorship_rows:
        doi = norm_doi(row.get("doi", ""))
        if doi:
            authorship_by_doi[doi].append(row)

    faculty_stats = defaultdict(Counter)
    dept_stats = defaultdict(Counter)
    top_work_map = {}
    matched_rows = 0
    unmatched_rows = 0

    for alt in altmetric_rows:
        doi = norm_doi(alt.get("doi", ""))
        work_id = alt.get("work_id", "").strip()
        matched_authorship = []
        if doi:
            matched_authorship = authorship_by_doi.get(doi, [])
        if not matched_authorship and work_id:
            matched_authorship = authorship_by_work.get(work_id, [])

        score = num_field(alt, "altmetric_score")
        news = int_field(alt, "news_mentions")
        policy = int_field(alt, "policy_mentions")
        social = int_field(alt, "social_mentions")
        readers = int_field(alt, "mendeley_readers")

        if not matched_authorship:
            unmatched_rows += 1
            continue
        matched_rows += 1

        work_key = matched_authorship[0].get("work_id") or work_id or doi
        top_work = top_work_map.setdefault(work_key, {
            "work_id": work_key,
            "doi": doi or alt.get("doi", ""),
            "title": matched_authorship[0].get("title", ""),
            "publication_year": matched_authorship[0].get("publication_year", ""),
            "altmetric_score": score,
            "news_mentions": news,
            "policy_mentions": policy,
            "social_mentions": social,
            "mendeley_readers": readers,
            "faculty_count": 0,
            "faculty_names": set(),
            "departments": set(),
            "source": alt.get("source", ""),
            "last_checked": alt.get("last_checked", ""),
        })
        top_work["altmetric_score"] = max(top_work["altmetric_score"], score)
        top_work["news_mentions"] = max(top_work["news_mentions"], news)
        top_work["policy_mentions"] = max(top_work["policy_mentions"], policy)
        top_work["social_mentions"] = max(top_work["social_mentions"], social)
        top_work["mendeley_readers"] = max(top_work["mendeley_readers"], readers)

        seen_faculty_for_alt = set()
        seen_depts_for_alt = set()
        for work in matched_authorship:
            faculty = work.get("faculty_name", "")
            dept = work.get("rush_dept", "")
            top_work["faculty_names"].add(faculty)
            top_work["departments"].add(dept)
            if faculty and faculty not in seen_faculty_for_alt:
                faculty_stats[faculty]["matched_works"] += 1
                faculty_stats[faculty]["altmetric_score"] += score
                faculty_stats[faculty]["news_mentions"] += news
                faculty_stats[faculty]["policy_mentions"] += policy
                faculty_stats[faculty]["social_mentions"] += social
                faculty_stats[faculty]["mendeley_readers"] += readers
                seen_faculty_for_alt.add(faculty)
            if dept and dept not in seen_depts_for_alt:
                dept_stats[dept]["matched_works"] += 1
                dept_stats[dept]["altmetric_score"] += score
                dept_stats[dept]["news_mentions"] += news
                dept_stats[dept]["policy_mentions"] += policy
                dept_stats[dept]["social_mentions"] += social
                dept_stats[dept]["mendeley_readers"] += readers
                seen_depts_for_alt.add(dept)
        top_work["faculty_count"] = len(top_work["faculty_names"])

    faculty_rows = [
        {"faculty_name": faculty, **dict(stats)}
        for faculty, stats in sorted(faculty_stats.items(), key=lambda item: (-item[1]["altmetric_score"], item[0]))
    ]
    dept_rows = [
        {"rush_dept": dept, **dict(stats)}
        for dept, stats in sorted(dept_stats.items(), key=lambda item: (-item[1]["altmetric_score"], item[0]))
    ]
    top_rows = []
    for row in top_work_map.values():
        next_row = dict(row)
        next_row["faculty_names"] = "|".join(sorted(row["faculty_names"]))
        next_row["departments"] = "|".join(sorted(row["departments"]))
        top_rows.append(next_row)
    top_rows.sort(key=lambda row: (-float(row["altmetric_score"]), row["title"]))

    return faculty_rows, dept_rows, top_rows, matched_rows, unmatched_rows


def main():
    authorship = read_csv(AUTHORSHIP_WORKS_CSV)
    overrides = read_csv(IDENTITY_OVERRIDES_CSV)
    altmetrics = read_csv(WORK_ALTMETRICS_CSV)
    external_funding = read_csv(EXTERNAL_FUNDING_CSV)
    brimr = read_csv(BRIMR_RANKINGS_CSV)

    identity_queue = build_identity_queue(overrides)
    faculty_alt, dept_alt, top_alt, matched_alt, unmatched_alt = build_altmetric_summaries(authorship, altmetrics)

    write_csv(IDENTITY_QUEUE_CSV, identity_queue, [
        "faculty_name", "rush_dept", "status", "confidence", "primary_openalex_id",
        "alternate_openalex_ids", "source_urls", "last_checked", "notes",
    ])
    write_csv(FACULTY_ALTMETRICS_CSV, faculty_alt, [
        "faculty_name", "matched_works", "altmetric_score", "news_mentions",
        "policy_mentions", "social_mentions", "mendeley_readers",
    ])
    write_csv(DEPT_ALTMETRICS_CSV, dept_alt, [
        "rush_dept", "matched_works", "altmetric_score", "news_mentions",
        "policy_mentions", "social_mentions", "mendeley_readers",
    ])
    write_csv(TOP_ALTMETRIC_WORKS_CSV, top_alt, [
        "work_id", "doi", "title", "publication_year", "altmetric_score",
        "news_mentions", "policy_mentions", "social_mentions", "mendeley_readers",
        "faculty_count", "faculty_names", "departments", "source", "last_checked",
    ])

    report = {
        "timestamp": datetime.now().isoformat(),
        "identity_override_rows": len(overrides),
        "identity_review_queue_rows": len(identity_queue),
        "altmetric_import_rows": len(altmetrics),
        "altmetric_matched_rows": matched_alt,
        "altmetric_unmatched_rows": unmatched_alt,
        "faculty_altmetric_summary_rows": len(faculty_alt),
        "department_altmetric_summary_rows": len(dept_alt),
        "top_altmetric_work_rows": len(top_alt),
        "external_funding_benchmark_rows": len(external_funding),
        "brimr_department_ranking_rows": len(brimr),
        "source_mode": "csv_import",
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
