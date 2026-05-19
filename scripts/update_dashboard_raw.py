#!/usr/bin/env python3
"""Regenerate the embedded RAW data block in index.html from the faculty CSV."""

import csv
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "data" / "rush_researcher_h_index.csv"
INDEX_PATH = REPO_ROOT / "index.html"
DEPT_STRATEGY_PATH = REPO_ROOT / "data" / "department_strategy_metrics.csv"
TOPIC_STRATEGY_PATH = REPO_ROOT / "data" / "topic_strategy_metrics.csv"
TEAM_SCIENCE_PATH = REPO_ROOT / "data" / "department_team_science.csv"
TEAM_PAIRS_PATH = REPO_ROOT / "data" / "department_team_science_pairs.csv"
NIH_DEPT_PATH = REPO_ROOT / "data" / "department_nih_funding.csv"
IDENTITY_QUEUE_PATH = REPO_ROOT / "data" / "identity_review_queue.csv"
TOP_ALTMETRIC_WORKS_PATH = REPO_ROOT / "data" / "top_altmetric_works.csv"
DEPT_ALTMETRICS_PATH = REPO_ROOT / "data" / "department_altmetric_summary.csv"
EXTERNAL_FUNDING_PATH = REPO_ROOT / "data" / "external_funding_benchmarks.csv"
BRIMR_RANKINGS_PATH = REPO_ROOT / "data" / "brimr_department_rankings.csv"
EXTERNAL_REPORT_PATH = REPO_ROOT / "data" / "external_benchmark_report.json"


def int_field(row, key):
    try:
        return int(float(row.get(key) or 0))
    except ValueError:
        return 0


def float_field(row, key, digits=2):
    try:
        return round(float(row.get(key) or 0), digits)
    except ValueError:
        return 0.0


def build_raw_rows():
    with CSV_PATH.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return [
        {
            "name": row.get("name", ""),
            "h": int_field(row, "h_index"),
            "i10": int_field(row, "i10_index"),
            "works": int_field(row, "works_count"),
            "cites": int_field(row, "cited_by_count"),
            "r5": int_field(row, "rush_works_5yr"),
            "cy2": float_field(row, "two_year_mean_citedness"),
            "recent5": int_field(row, "recent_author_works_5yr"),
            "senior5": int_field(row, "senior_author_5yr"),
            "first5": int_field(row, "first_author_5yr"),
            "contrib5": int_field(row, "contributing_author_5yr"),
            "ambiguous5": int_field(row, "ambiguous_author_5yr"),
            "leadershipRatio5": float_field(row, "leadership_ratio_5yr", 3),
            "rushSenior5": int_field(row, "rush_affiliated_senior_5yr"),
            "externalContrib5": int_field(row, "external_contributor_5yr"),
            "corresponding5": int_field(row, "corresponding_author_5yr"),
            "meanFwci5": float_field(row, "mean_fwci_5yr", 3),
            "top10Impact5": int_field(row, "top10_impact_works_5yr"),
            "top10ImpactShare5": float_field(row, "top10_impact_share_5yr", 3),
            "dominantTopic5": row.get("dominant_topic_5yr", ""),
            "dominantTopicWorks5": int_field(row, "dominant_topic_works_5yr"),
            "awardedWorks5": int_field(row, "openalex_awarded_works_5yr"),
            "nihAwardedWorks5": int_field(row, "nih_awarded_works_5yr"),
            "crossDept5": int_field(row, "cross_dept_publications_5yr"),
            "rushLedCrossDept5": int_field(row, "rush_led_cross_dept_5yr"),
            "nihProjectYears5": int_field(row, "nih_project_years_5yr"),
            "nihUniqueProjects5": int_field(row, "nih_unique_projects_5yr"),
            "nihActiveProjects": int_field(row, "nih_active_projects"),
            "nihR01Projects5": int_field(row, "nih_r01_projects_5yr"),
            "nihTotalCost5": int_field(row, "nih_total_cost_5yr"),
            "nihPiMatchType": row.get("nih_pi_match_type", ""),
            "dept": row.get("rush_dept", ""),
            "college": row.get("college", ""),
            "orcid": row.get("orcid", ""),
            "mt": row.get("match_type", ""),
        }
        for row in rows
    ]


