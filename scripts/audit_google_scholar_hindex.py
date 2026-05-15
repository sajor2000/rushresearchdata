#!/usr/bin/env python3
"""Optional Google Scholar h-index comparison for top faculty.

Google Scholar does not provide an official public API. This script uses the
unofficial `scholarly` package as a secondary audit only; it never updates the
dashboard source data. OpenAlex remains the primary h-index source because the
dashboard stores exact OpenAlex author IDs for attribution.
"""

import argparse
import csv
import json
import multiprocessing as mp
import re
import time
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

try:
    from scholarly import scholarly
except Exception as exc:  # pragma: no cover - dependency/runtime guard
    scholarly = None
    SCHOLARLY_IMPORT_ERROR = str(exc)
else:
    SCHOLARLY_IMPORT_ERROR = ""

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
SUMMARY_CSV = DATA_DIR / "rush_researcher_h_index.csv"
AUDIT_CSV = DATA_DIR / "google_scholar_hindex_audit.csv"
AUDIT_REPORT = DATA_DIR / "google_scholar_hindex_audit.json"


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


def normalize_name(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"\b(md|phd|scd|do|ms|mph|mba|rn|facs|faans)\b", " ", value)
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def name_score(left, right):
    return SequenceMatcher(None, normalize_name(left), normalize_name(right)).ratio()


def candidate_confidence(row, candidate):
    score = name_score(row["name"], candidate.get("name", ""))
    affiliation = (candidate.get("affiliation") or "").lower()
    email_domain = (candidate.get("email_domain") or "").lower()
    rush_signal = "rush" in affiliation or "rush" in email_domain
    if score >= 0.98 and rush_signal:
        return "high", score
    if score >= 0.98:
        return "name_only", score
    if score >= 0.92 and rush_signal:
        return "probable", score
    return "low", score


def search_scholar_candidate(row, max_candidates=5):
    if scholarly is None:
        return None, "scholarly_import_error", 0.0

    queries = [f"{row['name']} Rush", row["name"]]
    seen = set()
    best = None
    best_confidence = "not_found"
    best_score = 0.0
    confidence_rank = {"high": 4, "probable": 3, "name_only": 2, "low": 1, "not_found": 0}

    for query in queries:
        try:
            results = scholarly.search_author(query)
            for _ in range(max_candidates):
                try:
                    candidate = next(results)
                except StopIteration:
                    break
                scholar_id = candidate.get("scholar_id") or candidate.get("url_picture") or candidate.get("name", "")
                if scholar_id in seen:
                    continue
                seen.add(scholar_id)
                confidence, score = candidate_confidence(row, candidate)
                if confidence_rank[confidence] > confidence_rank[best_confidence] or (
                    confidence_rank[confidence] == confidence_rank[best_confidence] and score > best_score
                ):
                    best = candidate
                    best_confidence = confidence
                    best_score = score
        except Exception as exc:
            return best, f"search_error: {exc}", best_score

    if best is None:
        return None, "not_found", 0.0
    return best, best_confidence, best_score


def fill_candidate(candidate):
    if not candidate or scholarly is None:
        return candidate or {}
    try:
        return scholarly.fill(candidate, sections=[], publication_limit=0)
    except Exception:
        return candidate


def compact_candidate(candidate):
    candidate = candidate or {}
    return {
        "name": candidate.get("name", ""),
        "affiliation": candidate.get("affiliation", ""),
        "email_domain": candidate.get("email_domain", ""),
        "scholar_id": candidate.get("scholar_id", ""),
        "hindex": candidate.get("hindex", ""),
    }


def search_worker(row, max_candidates, queue):
    try:
        candidate, status, score = search_scholar_candidate(row, max_candidates)
        if status in {"high", "probable", "name_only"}:
            candidate = fill_candidate(candidate)
        queue.put({"candidate": compact_candidate(candidate), "status": status, "score": score})
    except Exception as exc:
        queue.put({"candidate": {}, "status": f"search_error: {exc}", "score": 0.0})


def search_with_timeout(row, max_candidates, timeout):
    queue = mp.Queue()
    process = mp.Process(target=search_worker, args=(row, max_candidates, queue))
    process.start()
    process.join(timeout)
    if process.is_alive():
        process.terminate()
        process.join(2)
        return {}, "timeout", 0.0
    if queue.empty():
        return {}, "no_worker_result", 0.0
    result = queue.get()
    return result["candidate"], result["status"], result["score"]


def main():
    parser = argparse.ArgumentParser(description="Compare top faculty h-index with Google Scholar via scholarly.")
    parser.add_argument("--limit", type=int, default=200, help="Number of top h-index faculty to check.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between Google Scholar searches.")
    parser.add_argument("--max-candidates", type=int, default=5, help="Author candidates to inspect per query.")
    parser.add_argument("--timeout", type=float, default=8.0, help="Per-author timeout in seconds.")
    args = parser.parse_args()

    rows = sorted(read_csv(SUMMARY_CSV), key=lambda row: int_field(row, "h_index"), reverse=True)[:args.limit]
    audit_rows = []
    for rank, row in enumerate(rows, start=1):
        candidate, status, score = search_with_timeout(row, args.max_candidates, args.timeout)
        scholar_h = candidate.get("hindex", "")
        h_delta = ""
        if isinstance(scholar_h, int):
            h_delta = scholar_h - int_field(row, "h_index")
        audit_rows.append({
            "rank": rank,
            "name": row["name"],
            "csv_openalex_h_index": row.get("h_index", ""),
            "google_scholar_h_index": scholar_h,
            "h_index_delta_scholar_minus_openalex": h_delta,
            "scholar_match_status": status,
            "scholar_match_score": f"{score:.3f}",
            "scholar_name": candidate.get("name", ""),
            "scholar_affiliation": candidate.get("affiliation", ""),
            "scholar_email_domain": candidate.get("email_domain", ""),
            "scholar_id": candidate.get("scholar_id", ""),
            "openalex_id": row.get("openalex_id", ""),
        })
        if rank % 25 == 0:
            print(f"Checked {rank}/{len(rows)}")
        if args.delay:
            time.sleep(args.delay)

    fieldnames = list(audit_rows[0].keys()) if audit_rows else [
        "rank",
        "name",
        "csv_openalex_h_index",
        "google_scholar_h_index",
        "h_index_delta_scholar_minus_openalex",
        "scholar_match_status",
        "scholar_match_score",
        "scholar_name",
        "scholar_affiliation",
        "scholar_email_domain",
        "scholar_id",
        "openalex_id",
    ]
    write_csv(AUDIT_CSV, audit_rows, fieldnames)

    status_counts = {}
    for audit_row in audit_rows:
        status_counts[audit_row["scholar_match_status"]] = status_counts.get(audit_row["scholar_match_status"], 0) + 1
    usable_matches = sum(status_counts.get(status, 0) for status in ("high", "probable"))
    report = {
        "timestamp": datetime.now().isoformat(),
        "scope": f"top {len(rows)} by CSV/OpenAlex h_index",
        "source_role": "Google Scholar via unofficial scholarly package, secondary comparison only",
        "primary_h_index_source": "OpenAlex author summary_stats.h_index by exact openalex_id",
        "scholarly_available": scholarly is not None,
        "scholarly_import_error": SCHOLARLY_IMPORT_ERROR,
        "status_counts": status_counts,
        "usable_high_or_probable_matches": usable_matches,
        "outputs": {"audit_csv": str(AUDIT_CSV.relative_to(REPO_ROOT))},
        "caveat": "Google Scholar has no official public API; search results can be blocked, incomplete, or ambiguous.",
    }
    with AUDIT_REPORT.open("w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
