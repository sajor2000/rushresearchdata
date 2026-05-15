#!/usr/bin/env python3
"""Regenerate the embedded RAW data block in index.html from the faculty CSV."""

import csv
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "data" / "rush_researcher_h_index.csv"
INDEX_PATH = REPO_ROOT / "index.html"


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
            "dept": row.get("rush_dept", ""),
            "college": row.get("college", ""),
            "orcid": row.get("orcid", ""),
            "mt": row.get("match_type", ""),
        }
        for row in rows
    ]


def main():
    raw_rows = build_raw_rows()
    html = INDEX_PATH.read_text()
    raw_json = json.dumps(raw_rows, ensure_ascii=False, separators=(",", ": "))
    next_html, count = re.subn(
        r"const RAW = \[.*?\];\n\n// =============================================\n// CONSTANTS",
        f"const RAW = {raw_json};\n\n// =============================================\n// CONSTANTS",
        html,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("Could not replace RAW data block in index.html")
    INDEX_PATH.write_text(next_html)
    print(f"Updated RAW data block with {len(raw_rows)} faculty rows.")


if __name__ == "__main__":
    main()