def read_rows(path):
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def build_department_strategy_rows():
    return [
        {
            "dept": row.get("rush_dept", ""),
            "uniqueRecentWorks": int_field(row, "unique_recent_works"),
            "meanFwci": float_field(row, "mean_fwci", 3),
            "top10ImpactWorks": int_field(row, "top10_impact_works"),
            "top10ImpactShare": float_field(row, "top10_impact_share", 3),
            "topTopic": row.get("top_topic", ""),
            "topTopicWorks": int_field(row, "top_topic_works"),
            "awardedWorks": int_field(row, "openalex_awarded_works"),
            "nihAwardedWorks": int_field(row, "nih_awarded_works"),
        }
        for row in read_rows(DEPT_STRATEGY_PATH)
    ]


def build_topic_strategy_rows(limit=80):
    rows = read_rows(TOPIC_STRATEGY_PATH)
    rows.sort(key=lambda row: int_field(row, "works"), reverse=True)
    return [
        {
            "topic": row.get("primary_topic", ""),
            "field": row.get("primary_field", ""),
            "domain": row.get("primary_domain", ""),
            "works": int_field(row, "works"),
            "rushLedWorks": int_field(row, "rush_led_works"),
            "top10ImpactWorks": int_field(row, "top10_impact_works"),
            "top10ImpactShare": float_field(row, "top10_impact_share", 3),
            "meanFwci": float_field(row, "mean_fwci", 3),
        }
        for row in rows[:limit]
    ]


def build_team_science_rows():
    return [
        {
            "dept": row.get("rush_dept", ""),
            "recentRows": int_field(row, "recent_faculty_work_rows"),
            "crossDeptWorks": int_field(row, "cross_dept_works"),
            "crossDeptShare": float_field(row, "cross_dept_share", 3),
            "rushLedCrossDeptWorks": int_field(row, "rush_led_cross_dept_works"),
            "rushLedWorks": int_field(row, "rush_led_works"),
        }
        for row in read_rows(TEAM_SCIENCE_PATH)
    ]


def build_team_pair_rows(limit=40):
    rows = read_rows(TEAM_PAIRS_PATH)
    rows.sort(key=lambda row: int_field(row, "cross_dept_works"), reverse=True)
    return [
        {
            "departmentA": row.get("department_a", ""),
            "departmentB": row.get("department_b", ""),
            "crossDeptWorks": int_field(row, "cross_dept_works"),
            "rushLedCrossDeptWorks": int_field(row, "rush_led_cross_dept_works"),
        }
        for row in rows[:limit]
    ]


def build_nih_department_rows():
    return [
        {
            "dept": row.get("rush_dept", ""),
            "projectYears": int_field(row, "nih_project_years_5yr"),
            "uniqueProjects": int_field(row, "nih_unique_projects_5yr"),
            "activeProjects": int_field(row, "nih_active_projects"),
            "r01Projects": int_field(row, "nih_r01_projects_5yr"),
            "totalCost": int_field(row, "nih_total_cost_5yr"),
        }
        for row in read_rows(NIH_DEPT_PATH)
    ]


def build_identity_review_rows():
    return [
        {
            "facultyName": row.get("faculty_name", ""),
            "dept": row.get("rush_dept", ""),
            "status": row.get("status", ""),
            "confidence": row.get("confidence", ""),
            "primaryOpenalexId": row.get("primary_openalex_id", ""),
            "alternateOpenalexIds": row.get("alternate_openalex_ids", ""),
            "lastChecked": row.get("last_checked", ""),
            "notes": row.get("notes", ""),
        }
        for row in read_rows(IDENTITY_QUEUE_PATH)
    ]


def build_top_altmetric_rows(limit=40):
    rows = read_rows(TOP_ALTMETRIC_WORKS_PATH)
    rows.sort(key=lambda row: float_field(row, "altmetric_score", 3), reverse=True)
    return [
        {
            "workId": row.get("work_id", ""),
            "doi": row.get("doi", ""),
            "title": row.get("title", ""),
            "year": int_field(row, "publication_year"),
            "score": float_field(row, "altmetric_score", 3),
            "news": int_field(row, "news_mentions"),
            "policy": int_field(row, "policy_mentions"),
            "social": int_field(row, "social_mentions"),
            "mendeley": int_field(row, "mendeley_readers"),
            "facultyCount": int_field(row, "faculty_count"),
            "facultyNames": row.get("faculty_names", ""),
            "departments": row.get("departments", ""),
            "source": row.get("source", ""),
        }
        for row in rows[:limit]
    ]


