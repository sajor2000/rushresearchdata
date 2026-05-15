#!/usr/bin/env python3
"""Audit top-200 h-index and department assignments.

H-index is checked against the current OpenAlex author record for the exact
OpenAlex author ID in the faculty CSV. Department is checked against the public
Rush University faculty directory, discovered with Tavily and scraped here for
repeatability.
"""

import csv
import html
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
SUMMARY_CSV = DATA_DIR / "rush_researcher_h_index.csv"
AUDIT_CSV = DATA_DIR / "top200_hindex_dept_audit.csv"
AUDIT_REPORT = DATA_DIR / "top200_hindex_dept_audit.json"

RUSH_FACULTY_URL = "https://www.rushu.rush.edu/faculty"
OPENALEX_API = "https://api.openalex.org"
MAILTO = "jcr@rush.edu"
TOP_N = 200

DEPT_LABEL_MAP = {
    "Anatomy and Cell Biology": "Anatomy & Cell Biology",
    "Cardiovascular and Thoracic Surgery": "Cardiovascular & Thoracic Surgery",
    "Community, Systems and Mental Health Nursing": "College of Nursing",
    "Diagnostic Radiology and Nuclear Medicine": "Diagnostic Radiology & Nuclear Medicine",
    "Family and Preventive Medicine": "Family & Preventive Medicine",
    "Microbial Pathogens and Immunity": "Microbial Pathogens & Immunity",
    "Obstetrics and Gynecology": "Obstetrics & Gynecology",
    "Otorhinolaryngology": "Otorhinolaryngology - Head & Neck Surgery",
    "Otorhinolaryngology - Head and Neck Surgery": "Otorhinolaryngology - Head & Neck Surgery",
    "Physical Medicine and Rehabilitation": "Physical Medicine & Rehabilitation",
    "Psychiatry and Behavioral Sciences": "Psychiatry & Behavioral Sciences",
}


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


def normalize_text(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_name(value):
    value = normalize_text(value).lower()
    value = re.sub(r"\b(md|phd|scd|do|ms|mph|rn|aprn|facs|faans|bcpps|fpmrs)\b", " ", value)
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_dept(value):
    value = normalize_text(value)
    value = re.sub(r"^Department of\s+", "", value)
    return DEPT_LABEL_MAP.get(value, value)


def get_url(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": "RushResearchDashboardAudit/1.0"})
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(str(last_error))


def scrape_rush_directory():
    records = []
    for page in range(85):
        url = RUSH_FACULTY_URL if page == 0 else f"{RUSH_FACULTY_URL}?page={page}"
        soup = BeautifulSoup(get_url(url), "html.parser")
        cards = soup.select(".faculty-card")
        for card in cards:
            link = card.select_one(".faculty-card__title a")
            if not link:
                continue
            name = normalize_text(link.get_text(" ", strip=True))
            href = link.get("href") or ""
            dept = card.select_one("[data-field-name='field_department']")
            college = card.select_one("[data-field-name='field_college']")
            title = card.select_one("[data-field-name='field_job_title']")
            records.append({
                "rush_name": name,
                "rush_name_key": normalize_name(name),
                "rush_profile_url": urllib.parse.urljoin(RUSH_FACULTY_URL, href),
                "rush_directory_dept": normalize_dept(dept.get_text(" ", strip=True) if dept else ""),
                "rush_directory_college": normalize_text(college.get_text(" ", strip=True) if college else ""),
                "rush_directory_title": normalize_text(title.get_text(" ", strip=True) if title else ""),
            })
        time.sleep(0.05)
    return records


def find_directory_match(row, directory_by_name, directory_records):
    name_key = normalize_name(row["name"])
    exact = directory_by_name.get(name_key) or []
    if len(exact) == 1:
        return exact[0], "exact_name", 1.0
    if len(exact) > 1:
        same_dept = [rec for rec in exact if rec["rush_directory_dept"] == row["rush_dept"]]
        if len(same_dept) == 1:
            return same_dept[0], "exact_name_same_dept", 1.0
        return exact[0], "ambiguous_exact_name", 1.0

    best = None
    best_score = 0.0
    for rec in directory_records:
        score = SequenceMatcher(None, name_key, rec["rush_name_key"]).ratio()
        if score > best_score:
            best = rec
            best_score = score
    if best and best_score >= 0.94:
        return best, "fuzzy_name", best_score
    return None, "not_found", best_score


def openalex_author(author_id):
    if not author_id:
        return {}
    short_id = author_id.replace("https://openalex.org/", "")
    params = urllib.parse.urlencode({"mailto": MAILTO})
    return json.loads(get_url(f"{OPENALEX_API}/authors/{short_id}?{params}"))


def main():
    summary = read_csv(SUMMARY_CSV)
    top_rows = sorted(summary, key=lambda row: int_field(row, "h_index"), reverse=True)[:TOP_N]
    directory_records = scrape_rush_directory()
    directory_by_name = {}
    for rec in directory_records:
        directory_by_name.setdefault(rec["rush_name_key"], []).append(rec)

    audit_rows = []
    h_mismatches = 0
    dept_mismatches = 0
    missing_directory = 0
    for rank, row in enumerate(top_rows, start=1):
        author = openalex_author(row.get("openalex_id", ""))
        stats = author.get("summary_stats") or {}
        openalex_h = stats.get("h_index", "")
        h_status = "match"
        if openalex_h != "" and int_field(row, "h_index") != int(openalex_h):
            h_status = "mismatch"
            h_mismatches += 1

        match, match_type, match_score = find_directory_match(row, directory_by_name, directory_records)
        if match:
            rush_dept = match["rush_directory_dept"]
            if not rush_dept:
                dept_status = "no_directory_dept"
            else:
                dept_status = "match" if rush_dept == row["rush_dept"] else "mismatch"
            if dept_status == "mismatch":
                dept_mismatches += 1
        else:
            rush_dept = ""
            dept_status = "not_found"
            missing_directory += 1
            match = {}

        audit_rows.append({
            "rank": rank,
            "name": row["name"],
            "csv_h_index": row.get("h_index", ""),
            "openalex_h_index": openalex_h,
            "h_index_status": h_status,
            "csv_dept": row.get("rush_dept", ""),
            "rush_directory_dept": rush_dept,
            "dept_status": dept_status,
            "directory_match_type": match_type,
            "directory_match_score": f"{match_score:.3f}",
            "rush_directory_name": match.get("rush_name", ""),
            "rush_directory_title": match.get("rush_directory_title", ""),
            "rush_directory_college": match.get("rush_directory_college", ""),
            "evidence_url": match.get("rush_profile_url", ""),
            "openalex_id": row.get("openalex_id", ""),
        })
        time.sleep(0.05)

    fieldnames = list(audit_rows[0].keys())
    write_csv(AUDIT_CSV, audit_rows, fieldnames)
    report = {
        "timestamp": datetime.now().isoformat(),
        "scope": f"top {TOP_N} by CSV h_index",
        "h_index_source": "OpenAlex author summary_stats.h_index by exact openalex_id",
        "department_source": "Rush University public faculty directory; directory was discovered with Tavily MCP and scraped for repeatability",
        "rush_directory_records": len(directory_records),
        "top_rows_checked": len(audit_rows),
        "h_index_mismatches": h_mismatches,
        "department_mismatches": dept_mismatches,
        "missing_directory_matches": missing_directory,
        "outputs": {"audit_csv": str(AUDIT_CSV.relative_to(REPO_ROOT))},
    }
    with AUDIT_REPORT.open("w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    if h_mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
