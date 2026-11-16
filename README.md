# Power BI build sheet

Power BI Desktop is the place this report is opened. This folder is everything required to rebuild it from the CSVs: the grain, the relationships, the measures, and the three pages. The Streamlit app in the project root is the same desk, already running.

## Load

Get data from text/CSV, all four files in `data/`:

| Table | File | Grain |
|---|---|---|
| `submissions` | `submissions.csv` | One filing: institution × quarter |
| `flags` | `flags.csv` | One failed check on one field of one filing |
| `institutions` | `institutions.csv` | One institution |
| `quarters` | `quarters.csv` | One quarter, with `quarter_idx` for sort order |

Do not let Power BI auto-detect a relationship from institution name. Names are unique here, but the key is `institution_id`.

## Relationships

```
institutions[institution_id]  1 ── *  submissions[institution_id]
institutions[institution_id]  1 ── *  flags[institution_id]
quarters[quarter]             1 ── *  submissions[quarter]
quarters[quarter]             1 ── *  flags[quarter]
```

`submissions` and `flags` are both many-side facts. Do not join them to each other on institution and quarter at once (that is a many-to-many on two columns). Filter both through `institutions` and `quarters`. A filing with several flags is several rows in `flags`, which is what a reviewer wants to count.

Mark `quarters[quarter_idx]` as the sort column for `quarters[quarter]`.

## Calculated column

On `flags`:

```
filing_key = flags[institution_id] & "|" & flags[quarter]
```

## Measures

See `measures.dax`. The ones to paste, after `filing_key` exists:

```
Filings = COUNTROWS(submissions)

Flags = COUNTROWS(flags)

Filings with a flag = DISTINCTCOUNT(flags[filing_key])

High severity flags = CALCULATE(COUNTROWS(flags), flags[severity] = "High")

Medium severity flags = CALCULATE(COUNTROWS(flags), flags[severity] = "Medium")

Flag rate = DIVIDE([Filings with a flag], [Filings])
```

## Pages

### 1. Overview

- Cards: Filings, Flags, Filings with a flag, Flag rate, High severity flags
- Column chart: `Flags` by `quarters[quarter]`
- Bar chart: `Flags` by `flags[check]`
- Slicers: quarter, peer group (`institutions[peer_group]`), severity

### 2. Queue

- Table: institution, quarter, check, field, severity, detail, value
- Sorted by severity, then institution
- Clicking a row should cross-filter the filing card on page 3. Turn on cross-report drill or a page navigation drillthrough with `institution_id` and `quarter`.

### 3. Institution

- Slicers: institution, quarter
- Multi-row card from `submissions`: total assets, CET1 ratio, LCR, NPL ratio, loans, deposits, equity
- Table of the flags on that filing only
- Line chart of `submissions[cet1_ratio]`, `submissions[npl_ratio]` and `submissions[lcr]` across `quarters[quarter]`, so a jump is visible next to the flag that caught it

## What "done" looks like

With no slicers applied the cards match `reports/metrics.json` from the Python run: 240 filings, 77 flags, 43 filings with a flag. If those three numbers differ, a relationship is filtering rows out or the wrong CSV was loaded.
