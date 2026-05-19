---
title: "Final dashboard audit"
date: 2026-05-15
branch: codex/senior-authorship-lens
status: passed_with_caveats
---

# Final Dashboard Audit

## Summary

The final audit passed the release gate for the current Rush research dashboard branch. Authorship, strategy, h-index, and department checks report zero blocking issues. The remaining issues are review caveats tied to source limitations, lower-confidence faculty matches, missing OpenAlex metadata, NIH matching ambiguity, Rush directory misses, and Google Scholar timeout behavior.

## Data Quality Results

| Check | Result |
| --- | --- |
| Authorship blockers | 0 |
| Duplicate normalized faculty names | 0 |
| Duplicate normalized faculty name plus department | 0 |
| Duplicate OpenAlex author IDs | 0 |
| Duplicate faculty-author-work rows | 0 |
| Faculty summary to work-audit mismatches | 0 |
| Leadership-ratio mismatches | 0 |
| Strategy blockers | 0 |
| Top-200 OpenAlex h-index mismatches | 0 |
| Top-200 Rush directory department mismatches | 0 |

Authorship row counts reconciled exactly:

- Faculty summary recent authorship rows: 26,645
- Work-level audit rows: 26,645
- Position-total rows: 26,645

OpenAlex author-position confidence:

- First-author rows: 2,884
- Last-author rows: 6,095
- First-or-last rows: 8,979
- High-confidence first-or-last rows: 8,979
- Single-author or ambiguous rows: 587

Manual OpenAlex spot checks confirmed the matched faculty OpenAlex author ID had the expected `author_position` for sampled first- and last-author works:

- David A. Bennett, first, `W2945300267`
- John E. O'Toole, first, `W4410823892`
- Christopher G. Goetz, first, `W4385751785`
- Julie A. Schneider, last, `W4389143955`
- Christopher J. O'Connor, last, `W3159502310`
- Brian J. Cole, last, `W3119331278`

## Source Checks

Top-200 h-index and department audit:

- Scope: top 200 faculty by CSV h-index
- H-index source: OpenAlex author `summary_stats.h_index` by exact OpenAlex author ID
- Department source: Rush University public faculty directory
- Rush directory records scraped: 1,691
- H-index mismatches: 0
- Department mismatches where directory matched: 0
- Missing Rush directory matches: 35

Google Scholar comparison:

- Scope: top 20 faculty by CSV/OpenAlex h-index
- Package available: yes
- Status counts: 20 timeouts
- Usable high or probable matches: 0
- Interpretation: non-blocking only. Google Scholar has no official public API, and `scholarly` results can be blocked, incomplete, or ambiguous.

## Strategy Metrics

Strategy audit passed with zero blockers.

Key reconciliation counts:

- Faculty summary rows: 1,688
- Faculty-work rows: 26,645
- Unique authorship works: 19,197
- Work strategy metric rows: 19,197
- Department strategy rows: 28
- Topic strategy rows: 1,847
- NIH Reporter award rows: 773

Review caveats:

- OpenAlex primary topic missing for 105 work rows.
- OpenAlex Field-Weighted Citation Impact missing for 1,224 work rows.
- NIH active project counts differ by denominator: 84 unique active department projects versus 93 summed faculty attributions.

## Scientific Wording and Visual QA

Dashboard wording was tightened so last authorship is described as a senior-leadership proxy based on authorship order, not proof that the faculty member owned a study. Middle authorship remains framed as legitimate collaboration and contribution, not inappropriate authorship.

Browser QA was run against the locally served dashboard at `http://127.0.0.1:8765/index.html`.

Desktop and mobile checks confirmed:

- Leadership Lens rendered.
- Last-author and first-author toggle states rendered.
- First-author toggle updated the top faculty ranking title and note.
- Authorship role-mix chart rendered.
- Authorship ranking chart rendered.
- Strategy Metrics tab rendered 8 KPI cards.
- Strategy impact, topic portfolio, and NIH funding charts rendered.
- Horizontal overflow was false on desktop and mobile.
- Browser console errors: 0.

## Caveats to Preserve

- The 49 lower-confidence or split-profile faculty matches with recent authorship rows remain review caveats.
- The 1,063 authorship rows inherited from lower-confidence or split-profile matches should not be described as fully identity-verified.
- Carlos A. Q. Santos is now explicitly flagged as an OpenAlex split-profile review case through `data/faculty_identity_overrides.csv`; see `docs/audits/carlos-santos-openalex-profile-audit-2026-05-15.md`.
- Multiple Rush faculty can appear on the same OpenAlex work; this is expected coauthorship, not a duplicate error.
- Missing Rush directory matches should not be auto-corrected without source evidence.
- Google Scholar should not overwrite OpenAlex h-index values.
