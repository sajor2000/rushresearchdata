#!/usr/bin/env python3
"""
Rush faculty authorship-role enrichment.

Fetches 2021-2026 OpenAlex works for matched faculty profiles, classifies the
faculty member's author position, updates data/rush_researcher_h_index.csv with
summary columns, and writes a work-level audit file.
"""

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "data" / "rush_researcher_h_index.csv"
WORK_AUDIT_PATH = REPO_ROOT / "data" / "faculty_authorship_works.csv"
REPORT_PATH = REPO_ROOT / "data" / "authorship_enrichment_report.json"

API_BASE = "https://api.openalex.org"
MAILTO = "jcr@rush.edu"
RATE_LIMIT_DELAY = 0.12
YEAR_FILTER = "2021-2026"
RUSH_INST_IDS = {"I1285301757", "I49886154"}
RUSH_INST_URLS = {f"https://openalex.org/{inst_id}" for inst_id in RUSH_INST_IDS}

SUMMARY_FIELDS = [
    "recent_author_works_5yr",
    "senior_author_5yr",
    "first_author_5yr",
    "contributing_author_5yr",
    "ambiguous_author_5yr",
    "leadership_ratio_5yr",
    "rush_affiliated_senior_5yr",
    "external_contributor_5yr",
    "corresponding_author_5yr",
]

WORK_FIELDS = [
    "faculty_name",
    "rush_dept",
    "college",
    "openalex_author_id",
    "work_id",
    "publication_year",
    "title",
    "author_position",
    "is_corresponding",
    "cited_by_count",
    "rush_in_work",
    "faculty_rush_affiliation",
    "work_type",
    "doi",
    "match_type",
]


def api_get(path, params=None):
    params = dict(params or {})
    params["mailto"] = MAILTO
    query = urllib.parse.urlencode(params, safe=":,|*")
    url = f"{API_BASE}{path}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "RushResearchDashboard/1.0"})
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    return {"error": str(last_error), "url": url}


def normalize_openalex_id(value):
    value = (value or "").strip()
    if not value:
        return ""
    return value if value.startswith("https://openalex.org/") else f"https://openalex.org/{value}"


def short_openalex_id(value):
    return normalize_openalex_id(value).replace("https://openalex.org/", "")


def has_rush_affiliation(authorships):
    for authorship in authorships or []:
        for inst in authorship.get("institutions") or []:
            inst_id = inst.get("id") or ""
            inst_short = inst_id.replace("https://openalex.org/", "")
            name = (inst.get("display_name") or "").lower()
            lineage = set(inst.get("lineage") or [])
            if inst_id in RUSH_INST_URLS or inst_short in RUSH_INST_IDS or lineage & RUSH_INST_URLS:
                return True
            if "rush" in name:
                return True
        for affiliation in authorship.get("affiliations") or []:
            raw = (affiliation.get("raw_affiliation_string") or "").lower()
            if "rush" in raw:
                return True
            inst_ids = set(affiliation.get("institution_ids") or [])
            if inst_ids & RUSH_INST_URLS:
                return True
        for raw in authorship.get("raw_affiliation_strings") or []:
            if "rush" in raw.lower():
                return True
    return False


def find_faculty_authorship(work, author_id):
    author_url = normalize_openalex_id(author_id)
    for authorship in work.get("authorships") or []:
        if normalize_openalex_id(authorship.get("author", {}).get("id")) == author_url:
            return authorship
    return None


def classify_position(work, authorship):
    if not authorship:
        return "ambiguous"
    authorships = work.get("authorships") or []
    position = (authorship.get("author_position") or "").lower()
    if len(authorships) == 1:
        return "single"
    if position in {"first", "middle", "last"}:
        return position
    return "ambiguous"


def fetch_recent_works(author_id, max_pages=None):
    works = []
    cursor = "*"
    pages = 0
    author_short = short_openalex_id(author_id)
    while cursor:
        data = api_get("/works", {
            "filter": f"authorships.author.id:{author_short},publication_year:{YEAR_FILTER}",
            "per_page": "200",
            "cursor": cursor,
            "select": "id,doi,display_name,publication_year,cited_by_count,type,authorships",
        })
        if "error" in data:
            raise RuntimeError(data["error"])
        works.extend(data.get("results") or [])
        pages += 1
        cursor = data.get("meta", {}).get("next_cursor")
        if not data.get("results") or (max_pages and pages >= max_pages):
            break
        time.sleep(RATE_LIMIT_DELAY)
    return works


def load_rows():
    with CSV_PATH.open(newline="") as f:
        reader = csv.DictReader(f)
        return list(reader), list(reader.fieldnames or [])


def write_rows(rows, fieldnames):
    for field in SUMMARY_FIELDS:
        if field not in fieldnames:
            fieldnames.append(field)
    with CSV_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_work_audit(work_rows):
    with WORK_AUDIT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=WORK_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(work_rows)


def choose_sample(rows, sample_size):
    candidates = [r for r in rows if r.get("openalex_id")]
    candidates.sort(key=lambda r: int(float(r.get("rush_works_5yr") or 0)), reverse=True)
    picked = []
    seen_depts = set()
    for row in candidates:
        dept = row.get("rush_dept") or ""
        if dept in seen_depts:
            continue
        picked.append(row)
        seen_depts.add(dept)
        if len(picked) >= sample_size:
            return picked
    for row in candidates:
        if row not in picked:
            picked.append(row)
        if len(picked) >= sample_size:
            break
    return picked


def zero_summary(row):
    for field in SUMMARY_FIELDS:
        row[field] = "0"
    row["leadership_ratio_5yr"] = "0.000"


