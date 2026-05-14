#!/usr/bin/env python3
"""
Rush Faculty OpenAlex Re-Matching Pipeline

Processes faculty in phases:
  Phase 1: Recover unmatched (match_type=none) — query OpenAlex by name + Rush affiliation
  Phase 2: Verify api_search entries — check institution affiliation, flag wrong-person
  Phase 3: Re-check corrected_wrong_person — attempt to find correct profiles

Outputs:
  - data/rush_researcher_h_index.csv (updated in place)
  - data/rematch_log.csv (audit trail of all changes)
  - data/rematch_report.json (summary metrics)

Usage:
  python3 scripts/rematch.py [--phase 1|2|3|all] [--dry-run] [--limit N]
"""

import csv
import json
import sys
import time
import urllib.request
import urllib.parse
import argparse
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "data" / "rush_researcher_h_index.csv"
LOG_PATH = REPO_ROOT / "data" / "rematch_log.csv"
REPORT_PATH = REPO_ROOT / "data" / "rematch_report.json"

RUSH_INST_IDS = ["I1285301757", "I49886154"]  # Rush UMC, Rush University
API_BASE = "https://api.openalex.org"
MAILTO = "jcr@rush.edu"
RATE_LIMIT_DELAY = 0.12  # ~8 req/sec, well under OpenAlex limit


def api_get(path, params=None):
    params = params or {}
    params["mailto"] = MAILTO
    qs = urllib.parse.urlencode(params, safe=":,|")
    url = f"{API_BASE}{path}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "RushResearchPipeline/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def search_author(name, per_page=5):
    return api_get("/authors", {"search": name, "per_page": str(per_page)})


def get_author(author_id):
    oid = author_id.replace("https://openalex.org/", "")
    return api_get(f"/authors/{oid}")


def get_rush_5yr(author_id):
    oid = author_id.replace("https://openalex.org/", "")
    best = 0
    for iid in RUSH_INST_IDS:
        data = api_get("/works", {
            "filter": f"author.id:{oid},institutions.id:{iid},publication_year:2021-2026",
            "per_page": "1",
        })
        if "error" not in data:
            c = data.get("meta", {}).get("count", 0)
            if c > best:
                best = c
    return best


def get_2yr_citedness(author_id):
    oid = author_id.replace("https://openalex.org/", "")
    data = api_get("/works", {
        "filter": f"author.id:{oid},publication_year:2024-2025",
        "per_page": "200",
        "select": "cited_by_count",
    })
    if "error" in data:
        return 0.0
    works = data.get("results", [])
    if not works:
        return 0.0
    return sum(w.get("cited_by_count", 0) for w in works) / len(works)


def is_rush_affiliated(author_data):
    insts = author_data.get("last_known_institutions") or []
    for i in insts:
        name = (i.get("display_name") or "").lower()
        iid = (i.get("id") or "")
        if "rush" in name or iid in [f"https://openalex.org/{x}" for x in RUSH_INST_IDS]:
            return True
    return False


def name_similarity(csv_name, oa_name):
    """Simple name matching score: 0-1"""
    def normalize(n):
        return set(n.lower().replace(".", "").replace(",", "").replace("-", " ").split())
    csv_parts = normalize(csv_name)
    oa_parts = normalize(oa_name)
    if not csv_parts or not oa_parts:
        return 0.0
    overlap = csv_parts & oa_parts
    return len(overlap) / max(len(csv_parts), len(oa_parts))


def find_best_match(name, dept, college, existing_orcid=""):
    """Search OpenAlex and return the best matching author profile, or None."""
    results = search_author(name, per_page=10)
    if "error" in results:
        return None

    candidates = []
    for r in results.get("results", []):
        stats = r.get("summary_stats") or {}
        h = stats.get("h_index", 0)
        works = r.get("works_count", 0)

        rush_aff = is_rush_affiliated(r)
        nsim = name_similarity(name, r.get("display_name", ""))
        orcid_match = False
        if existing_orcid and r.get("orcid"):
            orcid_match = existing_orcid in r["orcid"]

        score = 0.0
        if orcid_match:
            score += 50
        if rush_aff:
            score += 30
        score += nsim * 15
        if h > 0:
            score += min(h, 5)

        if nsim < 0.4 and not orcid_match:
            continue

        candidates.append({
            "id": r["id"],
            "display_name": r.get("display_name", ""),
            "h_index": h,
            "i10_index": stats.get("i10_index", 0),
            "works_count": works,
            "cited_by_count": r.get("cited_by_count", 0),
            "orcid": (r.get("orcid") or "").replace("https://orcid.org/", ""),
            "rush_affiliated": rush_aff,
            "name_similarity": nsim,
            "score": score,
            "2yr_citedness": stats.get("2yr_mean_citedness", 0),
        })

    if not candidates:
        return None

    candidates.sort(key=lambda c: -c["score"])
    best = candidates[0]

    if best["score"] < 30 and not best["rush_affiliated"]:
        return None

    return best


