#!/usr/bin/env python3
"""Add strategy-oriented research metrics for the Rush dashboard.

This script uses three sources:
- Existing faculty-work authorship audit for Rush-led and cross-department work.
- OpenAlex work records for field-normalized impact, topics, and awards.
- NIH RePORTER project search for Rush PI funding linkage.

It keeps generated work/grant audit files separate from the faculty summary so
the original attribution table remains inspectable.
"""

import argparse
import csv
import itertools
import json
import re
import sys
import time
import urllib.parse
import urllib.request
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
REPORT_PATH = DATA_DIR / "strategy_metrics_report.json"

OPENALEX_API = "https://api.openalex.org"
NIH_API = "https://api.reporter.nih.gov/v2/projects/search"
MAILTO = "jcr@rush.edu"
YEAR_MIN = 2021
YEAR_MAX = 2026

STRATEGY_SUMMARY_FIELDS = [
    "mean_fwci_5yr",
    "top10_impact_works_5yr",
    "top10_impact_share_5yr",
    "dominant_topic_5yr",
    "dominant_topic_works_5yr",
    "openalex_awarded_works_5yr",
    "nih_awarded_works_5yr",
    "cross_dept_publications_5yr",
    "rush_led_cross_dept_5yr",
    "nih_project_years_5yr",
    "nih_unique_projects_5yr",
    "nih_active_projects",
    "nih_r01_projects_5yr",
    "nih_total_cost_5yr",
    "nih_pi_match_type",
]

WORK_METRIC_FIELDS = [
    "work_id",
    "publication_year",
    "title",
    "cited_by_count",
    "fwci",
    "citation_percentile",
    "is_top10_impact",
    "primary_topic",
    "primary_subfield",
    "primary_field",
    "primary_domain",
    "openalex_awards_count",
    "nih_awards_count",
    "nih_award_ids",
]


def read_csv(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def int_field(row, key):
    try:
        return int(float(row.get(key) or 0))
    except ValueError:
        return 0


def norm_name(value):
    return re.sub(r"[^a-z ]+", " ", (value or "").lower()).strip()


def compact_spaces(value):
    return re.sub(r"\s+", " ", value or "").strip()


def person_key(first, last):
    return (norm_name(first), norm_name(last))


def faculty_person_key(name):
    parts = norm_name(name).split()
    if len(parts) < 2:
        return ("", "")
    return (parts[0], parts[-1])


def short_work_id(work_id):
    return (work_id or "").replace("https://openalex.org/", "")


def batch_items(items, size):
    for idx in range(0, len(items), size):
        yield items[idx:idx + size]


def get_json(url, data=None, headers=None, retries=3):
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers or {"User-Agent": "RushResearchDashboard/1.0"},
    )
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(str(last_error))


def openalex_works_by_ids(work_ids, batch_size=80, limit_batches=None):
    metrics = {}
    select = ",".join([
        "id",
        "display_name",
        "publication_year",
        "cited_by_count",
        "fwci",
        "citation_normalized_percentile",
        "primary_topic",
        "awards",
    ])
    batches = list(batch_items(work_ids, batch_size))
    if limit_batches:
        batches = batches[:limit_batches]

    for idx, batch in enumerate(batches, start=1):
        ids = "|".join(short_work_id(work_id) for work_id in batch)
        params = {
            "filter": f"openalex:{ids}",
            "per_page": str(max(len(batch), 1)),
            "select": select,
            "mailto": MAILTO,
        }
        url = f"{OPENALEX_API}/works?{urllib.parse.urlencode(params, safe=':,|')}"
        data = get_json(url)
        for work in data.get("results") or []:
            metrics[work["id"]] = parse_openalex_work(work)
        print(f"  OpenAlex work batch {idx}/{len(batches)}: fetched {len(data.get('results') or [])}")
        time.sleep(0.1)
    return metrics


def parse_topic(topic):
    topic = topic or {}
    subfield = topic.get("subfield") or {}
    field = topic.get("field") or {}
    domain = topic.get("domain") or {}
    return {
        "topic": topic.get("display_name") or "",
        "subfield": subfield.get("display_name") or "",
        "field": field.get("display_name") or "",
        "domain": domain.get("display_name") or "",
    }