def summarize_faculty(row, works):
    counts = Counter()
    work_rows = []
    author_id = row.get("openalex_id", "")
    for work in works:
        authorship = find_faculty_authorship(work, author_id)
        position = classify_position(work, authorship)
        rush_in_work = has_rush_affiliation(work.get("authorships") or [])
        faculty_rush = has_rush_affiliation([authorship] if authorship else [])
        is_corr = bool(authorship and authorship.get("is_corresponding"))

        counts[position] += 1
        if position == "middle":
            counts["contributing"] += 1
            if not rush_in_work:
                counts["external_contributor"] += 1
        if position == "last":
            counts["senior"] += 1
            if rush_in_work:
                counts["rush_affiliated_senior"] += 1
        if is_corr:
            counts["corresponding"] += 1

        work_rows.append({
            "faculty_name": row.get("name", ""),
            "rush_dept": row.get("rush_dept", ""),
            "college": row.get("college", ""),
            "openalex_author_id": normalize_openalex_id(author_id),
            "work_id": work.get("id", ""),
            "publication_year": work.get("publication_year", ""),
            "title": work.get("display_name", ""),
            "author_position": position,
            "is_corresponding": "true" if is_corr else "false",
            "cited_by_count": work.get("cited_by_count", 0),
            "rush_in_work": "true" if rush_in_work else "false",
            "faculty_rush_affiliation": "true" if faculty_rush else "false",
            "work_type": work.get("type", ""),
            "doi": work.get("doi", ""),
            "match_type": row.get("match_type", ""),
        })

    total = sum(counts[pos] for pos in ("first", "middle", "last", "single", "ambiguous"))
    senior = counts["senior"]
    row["recent_author_works_5yr"] = str(total)
    row["senior_author_5yr"] = str(senior)
    row["first_author_5yr"] = str(counts["first"])
    row["contributing_author_5yr"] = str(counts["contributing"])
    row["ambiguous_author_5yr"] = str(counts["single"] + counts["ambiguous"])
    row["leadership_ratio_5yr"] = f"{(senior / total) if total else 0:.3f}"
    row["rush_affiliated_senior_5yr"] = str(counts["rush_affiliated_senior"])
    row["external_contributor_5yr"] = str(counts["external_contributor"])
    row["corresponding_author_5yr"] = str(counts["corresponding"])
    return work_rows, total, counts


def main():
    parser = argparse.ArgumentParser(description="Enrich Rush faculty data with OpenAlex authorship-position metrics.")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N eligible rows.")
    parser.add_argument("--sample-size", type=int, default=None, help="Process a high-volume, cross-department sample.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and summarize without writing CSV or audit files.")
    parser.add_argument("--max-pages", type=int, default=None, help="Debug option: limit pages fetched per faculty member.")
    args = parser.parse_args()

    rows, fieldnames = load_rows()
    for row in rows:
        zero_summary(row)

    eligible = [row for row in rows if row.get("openalex_id", "").strip()]
    if args.sample_size:
        targets = choose_sample(rows, args.sample_size)
    else:
        targets = eligible[:args.limit] if args.limit else eligible

    print("Rush Faculty Authorship Enrichment")
    print(f"  CSV: {CSV_PATH}")
    print(f"  Eligible OpenAlex profiles: {len(eligible)}")
    print(f"  Processing: {len(targets)}")
    print(f"  Dry run: {args.dry_run}")

    all_work_rows = []
    failures = []
    totals = Counter()

    target_ids = {id(row) for row in targets}
    for idx, row in enumerate(rows, start=1):
        if id(row) not in target_ids:
            continue
        name = row.get("name", "")
        author_id = row.get("openalex_id", "")
        try:
            works = fetch_recent_works(author_id, max_pages=args.max_pages)
            work_rows, total, counts = summarize_faculty(row, works)
            all_work_rows.extend(work_rows)
            totals.update(counts)
            totals["faculty_processed"] += 1
            totals["works_processed"] += total
            print(
                f"  {totals['faculty_processed']:>4}/{len(targets)} {name}: "
                f"total={total}, last={counts['senior']}, middle={counts['contributing']}, "
                f"external_middle={counts['external_contributor']}"
            )
            time.sleep(RATE_LIMIT_DELAY)
        except Exception as exc:
            failures.append({"name": name, "openalex_id": author_id, "error": str(exc)})
            print(f"  ERROR {name}: {exc}", file=sys.stderr)

    report = {
        "timestamp": datetime.now().isoformat(),
        "year_filter": YEAR_FILTER,
        "eligible_profiles": len(eligible),
        "processed_profiles": int(totals["faculty_processed"]),
        "work_rows": len(all_work_rows),
        "position_totals": {
            "first": int(totals["first"]),
            "middle": int(totals["middle"]),
            "last": int(totals["last"]),
            "single": int(totals["single"]),
            "ambiguous": int(totals["ambiguous"]),
        },
        "senior_author_works": int(totals["senior"]),
        "external_contributor_works": int(totals["external_contributor"]),
        "failures": failures,
    }

    if not args.dry_run:
        write_rows(rows, fieldnames)
        write_work_audit(all_work_rows)
        with REPORT_PATH.open("w") as f:
            json.dump(report, f, indent=2)
        print(f"\n  Updated: {CSV_PATH}")
        print(f"  Work audit: {WORK_AUDIT_PATH}")
        print(f"  Report: {REPORT_PATH}")
    else:
        print("\nDry run report:")
        print(json.dumps(report, indent=2))

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
