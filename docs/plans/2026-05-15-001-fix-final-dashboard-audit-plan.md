---
title: "fix: Final release audit for Rush research dashboard"
type: fix
status: completed
date: 2026-05-15
---

# Final Release Audit for Rush Research Dashboard

## Summary

Run a final release-readiness audit for the Rush research dashboard branch before merge. The audit covers data correctness, OpenAlex author attribution, h-index and department fact-checking, first/last author confidence, duplicate detection, scientific wording, visual quality, and PR evidence for the new authorship and strategy analytics.

The goal is not to add another major feature. The goal is to prove the current data and dashboard are clean enough to share, identify any remaining caveats plainly, and avoid making the dataset less reliable while adding the new senior/first-author and strategy metrics.

## Problem Frame

The dashboard now includes:

- Senior authorship and first-author metrics based on OpenAlex `authorships.author_position`.
- Faculty-work audit rows in `data/faculty_authorship_works.csv`.
- Strategy metrics for topics, team science, funding, NIH linkage, and department summaries.
- Top-200 h-index and department audit outputs.
- Optional Google Scholar comparison logic through `scholarly`.

These additions increase analytical value but also increase risk. The final audit must verify that:

- Faculty rows still attribute publications to the correct OpenAlex author IDs.
- First-author and last-author counts reconcile with work-level evidence.
- H-index and department values are not silently worsened by enrichment.
- Duplicate faculty, duplicate author IDs, and duplicate faculty-work rows are not introduced.
- Visuals make the new lens clear without overstating scientific meaning.
- Remaining review caveats are labeled as caveats, not hidden failures.

## Requirements

### R1. Reproducible Data Checkpoint

Re-run the relevant enrichment and audit scripts from the current branch, then review generated diffs before accepting them.

Verification:

- Generated audit JSON files report zero blocking issues.
- Any changed CSV or JSON output is explainable as source drift, deterministic regeneration, or an intentional correction.
- Line endings remain normalized according to `.gitattributes`.

### R2. Authorship Attribution and Confidence

Verify that the authorship lens attributes each faculty-work row to the intended faculty OpenAlex author ID and that first, last, middle, and ambiguous counts reconcile.

Verification:

- `data/authorship_quality_audit.json` reports:
  - zero duplicate normalized faculty names when exact duplicate identity would be unsafe.
  - zero duplicate OpenAlex author IDs.
  - zero duplicate faculty-author-work rows.
  - zero summary count mismatches.
  - zero leadership ratio mismatches.
- First-author plus middle-author plus last-author plus ambiguous rows equal the total fetched recent authorship rows.
- Lower-confidence faculty matches are preserved as review caveats, not treated as high-confidence proof.
- Multi-faculty same-work rows are documented as expected coauthorship, not deduplicated away.

### R3. H-Index and Department Fact Check

Verify h-index values and department labels for the top 200 faculty without replacing source-of-truth data with weaker secondary sources.

Verification:

- `data/top200_hindex_dept_audit.json` reports zero h-index mismatches against exact OpenAlex author IDs.
- `data/top200_hindex_dept_audit.json` reports zero department mismatches where Rush directory matches exist.
- Missing Rush directory matches are listed as caveats, not auto-corrected.
- Optional Google Scholar audit output is treated as secondary context only because Google Scholar does not provide an official public API and `scholarly` can be blocked or ambiguous.

### R4. Strategy Metrics Reconciliation

Verify that strategy dashboards reconcile to faculty-work data and NIH/OpenAlex source data.

Verification:

- `data/strategy_quality_audit.json` reports zero blocking issues.
- Department-level row counts reconcile to the generated strategy tables.
- OpenAlex topic and Field-Weighted Citation Impact missingness are quantified.
- NIH Reporter matching statuses are summarized and ambiguous/unmatched rows remain visible for review.

### R5. Scientific Accuracy and Wording

Audit dashboard language so the authorship lens is scientifically defensible.

Verification:

- Last authorship is described as a leadership proxy, not proof of study ownership.
- First authorship is described as an early-career or project-execution signal, not a universal leadership measure.
- Middle authorship is described as potentially valuable collaboration and contribution, not inappropriate authorship.
- Rush affiliation is described as evidence from work/authorship institution metadata, not proof that the study was performed at Rush.
- Google Scholar language clearly states the unofficial and incomplete nature of the comparison.

