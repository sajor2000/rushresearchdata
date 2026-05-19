---
title: "Carlos A. Q. Santos OpenAlex profile audit"
date: 2026-05-15
status: review_caveat_added
---

# Carlos A. Q. Santos OpenAlex Profile Audit

## Finding

Carlos A. Q. Santos, MD, MPHS is correctly identified as Rush faculty in the local dataset, but his OpenAlex publication record appears split across multiple OpenAlex author profiles. The current dashboard profile is not clearly the wrong person; it is the cleanest exact Rush-linked profile and contains several publications that match the Google Scholar profile. However, OpenAlex also has additional candidate profiles containing likely same-person transplant infectious disease works.

Because one candidate profile also includes apparent unrelated works, the audit did not auto-merge the profiles or overwrite h-index values. The case is now recorded in `data/faculty_identity_overrides.csv` and applied to the local row as a review caveat:

`split_profile_review(primary=A5102980347;possible=A5043572409|A5122848926)`

## Local Row

- Faculty: Carlos A. Q. Santos
- Department: Internal Medicine
- OpenAlex ID used by dashboard: `https://openalex.org/A5102980347`
- ORCID on that OpenAlex profile: `https://orcid.org/0000-0002-6224-0371`
- Local h-index: 11
- Local works count: 51
- Local cited-by count: 489
- Recent authorship rows: 25
- Last-author rows: 7
- First-author rows: 4
- Middle-author rows: 14

## External Identity Evidence

Rush faculty directory confirms:

- Name: Carlos A. Q. Santos, MD
- Role: Professor, Department of Internal Medicine, Division of Infectious Diseases
- Other roles: Director, Transplant Infectious Diseases Service; Informatics Lead, Institute for Translational Medicine
- Research focus: transplant infectious disease, epidemiology, pharmacoepidemiology, comparative effectiveness research, public health informatics
- Source: `https://www.rushu.rush.edu/faculty/carlos-q-santos-md`

Google Scholar profile found by web research:

- `https://scholar.google.com/citations?user=WmDpQNQAAAAJ&hl=en`
- Verified email at `rush.edu`
- Listed as Carlos A. Q. Santos, MD, MPHS, Professor of Medicine, Rush University Medical Center

Direct automated Google Scholar scraping was blocked or timed out, so Google Scholar was used only for identity and publication-title comparison, not as a numeric source of truth.

## OpenAlex Candidate Profiles

| OpenAlex ID | Display name | OpenAlex ORCID | h-index | Works | Citations | Interpretation |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `A5102980347` | Carlos A.Q. Santos | `0000-0002-6224-0371` | 11 | 51 | 489 | Current dashboard profile; Rush-linked and contains several Google Scholar-profile works. |
| `A5043572409` | Carlos Santos | `0000-0002-6874-6736` | 12 | 48 | 593 | Contains likely same-person transplant infectious disease works, but also apparent unrelated works, so unsafe to merge wholesale. |
| `A5122848926` | Carlos A Q Santos | none | 0 | 3 | 0 | Contains recent HIV transplant works likely related to the same investigator; needs manual review. |

## Publication Cross-Checks

Google Scholar-profile or Rush-relevant publication titles mapped as follows in OpenAlex:

| Publication | OpenAlex author profile found |
| --- | --- |
| Epidemiology of bloodstream infections in a multicenter retrospective cohort of liver transplant recipients | `A5102980347` |
| Pseudozyma and other non-Candida opportunistic yeast bloodstream infections in a large stem cell transplant center | `A5102980347` |
| Methicillin-resistant Staphylococcus aureus USA300 clone as a cause of Lemierre syndrome | `A5102980347` |
| Human paragonimiasis in North America following ingestion of raw crayfish | `A5102980347` |
| Effects of recurrent urinary tract infections on graft and patient outcomes after kidney transplantation | `A5102980347` |
| Epidemiology of cryptococcosis and cryptococcal meningitis in a large retrospective cohort of patients after solid organ transplantation | `A5043572409` |
| Safety of Kidney Transplantation from Donors with HIV | `A5043572409` |

## Decision

Do not replace the dashboard OpenAlex ID and do not merge all candidate works automatically.

Reason:

- `A5102980347` is a valid Rush-linked Carlos A. Q. Santos profile and contains multiple Google Scholar-profile publications.
- `A5043572409` likely contains some same-person publications but also shows signs of profile contamination, including unrelated publication topics and institution/name variants.
- A safe correction requires publication-level manual curation or an OpenAlex profile merge upstream.

## Data Change Made

The dashboard dataset now marks Carlos A. Q. Santos as a split-profile review case via a structured identity override. This keeps the record visible as a data quality caveat without introducing an unsafe h-index or authorship overwrite.

Verification after the override:

- Carlos has one faculty summary row.
- The dashboard primary OpenAlex ID remains `https://openalex.org/A5102980347`.
- No duplicate OpenAlex author IDs were introduced.
- No duplicate faculty-author-work rows were introduced.
- Authorship audit blockers remain zero.