def load_csv():
    with open(CSV_PATH, "r") as f:
        reader = csv.DictReader(f)
        return list(reader), reader.fieldnames


def save_csv(rows, fieldnames):
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def append_log(entries):
    exists = LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "timestamp", "phase", "name", "dept", "action",
            "old_h", "new_h", "old_r5", "new_r5",
            "old_match_type", "new_match_type", "openalex_id", "notes",
        ])
        if not exists:
            writer.writeheader()
        writer.writerows(entries)


def phase1_recover_unmatched(rows, fieldnames, dry_run=False, limit=None):
    """Try to find OpenAlex profiles for faculty with match_type=none."""
    unmatched = [(i, r) for i, r in enumerate(rows) if r["match_type"].strip() == "none"]
    print(f"\n{'='*60}")
    print(f"PHASE 1: Recover Unmatched ({len(unmatched)} faculty)")
    print(f"{'='*60}")

    if limit:
        unmatched = unmatched[:limit]
        print(f"  (limited to {limit})")

    recovered = 0
    not_found = 0
    log_entries = []

    for idx, (row_i, row) in enumerate(unmatched):
        name = row["name"]
        dept = row["rush_dept"]
        orcid = row.get("orcid", "").strip()

        if idx % 50 == 0 and idx > 0:
            print(f"  Progress: {idx}/{len(unmatched)} ({recovered} recovered)")

        match = find_best_match(name, dept, row["college"], orcid)
        time.sleep(RATE_LIMIT_DELAY)

        if match and match["rush_affiliated"]:
            r5 = get_rush_5yr(match["id"])
            time.sleep(RATE_LIMIT_DELAY)

            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "phase": "1-recover",
                "name": name,
                "dept": dept,
                "action": "recovered",
                "old_h": row["h_index"],
                "new_h": str(match["h_index"]),
                "old_r5": row["rush_works_5yr"],
                "new_r5": str(r5),
                "old_match_type": row["match_type"],
                "new_match_type": f"rematch_p1(score={match['score']:.0f})",
                "openalex_id": match["id"],
                "notes": f"name_sim={match['name_similarity']:.2f}, oa_name={match['display_name']}",
            }
            log_entries.append(log_entry)

            if not dry_run:
                rows[row_i]["h_index"] = str(match["h_index"])
                rows[row_i]["i10_index"] = str(match["i10_index"])
                rows[row_i]["works_count"] = str(match["works_count"])
                rows[row_i]["cited_by_count"] = str(match["cited_by_count"])
                rows[row_i]["rush_works_5yr"] = str(r5)
                rows[row_i]["two_year_mean_citedness"] = str(match["2yr_citedness"])
                rows[row_i]["match_type"] = f"rematch_p1(score={match['score']:.0f})"
                rows[row_i]["openalex_id"] = match["id"]
                if match["orcid"] and not rows[row_i]["orcid"].strip():
                    rows[row_i]["orcid"] = match["orcid"]

            recovered += 1
            print(f"  + {name} -> h={match['h_index']}, r5={r5} ({match['display_name']})")
        else:
            not_found += 1

    append_log(log_entries)
    print(f"\n  Phase 1 complete: {recovered} recovered, {not_found} not found")
    return recovered, not_found