### R6. Visual and Interaction QA

Open the dashboard locally and inspect the analytics views on desktop and mobile.

Verification:

- Leadership Lens renders with senior-author and first-author toggle states.
- Strategy tab renders all core charts/tables.
- Top faculty, department, and strategy sections have no text overlap.
- Browser console has no runtime errors.
- Mobile layout preserves labels, tables, and controls without incoherent overlap.
- Screenshots or notes are captured as final audit evidence.

### R7. Merge-Ready Evidence

Produce a final evidence package that separates blockers, review caveats, and source limitations.

Verification:

- Final audit note summarizes exact audit files, counts, and caveats.
- PR or handoff summary lists data sources and limitations.
- Branch is clean except intentional audit documentation or regenerated outputs.
- No commit or push occurs unless explicitly requested after audit execution.

## Scope Boundaries

In scope:

- Running existing enrichment and audit scripts.
- Fixing clear bugs found by the audit.
- Correcting h-index or department values only when supported by high-confidence source evidence.
- Improving dashboard labels, caveats, and layout defects found during visual QA.
- Adding a final audit note if evidence needs a durable home.

Out of scope:

- Replacing OpenAlex as the primary authorship and h-index source.
- Auto-overwriting values from Google Scholar.
- Resolving every lower-confidence faculty identity match without manual evidence.
- Rebuilding the dashboard architecture.
- Making accusations about authorship appropriateness.
- Introducing new metrics during the final audit unless a missing metric is necessary to validate existing claims.

## Context and Current Evidence

Relevant files:

- `index.html`
- `data/rush_researcher_h_index.csv`
- `data/faculty_authorship_works.csv`
- `data/authorship_enrichment_report.json`
- `data/authorship_quality_audit.json`
- `data/authorship_quality_flags.csv`
- `data/strategy_quality_audit.json`
- `data/strategy_quality_flags.csv`
- `data/top200_hindex_dept_audit.json`
- `data/top200_hindex_dept_audit.csv`
- `data/google_scholar_hindex_audit.json`
- `data/google_scholar_hindex_audit.csv`
- `scripts/enrich_authorship.py`
- `scripts/audit_authorship_quality.py`
- `scripts/enrich_strategy_metrics.py`
- `scripts/audit_strategy_metrics.py`
- `scripts/audit_top200_hindex_dept.py`
- `scripts/audit_google_scholar_hindex.py`
- `scripts/update_dashboard_raw.py`

Current expected audit posture:

- Authorship audit should have zero blocking issues.
- Strategy audit should have zero blocking issues.
- Top-200 h-index and department audit should have zero mismatches where source matches exist.
- Google Scholar comparison may time out or fail and must not be treated as a primary source.
- Existing review caveats include lower-confidence faculty matches, Rush directory misses, OpenAlex missingness, and NIH ambiguous/unmatched records.

## Key Decisions

1. OpenAlex exact author IDs remain the primary source for h-index and authorship-role counts.
2. Rush public faculty directory remains the department check source where a reliable directory match exists.
3. Google Scholar is a secondary comparison only; it can flag possible manual-review targets but cannot overwrite the dataset automatically.
4. First-author and last-author counts are high-confidence only when OpenAlex provides explicit `author_position` values for the matched faculty author ID.
5. The final audit will classify findings into blockers and caveats.
6. Any live external data refresh must be diff-reviewed before commit because OpenAlex, NIH Reporter, Rush directory, and Google Scholar-adjacent results can drift.

## Open Questions

Resolved assumptions:

- Last author remains the primary senior-author proxy.
- First author is added as a parallel lens for early-career and execution-heavy research roles.
- Middle authorship is not treated as bad authorship.
- Google Scholar is not a primary data source.

Deferred decisions:

- Whether to manually resolve all lower-confidence faculty identity matches after this audit.
- Whether to expand top-200 department/h-index verification to every faculty row.
- Whether to publish a separate methodology page beyond dashboard notes.

## Implementation Units