def parse_openalex_work(work):
    percentile = work.get("citation_normalized_percentile") or {}
    percentile_value = percentile.get("value")
    is_top10 = bool(percentile.get("is_in_top_10_percent"))
    topic = parse_topic(work.get("primary_topic"))
    awards = work.get("awards") or []
    nih_awards = [
        award.get("funder_award_id") or ""
        for award in awards
        if "national institute" in (award.get("funder_display_name") or "").lower()
        or (award.get("funder_display_name") or "").lower() == "national institutes of health"
        or re.match(r"^[A-Z]+\\d", award.get("funder_award_id") or "")
    ]
    nih_awards = sorted({award for award in nih_awards if award})
    return {
        "work_id": work.get("id", ""),
        "publication_year": work.get("publication_year", ""),
        "title": work.get("display_name", ""),
        "cited_by_count": work.get("cited_by_count", 0),
        "fwci": work.get("fwci"),
        "citation_percentile": percentile_value,
        "is_top10_impact": "true" if is_top10 else "false",
        "primary_topic": topic["topic"],
        "primary_subfield": topic["subfield"],
        "primary_field": topic["field"],
        "primary_domain": topic["domain"],
        "openalex_awards_count": len(awards),
        "nih_awards_count": len(nih_awards),
        "nih_award_ids": ";".join(nih_awards),
    }


def is_rush_led(rows):
    return any(row.get("author_position") in {"first", "last", "single"} and row.get("rush_in_work") == "true" for row in rows)


def build_team_science(authorship_rows):
    rows_by_work = defaultdict(list)
    for row in authorship_rows:
        rows_by_work[row["work_id"]].append(row)

    work_flags = {}
    dept_stats = defaultdict(Counter)
    pair_stats = defaultdict(Counter)

    for work_id, rows in rows_by_work.items():
        depts = sorted({row["rush_dept"] for row in rows if row.get("rush_dept")})
        cross_dept = len(depts) > 1
        led = is_rush_led(rows)
        work_flags[work_id] = {"cross_dept": cross_dept, "rush_led": led, "departments": depts}

        for dept in depts:
            dept_stats[dept]["recent_faculty_work_rows"] += sum(1 for row in rows if row.get("rush_dept") == dept)
            if cross_dept:
                dept_stats[dept]["cross_dept_works"] += 1
            if cross_dept and led:
                dept_stats[dept]["rush_led_cross_dept_works"] += 1
            if led:
                dept_stats[dept]["rush_led_works"] += 1

        if cross_dept:
            for dept_a, dept_b in itertools.combinations(depts, 2):
                key = (dept_a, dept_b)
                pair_stats[key]["cross_dept_works"] += 1
                if led:
                    pair_stats[key]["rush_led_cross_dept_works"] += 1

    dept_rows = []
    for dept, counts in sorted(dept_stats.items()):
        cross = counts["cross_dept_works"]
        recent = counts["recent_faculty_work_rows"]
        dept_rows.append({
            "rush_dept": dept,
            "recent_faculty_work_rows": recent,
            "cross_dept_works": cross,
            "cross_dept_share": f"{(cross / recent) if recent else 0:.3f}",
            "rush_led_cross_dept_works": counts["rush_led_cross_dept_works"],
            "rush_led_works": counts["rush_led_works"],
        })

    pair_rows = []
    for (dept_a, dept_b), counts in sorted(pair_stats.items(), key=lambda item: (-item[1]["cross_dept_works"], item[0])):
        pair_rows.append({
            "department_a": dept_a,
            "department_b": dept_b,
            "cross_dept_works": counts["cross_dept_works"],
            "rush_led_cross_dept_works": counts["rush_led_cross_dept_works"],
        })
    return work_flags, dept_rows, pair_rows