def phase2_verify_api_search(rows, fieldnames, dry_run=False, limit=None):
    """Verify api_search matches are correct — check Rush affiliation."""
    api_rows = [(i, r) for i, r in enumerate(rows) if r["match_type"].strip() == "api_search"]
    print(f"\n{'='*60}")
    print(f"PHASE 2: Verify API Search ({len(api_rows)} entries)")
    print(f"{'='*60}")

    if limit:
        api_rows = api_rows[:limit]

    verified = 0
    flagged = 0
    log_entries = []

    for idx, (row_i, row) in enumerate(api_rows):
        name = row["name"]
        oaid = row.get("openalex_id", "").strip()
        h = int(row["h_index"])
        r5 = int(row["rush_works_5yr"])

        if not oaid:
            continue

        author = get_author(oaid)
        time.sleep(RATE_LIMIT_DELAY)

        if "error" in author:
            continue

        rush_aff = is_rush_affiliated(author)
        nsim = name_similarity(name, author.get("display_name", ""))

        is_suspect = False
        notes = []

        if not rush_aff:
            is_suspect = True
            notes.append("no_rush_affiliation")
        if nsim < 0.5:
            is_suspect = True
            notes.append(f"name_mismatch(sim={nsim:.2f},oa={author.get('display_name','')})")
        if h > 30 and r5 == 0:
            is_suspect = True
            notes.append("high_h_zero_r5")

        if is_suspect:
            flagged += 1
            action = "flagged_wrong_person"
            print(f"  ! {name}: h={h}, r5={r5} -> FLAGGED ({', '.join(notes)})")

            if not dry_run and not rush_aff:
                rows[row_i]["h_index"] = "0"
                rows[row_i]["i10_index"] = "0"
                rows[row_i]["works_count"] = "0"
                rows[row_i]["cited_by_count"] = "0"
                rows[row_i]["rush_works_5yr"] = "0"
                rows[row_i]["two_year_mean_citedness"] = "0"
                rows[row_i]["match_type"] = "api_search_wrong_person"
                rows[row_i]["openalex_id"] = ""
                rows[row_i]["orcid"] = ""
        else:
            verified += 1
            action = "verified"

        log_entries.append({
            "timestamp": datetime.now().isoformat(),
            "phase": "2-verify",
            "name": name,
            "dept": row["rush_dept"],
            "action": action,
            "old_h": row["h_index"],
            "new_h": rows[row_i]["h_index"] if not dry_run else row["h_index"],
            "old_r5": row["rush_works_5yr"],
            "new_r5": rows[row_i]["rush_works_5yr"] if not dry_run else row["rush_works_5yr"],
            "old_match_type": row["match_type"],
            "new_match_type": rows[row_i]["match_type"] if not dry_run else row["match_type"],
            "openalex_id": oaid,
            "notes": "; ".join(notes) if notes else "ok",
        })

    append_log(log_entries)
    print(f"\n  Phase 2 complete: {verified} verified, {flagged} flagged")
    return verified, flagged


def phase3_recheck_corrected(rows, fieldnames, dry_run=False, limit=None):
    """Re-check corrected_wrong_person entries for better matches."""
    corrected = [(i, r) for i, r in enumerate(rows)
                 if "corrected_wrong_person" in r["match_type"]
                 and int(r["h_index"]) == 0]
    print(f"\n{'='*60}")
    print(f"PHASE 3: Re-check Corrected ({len(corrected)} with h=0)")
    print(f"{'='*60}")

    if limit:
        corrected = corrected[:limit]

    fixed = 0
    still_zero = 0
    log_entries = []

    for row_i, row in corrected:
        name = row["name"]
        match = find_best_match(name, row["rush_dept"], row["college"])
        time.sleep(RATE_LIMIT_DELAY)

        if match and match["rush_affiliated"] and match["h_index"] > 0:
            r5 = get_rush_5yr(match["id"])
            time.sleep(RATE_LIMIT_DELAY)

            if not dry_run:
                rows[row_i]["h_index"] = str(match["h_index"])
                rows[row_i]["i10_index"] = str(match["i10_index"])
                rows[row_i]["works_count"] = str(match["works_count"])
                rows[row_i]["cited_by_count"] = str(match["cited_by_count"])
                rows[row_i]["rush_works_5yr"] = str(r5)
                rows[row_i]["two_year_mean_citedness"] = str(match["2yr_citedness"])
                rows[row_i]["match_type"] = f"rematch_p3(score={match['score']:.0f})"
                rows[row_i]["openalex_id"] = match["id"]
                if match["orcid"]:
                    rows[row_i]["orcid"] = match["orcid"]

            fixed += 1
            print(f"  + {name} -> h={match['h_index']}, r5={r5}")

            log_entries.append({
                "timestamp": datetime.now().isoformat(),
                "phase": "3-recheck",
                "name": name,
                "dept": row["rush_dept"],
                "action": "recovered",
                "old_h": row["h_index"],
                "new_h": str(match["h_index"]),
                "old_r5": row["rush_works_5yr"],
                "new_r5": str(r5),
                "old_match_type": row["match_type"],
                "new_match_type": f"rematch_p3(score={match['score']:.0f})",
                "openalex_id": match["id"],
                "notes": f"oa_name={match['display_name']}",
            })
        else:
            still_zero += 1

    append_log(log_entries)
    print(f"\n  Phase 3 complete: {fixed} recovered, {still_zero} still zero")
    return fixed, still_zero