def build_department_altmetric_rows():
    return [
        {
            "dept": row.get("rush_dept", ""),
            "matchedWorks": int_field(row, "matched_works"),
            "score": float_field(row, "altmetric_score", 3),
            "news": int_field(row, "news_mentions"),
            "policy": int_field(row, "policy_mentions"),
            "social": int_field(row, "social_mentions"),
            "mendeley": int_field(row, "mendeley_readers"),
        }
        for row in read_rows(DEPT_ALTMETRICS_PATH)
    ]


def build_external_funding_rows():
    return [
        {
            "year": int_field(row, "year"),
            "source": row.get("source", ""),
            "organization": row.get("organization", ""),
            "category": row.get("department_or_category", ""),
            "nihDollars": int_field(row, "nih_dollars"),
            "rank": int_field(row, "rank"),
            "activeProjects": int_field(row, "active_projects"),
            "r01Count": int_field(row, "r01_count"),
            "sourceUrl": row.get("source_url", ""),
            "lastChecked": row.get("last_checked", ""),
            "notes": row.get("notes", ""),
        }
        for row in read_rows(EXTERNAL_FUNDING_PATH)
    ]


def build_brimr_rows():
    return [
        {
            "year": int_field(row, "year"),
            "organization": row.get("organization", ""),
            "category": row.get("brimr_category", ""),
            "rank": int_field(row, "rank"),
            "totalNihFunding": int_field(row, "total_nih_funding"),
            "peerCount": int_field(row, "peer_count"),
            "sourceUrl": row.get("source_url", ""),
            "lastChecked": row.get("last_checked", ""),
            "notes": row.get("notes", ""),
        }
        for row in read_rows(BRIMR_RANKINGS_PATH)
    ]


def build_external_report():
    if not EXTERNAL_REPORT_PATH.exists():
        return {}
    return json.loads(EXTERNAL_REPORT_PATH.read_text())


def replace_const(html, name, value):
    json_value = json.dumps(value, ensure_ascii=False, separators=(",", ": "))
    pattern = rf"const {name} = (?:\[.*?\]|\{{.*?\}});"
    replacement = f"const {name} = {json_value};"
    next_html, count = re.subn(pattern, replacement, html, count=1, flags=re.S)
    if count:
        return next_html
    marker = "\n\n// =============================================\n// CONSTANTS"
    return html.replace(marker, f"\nconst {name} = {json_value};{marker}", 1)


def main():
    raw_rows = build_raw_rows()
    html = INDEX_PATH.read_text()
    next_html = replace_const(html, "RAW", raw_rows)
    next_html = replace_const(next_html, "STRATEGY_DEPT", build_department_strategy_rows())
    next_html = replace_const(next_html, "STRATEGY_TOPICS", build_topic_strategy_rows())
    next_html = replace_const(next_html, "TEAM_SCIENCE", build_team_science_rows())
    next_html = replace_const(next_html, "TEAM_PAIRS", build_team_pair_rows())
    next_html = replace_const(next_html, "NIH_DEPT", build_nih_department_rows())
    next_html = replace_const(next_html, "IDENTITY_REVIEW_QUEUE", build_identity_review_rows())
    next_html = replace_const(next_html, "TOP_ALTMETRIC_WORKS", build_top_altmetric_rows())
    next_html = replace_const(next_html, "DEPT_ALTMETRICS", build_department_altmetric_rows())
    next_html = replace_const(next_html, "EXTERNAL_FUNDING_BENCHMARKS", build_external_funding_rows())
    next_html = replace_const(next_html, "BRIMR_RANKINGS", build_brimr_rows())
    next_html = replace_const(next_html, "EXTERNAL_BENCHMARK_REPORT", build_external_report())
    INDEX_PATH.write_text(next_html)
    print(f"Updated RAW data block with {len(raw_rows)} faculty rows.")


if __name__ == "__main__":
    main()
