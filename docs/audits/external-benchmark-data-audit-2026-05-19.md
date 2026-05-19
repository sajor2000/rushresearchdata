---
title: "External benchmark data audit"
date: 2026-05-19
status: scaffold_ready_missing_external_imports
---

# External Benchmark Data Audit

## Summary

The external benchmark layer is implemented as a CSV-first import scaffold. The dashboard can now display identity-review caveats, Altmetric/attention rows, external funding benchmark rows, and BRIMR category rows without changing existing OpenAlex h-index, citation, authorship, or NIH RePORTER strategy metrics.

Current state:

- Identity override rows: 1
- Identity review queue rows: 1
- Imported Altmetric rows: 0
- Imported external funding benchmark rows: 0
- Imported BRIMR rows: 0
- External benchmark audit blockers: 0
- External benchmark review caveats: 3

## Review Caveats

The three review caveats are expected for V1 because source exports have not yet been populated:

- `work_altmetrics.csv` has headers only.
- `external_funding_benchmarks.csv` has headers only.
- `brimr_department_rankings.csv` has headers only.

These are not interpreted as zero attention or zero funding. They are missing imported source rows.

## Safety Checks

The audit verifies:

- duplicate identity override keys.
- duplicate DOI/work/source Altmetric keys.
- duplicate external funding benchmark keys.
- duplicate BRIMR category keys.
- Altmetric DOI/OpenAlex work joins to `faculty_authorship_works.csv`.
- required source URLs for populated external funding and BRIMR rows.
- nonnegative numeric values for attention and funding fields.
- generated report counts reconcile to generated CSV summaries.

## Interpretation Boundaries

Altmetric/attention rows should be described as visibility or translation reach, not research quality. BRIMR and external funding files provide strategy context by source, year, organization, and category; they should not be forced into Rush department labels unless a documented crosswalk exists.

The Carlos A. Q. Santos split-profile issue is visible through `data/faculty_identity_overrides.csv` and `data/identity_review_queue.csv`. His OpenAlex metrics remain based on the current primary Rush-linked profile.