def generate_report(rows, baseline, results):
    total = len(rows)
    h_pos = sum(1 for r in rows if int(r["h_index"]) > 0)
    r5_active = sum(1 for r in rows if int(r["rush_works_5yr"]) > 0)
    has_oaid = sum(1 for r in rows if r["openalex_id"].strip())

    report = {
        "timestamp": datetime.now().isoformat(),
        "baseline": baseline,
        "final": {
            "total_faculty": total,
            "h_positive": h_pos,
            "h_positive_pct": round(h_pos / total * 100, 1),
            "r5_active": r5_active,
            "r5_active_pct": round(r5_active / total * 100, 1),
            "has_openalex_id": has_oaid,
            "match_rate_pct": round(has_oaid / total * 100, 1),
        },
        "improvement": {
            "new_matches": h_pos - baseline["h_positive"],
            "match_rate_delta": round((has_oaid / total - baseline["has_openalex_id"] / baseline["total_faculty"]) * 100, 1),
        },
        "phase_results": results,
    }

    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  Faculty with h > 0:  {baseline['h_positive']} -> {h_pos} (+{h_pos - baseline['h_positive']})")
    print(f"  Match rate:          {baseline['has_openalex_id']}/{baseline['total_faculty']} -> {has_oaid}/{total}")
    print(f"  R5 active:           {baseline['r5_active']} -> {r5_active}")
    print(f"\n  Report: {REPORT_PATH}")
    print(f"  Log:    {LOG_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Rush Faculty OpenAlex Re-Matching Pipeline")
    parser.add_argument("--phase", choices=["1", "2", "3", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true", help="Don't modify CSV")
    parser.add_argument("--limit", type=int, default=None, help="Max entries per phase")
    args = parser.parse_args()

    rows, fieldnames = load_csv()

    total = len(rows)
    baseline = {
        "total_faculty": total,
        "h_positive": sum(1 for r in rows if int(r["h_index"]) > 0),
        "r5_active": sum(1 for r in rows if int(r["rush_works_5yr"]) > 0),
        "has_openalex_id": sum(1 for r in rows if r["openalex_id"].strip()),
    }

    print(f"Rush Faculty Re-Matching Pipeline")
    print(f"  CSV: {CSV_PATH}")
    print(f"  Total: {total}, h>0: {baseline['h_positive']}, matched: {baseline['has_openalex_id']}")
    print(f"  Phase: {args.phase}, Dry run: {args.dry_run}, Limit: {args.limit or 'none'}")

    if LOG_PATH.exists():
        LOG_PATH.unlink()

    results = {}

    if args.phase in ("1", "all"):
        r, nf = phase1_recover_unmatched(rows, fieldnames, args.dry_run, args.limit)
        results["phase1"] = {"recovered": r, "not_found": nf}

    if args.phase in ("2", "all"):
        v, f = phase2_verify_api_search(rows, fieldnames, args.dry_run, args.limit)
        results["phase2"] = {"verified": v, "flagged": f}

    if args.phase in ("3", "all"):
        f, sz = phase3_recheck_corrected(rows, fieldnames, args.dry_run, args.limit)
        results["phase3"] = {"recovered": f, "still_zero": sz}

    if not args.dry_run:
        save_csv(rows, fieldnames)
        print(f"\n  CSV updated: {CSV_PATH}")

    generate_report(rows, baseline, results)


if __name__ == "__main__":
    main()