### U1. Clean Regeneration Checkpoint

Purpose:

Confirm the current branch regenerates its derived data without unexplained drift.

Files:

- `scripts/enrich_authorship.py`
- `scripts/enrich_strategy_metrics.py`
- `scripts/update_dashboard_raw.py`
- `data/*.csv`
- `data/*.json`
- `index.html`

Actions:

- Capture a pre-audit `git status`.
- Run the existing generation scripts needed for authorship and strategy outputs.
- Review changed files before accepting them.
- Normalize generated CSV/JSON line endings if needed.

Verification:

- No unexpected file classes change.
- Data changes have a clear source or script explanation.
- Dashboard raw embedded data reflects current CSV/JSON outputs.

### U2. Authorship Attribution and Duplicate Audit

Purpose:

Prove the new authorship lens did not create author attribution errors or duplicate rows.

Files:

- `scripts/audit_authorship_quality.py`
- `data/authorship_quality_audit.json`
- `data/authorship_quality_flags.csv`
- `data/faculty_authorship_works.csv`
- `data/rush_researcher_h_index.csv`

Actions:

- Run the authorship quality audit.
- Inspect blocking counts, duplicate checks, reconciliation checks, and confidence counts.
- Sample first-author and last-author rows by opening the corresponding OpenAlex work records and checking the matched faculty author position.
- Confirm lower-confidence match rows are flagged and not silently promoted.

Verification:

- Duplicate OpenAlex author IDs: zero.
- Duplicate faculty-author-work rows: zero.
- Summary mismatches: zero.
- Leadership ratio mismatches: zero.
- First/last high-confidence count equals first/last rows with explicit OpenAlex author position.
- Any caveat rows are present in `data/authorship_quality_flags.csv`.

### U3. H-Index and Department Fact Check

Purpose:

Verify top-200 h-index and department values from source evidence.

Files:

- `scripts/audit_top200_hindex_dept.py`
- `scripts/audit_google_scholar_hindex.py`
- `data/top200_hindex_dept_audit.json`
- `data/top200_hindex_dept_audit.csv`
- `data/google_scholar_hindex_audit.json`
- `data/google_scholar_hindex_audit.csv`
- `data/rush_researcher_h_index.csv`

Actions:

- Run the top-200 audit with OpenAlex and Rush directory checks.
- Use Tavily or equivalent web search only for source lookup/confirmation where the script or directory lookup is unclear.
- Run optional Google Scholar comparison as a non-blocking secondary check if available.
- Inspect any h-index or department mismatch before changing source data.

Verification:

- Top-200 h-index mismatches: zero or individually resolved with source evidence.
- Top-200 department mismatches: zero where Rush directory matches exist, or individually resolved with source evidence.
- Missing directory matches are counted and listed.
- Google Scholar failures, timeouts, and ambiguous matches are documented as limitations.

### U4. Strategy Metrics Reconciliation

Purpose:

Verify the strategy dashboard metrics are internally consistent and source limitations are visible.

Files:

- `scripts/audit_strategy_metrics.py`
- `data/strategy_quality_audit.json`
- `data/strategy_quality_flags.csv`
- `data/work_strategy_metrics.csv`
- `data/department_strategy_metrics.csv`
- `data/topic_strategy_metrics.csv`
- `data/department_team_science.csv`
- `data/department_team_science_pairs.csv`
- `data/nih_reporter_awards.csv`
- `data/department_nih_funding.csv`

Actions:

- Run the strategy quality audit.
- Check row-count reconciliation across work, department, topic, team-science, and NIH outputs.
- Inspect OpenAlex missingness for topic and Field-Weighted Citation Impact.
- Inspect NIH Reporter match statuses.

Verification:

- Strategy blocking issue count: zero.
- Faculty top-10 calculations match source tables.
- Active NIH department and faculty aggregates are explainable.
- Missingness and ambiguous matches are review caveats, not hidden errors.

### U5. Scientific Wording Audit

Purpose:

Ensure the dashboard accurately frames authorship and strategy metrics.

Files:

- `index.html`

Actions:

- Search dashboard copy for overclaims about ownership, leadership, contribution, Rush performance, NIH funding, and Google Scholar.
- Adjust language only where wording implies stronger claims than the data supports.
- Confirm methodology notes are visible near the relevant visuals.

Verification:

- No language implies that last author proves ownership.
- No language implies that middle authorship is inappropriate or low value.
- No language implies Rush-affiliated metadata proves study performance location.
- No language implies Google Scholar is authoritative in this pipeline.

### U6. Visual and Interaction QA

Purpose:

Verify the new analytics are understandable and usable on the existing dashboard.

Files:

- `index.html`

Actions:

- Serve the dashboard locally.
- Inspect desktop and mobile viewports.
- Exercise Leadership Lens first-author and last-author toggle states.
- Inspect Strategy tab charts and tables.
- Check browser console for errors.
- Capture screenshots or a concise visual QA log.

Verification:

- No text overlap in cards, tables, legends, controls, or chart labels.
- Toggle state changes update the expected rankings.
- Strategy visuals render without empty or broken charts.
- Mobile layout remains readable.
- Console errors: zero.

### U7. Final Evidence and Handoff

Purpose:

Package audit results so the branch can be reviewed or merged confidently.

Files:

- `docs/plans/2026-05-15-001-fix-final-dashboard-audit-plan.md`
- Optional: `docs/audits/final-dashboard-audit-2026-05-15.md`
- Audit JSON and CSV outputs under `data/`

Actions:

- Summarize audit commands, output files, blockers, caveats, and visual QA.
- If fixes were made during audit execution, rerun affected audits.
- Produce a final branch status.
- Commit and push only if explicitly requested after the audit work.

Verification:

- All blocking counts are zero or explicitly unresolved with a reason.
- Caveats are documented with source files.
- Branch status is clean or contains only intentional audit artifacts.
- User receives a concise final summary with the exact next action.

## Test Matrix

| Area | Test | Expected Result |
| --- | --- | --- |
| Authorship attribution | Reconcile work audit rows to faculty summary counts | Zero mismatches |
| First/last confidence | Sample OpenAlex work records for matched faculty IDs | `author_position` matches dashboard role |
| Duplicate safety | Check normalized names, OpenAlex IDs, faculty-work keys | Zero unsafe duplicates |
| H-index | Top-200 exact OpenAlex author ID comparison | Zero mismatches or sourced fixes |
| Department | Rush directory comparison for matched faculty | Zero mismatches or sourced fixes |
| Google Scholar | Optional `scholarly` comparison | Non-blocking secondary caveat |
| Strategy metrics | Department/topic/team/NIH reconciliation | Zero blockers |
| Scientific copy | Search and review methodology wording | No overclaiming |
| Visual QA | Desktop and mobile dashboard inspection | No overlap, no console errors |

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| OpenAlex data drifts between runs | Review diffs and preserve audit evidence from the run date |
| Rush directory pages change or omit faculty | Treat missing matches as caveats unless source evidence supports correction |
| Google Scholar scraping fails | Keep it optional and secondary; never use it as the primary correction source |
| Lower-confidence author matches contaminate metrics | Flag rows and keep them out of high-confidence claims |
| Visual audit misses mobile overlap | Inspect at least one desktop and one narrow mobile viewport |
| Dashboard wording overstates authorship meaning | Keep language framed as proxy, signal, or evidence rather than proof |

## Success Criteria

The final audit is complete when:

- Authorship, strategy, and top-200 audits have zero blocking issues.
- First-author and last-author confidence is backed by work-level OpenAlex evidence.
- No unsafe duplicates are present.
- H-index and department values for top-200 faculty are source-checked.
- Visual QA confirms the new analytics render cleanly on desktop and mobile.
- Scientific caveats are visible and defensible.
- A final audit summary is ready for PR review or merge handoff.

## Execution Order

1. Run U1 to establish a clean regeneration checkpoint.
2. Run U2 and fix any authorship blockers before reviewing visuals.
3. Run U3 to verify h-index and department fields for the top 200.
4. Run U4 to verify strategy metric reconciliation.
5. Run U5 to tighten scientific wording.
6. Run U6 to visually inspect the dashboard.
7. Run U7 to write the final evidence summary and prepare the branch for review.