def fetch_nih_projects(limit_pages=None):
    results = []
    offset = 0
    limit = 500
    page = 0
    while True:
        page += 1
        payload = {
            "criteria": {
                "org_names": ["RUSH UNIVERSITY MEDICAL CENTER"],
                "fiscal_years": list(range(YEAR_MIN, YEAR_MAX + 1)),
            },
            "offset": offset,
            "limit": limit,
        }
        req_data = json.dumps(payload).encode()
        data = get_json(
            NIH_API,
            data=req_data,
            headers={"Content-Type": "application/json", "User-Agent": "RushResearchDashboard/1.0"},
        )
        page_results = data.get("results") or []
        results.extend(page_results)
        total = int((data.get("meta") or {}).get("total") or 0)
        print(f"  NIH RePORTER page {page}: fetched {len(page_results)} of {total}")
        offset += len(page_results)
        if not page_results or offset >= total or (limit_pages and page >= limit_pages):
            break
        time.sleep(0.2)
    deduped = []
    seen = set()
    for project in results:
        key = (project.get("appl_id"), project.get("subproject_id"), project.get("project_num"), project.get("fiscal_year"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(project)
    return deduped


def normalize_activity(activity):
    return (activity or "").strip().upper()


def project_id(project):
    return project.get("core_project_num") or project.get("project_num") or ""


def project_ids(projects, predicate=None):
    ids = set()
    for project in projects:
        if predicate and not predicate(project):
            continue
        value = project_id(project)
        if value:
            ids.add(value)
    return ids


def total_award_amount(projects):
    return sum(int(float(project.get("award_amount") or 0)) for project in projects)


def is_active_project(project):
    return bool(project.get("is_active"))


def is_r01_project(project):
    return normalize_activity(project.get("activity_code")) == "R01"


def nih_award_rows(projects, faculty_rows):
    by_key = defaultdict(list)
    for row in faculty_rows:
        by_key[faculty_person_key(row["name"])].append(row)

    award_rows = []
    faculty_grants = defaultdict(list)
    unmatched = 0
    ambiguous = 0

    for project in projects:
        pis = project.get("principal_investigators") or []
        if not pis and project.get("contact_pi_name"):
            parts = norm_name(project["contact_pi_name"]).replace(",", "").split()
            if len(parts) >= 2:
                pis = [{"first_name": parts[-1], "last_name": parts[0], "is_contact_pi": True, "full_name": project["contact_pi_name"]}]
        for pi in pis:
            key = person_key(pi.get("first_name"), pi.get("last_name"))
            candidates = by_key.get(key, [])
            match_type = "unmatched"
            faculty_name = ""
            faculty_dept = ""
            if len(candidates) == 1:
                match_type = "exact_first_last"
                faculty_name = candidates[0]["name"]
                faculty_dept = candidates[0]["rush_dept"]
                faculty_grants[faculty_name].append(project)
            elif len(candidates) > 1:
                match_type = "ambiguous_first_last"
                ambiguous += 1
            else:
                unmatched += 1

            award_rows.append({
                "appl_id": project.get("appl_id", ""),
                "subproject_id": project.get("subproject_id", ""),
                "faculty_name": faculty_name,
                "rush_dept": faculty_dept,
                "pi_full_name": pi.get("full_name") or compact_spaces(f"{pi.get('first_name','')} {pi.get('last_name','')}"),
                "pi_match_type": match_type,
                "is_contact_pi": str(bool(pi.get("is_contact_pi"))).lower(),
                "fiscal_year": project.get("fiscal_year", ""),
                "project_num": project.get("project_num", ""),
                "core_project_num": project.get("core_project_num", ""),
                "activity_code": normalize_activity(project.get("activity_code")),
                "agency": (project.get("agency_ic_admin") or {}).get("abbreviation", ""),
                "award_amount": project.get("award_amount") or 0,
                "is_active": str(bool(project.get("is_active"))).lower(),
                "project_title": project.get("project_title", ""),
                "organization": (project.get("organization") or {}).get("org_name", ""),
                "project_start_date": project.get("project_start_date", ""),
                "project_end_date": project.get("project_end_date", ""),
            })

    return award_rows, faculty_grants, unmatched, ambiguous


def summarize_strategy(faculty_rows, authorship_rows, work_metrics, work_flags, faculty_grants):
    work_rows_by_faculty = defaultdict(list)
    for row in authorship_rows:
        work_rows_by_faculty[row["faculty_name"]].append(row)

    for row in faculty_rows:
        for field in STRATEGY_SUMMARY_FIELDS:
            row[field] = "0"
        row["mean_fwci_5yr"] = "0.000"
        row["top10_impact_share_5yr"] = "0.000"
        row["dominant_topic_5yr"] = ""
        row["nih_pi_match_type"] = "none"

        rows = work_rows_by_faculty.get(row["name"], [])
        fwcis = []
        topic_counts = Counter()
        top10 = 0
        awarded = 0
        nih_awarded = 0
        cross = 0
        led_cross = 0
        seen_works = set()
        for work_row in rows:
            work_id = work_row["work_id"]
            if work_id in seen_works:
                continue
            seen_works.add(work_id)
            metric = work_metrics.get(work_id) or {}
            if metric.get("fwci") not in (None, ""):
                fwcis.append(float(metric["fwci"]))
            if metric.get("is_top10_impact") == "true":
                top10 += 1
            if metric.get("primary_topic"):
                topic_counts[metric["primary_topic"]] += 1
            if int(metric.get("openalex_awards_count") or 0):
                awarded += 1
            if int(metric.get("nih_awards_count") or 0):
                nih_awarded += 1
            flags = work_flags.get(work_id) or {}
            if flags.get("cross_dept"):
                cross += 1
            if flags.get("cross_dept") and flags.get("rush_led"):
                led_cross += 1

        recent = len(seen_works)
        row["mean_fwci_5yr"] = f"{(sum(fwcis) / len(fwcis)) if fwcis else 0:.3f}"
        row["top10_impact_works_5yr"] = str(top10)
        row["top10_impact_share_5yr"] = f"{(top10 / recent) if recent else 0:.3f}"
        if topic_counts:
            topic, count = topic_counts.most_common(1)[0]
            row["dominant_topic_5yr"] = topic
            row["dominant_topic_works_5yr"] = str(count)
        row["openalex_awarded_works_5yr"] = str(awarded)
        row["nih_awarded_works_5yr"] = str(nih_awarded)
        row["cross_dept_publications_5yr"] = str(cross)
        row["rush_led_cross_dept_5yr"] = str(led_cross)

        grants = faculty_grants.get(row["name"], [])
        if grants:
            row["nih_project_years_5yr"] = str(len(grants))
            row["nih_unique_projects_5yr"] = str(len(project_ids(grants)))
            row["nih_active_projects"] = str(len(project_ids(grants, is_active_project)))
            row["nih_r01_projects_5yr"] = str(len(project_ids(grants, is_r01_project)))
            row["nih_total_cost_5yr"] = str(total_award_amount(grants))
            row["nih_pi_match_type"] = "exact_first_last"


def build_department_outputs(faculty_rows, authorship_rows, work_metrics, faculty_grants):
    by_work = defaultdict(list)
    for row in authorship_rows:
        by_work[row["work_id"]].append(row)

    dept_work_ids = defaultdict(set)
    dept_topic_counts = defaultdict(Counter)
    dept_fwcis = defaultdict(list)
    dept_top10 = defaultdict(int)
    dept_awarded = defaultdict(int)
    dept_nih_awarded = defaultdict(int)
    topic_stats = defaultdict(Counter)
    topic_fwcis = defaultdict(list)

    for work_id, rows in by_work.items():
        metric = work_metrics.get(work_id) or {}
        depts = {row["rush_dept"] for row in rows if row.get("rush_dept")}
        topic = metric.get("primary_topic") or "Unclassified topic"
        field = metric.get("primary_field") or "Unclassified field"
        domain = metric.get("primary_domain") or "Unclassified domain"
        top10 = metric.get("is_top10_impact") == "true"
        fwci = metric.get("fwci")
        if fwci not in (None, ""):
            topic_fwcis[(topic, field, domain)].append(float(fwci))
        topic_stats[(topic, field, domain)]["works"] += 1
        if top10:
            topic_stats[(topic, field, domain)]["top10_works"] += 1
        if is_rush_led(rows):
            topic_stats[(topic, field, domain)]["rush_led_works"] += 1

        for dept in depts:
            dept_work_ids[dept].add(work_id)
            dept_topic_counts[dept][topic] += 1
            if fwci not in (None, ""):
                dept_fwcis[dept].append(float(fwci))
            if top10:
                dept_top10[dept] += 1
            if int(metric.get("openalex_awards_count") or 0):
                dept_awarded[dept] += 1
            if int(metric.get("nih_awards_count") or 0):
                dept_nih_awarded[dept] += 1

    faculty_dept_by_name = {row["name"]: row["rush_dept"] for row in faculty_rows}
    grant_by_dept = defaultdict(list)
    for faculty_name, grants in faculty_grants.items():
        dept = faculty_dept_by_name.get(faculty_name, "")
        grant_by_dept[dept].extend(grants)

    dept_rows = []
    nih_rows = []
    for dept in sorted({row["rush_dept"] for row in faculty_rows}):
        works = dept_work_ids.get(dept, set())
        fwcis = dept_fwcis.get(dept, [])
        top_topic, top_topic_count = ("", 0)
        if dept_topic_counts.get(dept):
            top_topic, top_topic_count = dept_topic_counts[dept].most_common(1)[0]
        recent = len(works)
        dept_rows.append({
            "rush_dept": dept,
            "unique_recent_works": recent,
            "mean_fwci": f"{(sum(fwcis) / len(fwcis)) if fwcis else 0:.3f}",
            "top10_impact_works": dept_top10[dept],
            "top10_impact_share": f"{(dept_top10[dept] / recent) if recent else 0:.3f}",
            "top_topic": top_topic,
            "top_topic_works": top_topic_count,
            "openalex_awarded_works": dept_awarded[dept],
            "nih_awarded_works": dept_nih_awarded[dept],
        })

        grants = grant_by_dept.get(dept, [])
        nih_rows.append({
            "rush_dept": dept,
            "nih_project_years_5yr": len(grants),
            "nih_unique_projects_5yr": len(project_ids(grants)),
            "nih_active_projects": len(project_ids(grants, is_active_project)),
            "nih_r01_projects_5yr": len(project_ids(grants, is_r01_project)),
            "nih_total_cost_5yr": total_award_amount(grants),
        })

    topic_rows = []
    for (topic, field, domain), counts in sorted(topic_stats.items(), key=lambda item: (-item[1]["works"], item[0][0])):
        fwcis = topic_fwcis.get((topic, field, domain), [])
        topic_rows.append({
            "primary_topic": topic,
            "primary_field": field,
            "primary_domain": domain,
            "works": counts["works"],
            "rush_led_works": counts["rush_led_works"],
            "top10_impact_works": counts["top10_works"],
            "top10_impact_share": f"{(counts['top10_works'] / counts['works']) if counts['works'] else 0:.3f}",
            "mean_fwci": f"{(sum(fwcis) / len(fwcis)) if fwcis else 0:.3f}",
        })
    return dept_rows, topic_rows, nih_rows


def main():
    parser = argparse.ArgumentParser(description="Enrich Rush dashboard with strategy metrics.")
    parser.add_argument("--limit-openalex-batches", type=int, default=None, help="Debug: fetch only N OpenAlex batches.")
    parser.add_argument("--limit-nih-pages", type=int, default=None, help="Debug: fetch only N NIH pages.")
    args = parser.parse_args()

    faculty_rows = read_csv(SUMMARY_CSV)
    fieldnames = list(faculty_rows[0].keys())
    for field in STRATEGY_SUMMARY_FIELDS:
        if field not in fieldnames:
            fieldnames.append(field)

    authorship_rows = read_csv(AUTHORSHIP_WORKS_CSV)
    unique_work_ids = sorted({row["work_id"] for row in authorship_rows if row.get("work_id")})
    authorship_by_work = {}
    for row in authorship_rows:
        authorship_by_work.setdefault(row["work_id"], row)

    print("Rush strategy metric enrichment")
    print(f"  Faculty rows: {len(faculty_rows)}")
    print(f"  Faculty-work rows: {len(authorship_rows)}")
    print(f"  Unique works: {len(unique_work_ids)}")

    existing_metric_rows = read_csv(WORK_METRICS_CSV) if WORK_METRICS_CSV.exists() and not args.limit_openalex_batches else []
    existing_metric_ids = {row.get("work_id") for row in existing_metric_rows}
    if existing_metric_ids == set(unique_work_ids):
        print(f"  Reusing existing OpenAlex work metrics: {WORK_METRICS_CSV}")
        work_metrics = {row["work_id"]: row for row in existing_metric_rows}
    else:
        work_metrics = openalex_works_by_ids(unique_work_ids, limit_batches=args.limit_openalex_batches)
    for work_id in unique_work_ids:
        if work_id not in work_metrics:
            matching = authorship_by_work.get(work_id, {})
            work_metrics[work_id] = {
                "work_id": work_id,
                "publication_year": matching.get("publication_year", ""),
                "title": matching.get("title", ""),
                "cited_by_count": matching.get("cited_by_count", 0),
                "fwci": "",
                "citation_percentile": "",
                "is_top10_impact": "false",
                "primary_topic": "",
                "primary_subfield": "",
                "primary_field": "",
                "primary_domain": "",
                "openalex_awards_count": 0,
                "nih_awards_count": 0,
                "nih_award_ids": "",
            }

    work_metric_rows = [work_metrics[work_id] for work_id in unique_work_ids]

    work_flags, team_dept_rows, team_pair_rows = build_team_science(authorship_rows)
    nih_projects = fetch_nih_projects(limit_pages=args.limit_nih_pages)
    nih_rows, faculty_grants, unmatched_nih, ambiguous_nih = nih_award_rows(nih_projects, faculty_rows)

    summarize_strategy(faculty_rows, authorship_rows, work_metrics, work_flags, faculty_grants)
    dept_strategy_rows, topic_rows, dept_nih_rows = build_department_outputs(faculty_rows, authorship_rows, work_metrics, faculty_grants)

    write_csv(SUMMARY_CSV, faculty_rows, fieldnames)
    write_csv(WORK_METRICS_CSV, work_metric_rows, WORK_METRIC_FIELDS)
    write_csv(DEPT_STRATEGY_CSV, dept_strategy_rows, list(dept_strategy_rows[0].keys()))
    write_csv(TOPIC_STRATEGY_CSV, topic_rows, list(topic_rows[0].keys()))
    write_csv(TEAM_SCIENCE_CSV, team_dept_rows, list(team_dept_rows[0].keys()))
    write_csv(TEAM_PAIRS_CSV, team_pair_rows, list(team_pair_rows[0].keys()))
    write_csv(NIH_AWARDS_CSV, nih_rows, list(nih_rows[0].keys()))
    write_csv(NIH_DEPT_CSV, dept_nih_rows, list(dept_nih_rows[0].keys()))

    report = {
        "timestamp": datetime.now().isoformat(),
        "year_window": f"{YEAR_MIN}-{YEAR_MAX}",
        "faculty_rows": len(faculty_rows),
        "faculty_work_rows": len(authorship_rows),
        "unique_works": len(unique_work_ids),
        "openalex_work_metrics_rows": len(work_metric_rows),
        "openalex_missing_work_rows": sum(1 for row in work_metric_rows if not row.get("primary_topic") and not row.get("fwci")),
        "top10_impact_work_rows": sum(1 for row in work_metric_rows if row.get("is_top10_impact") == "true"),
        "topic_rows": len(topic_rows),
        "cross_department_unique_works": sum(1 for flags in work_flags.values() if flags["cross_dept"]),
        "rush_led_cross_department_unique_works": sum(1 for flags in work_flags.values() if flags["cross_dept"] and flags["rush_led"]),
        "nih_reporter_project_pi_year_rows": len(nih_rows),
        "nih_reporter_exact_pi_matches": sum(1 for row in nih_rows if row["pi_match_type"] == "exact_first_last"),
        "nih_reporter_unmatched_pi_rows": unmatched_nih,
        "nih_reporter_ambiguous_pi_rows": ambiguous_nih,
        "outputs": {
            "work_metrics": str(WORK_METRICS_CSV.relative_to(REPO_ROOT)),
            "department_strategy": str(DEPT_STRATEGY_CSV.relative_to(REPO_ROOT)),
            "topic_strategy": str(TOPIC_STRATEGY_CSV.relative_to(REPO_ROOT)),
            "team_science": str(TEAM_SCIENCE_CSV.relative_to(REPO_ROOT)),
            "team_pairs": str(TEAM_PAIRS_CSV.relative_to(REPO_ROOT)),
            "nih_awards": str(NIH_AWARDS_CSV.relative_to(REPO_ROOT)),
            "nih_department": str(NIH_DEPT_CSV.relative_to(REPO_ROOT)),
        },
    }
    with REPORT_PATH.open("w") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
