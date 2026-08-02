# `bandplans.tsv`: licence/band data

The list of licence classes and which frequencies they're allowed on lives
in `bandplans.tsv` at the project root, not in the code. The app re-reads it
on every request to `/licenses`, so you can edit it and just refresh the
browser - no restart needed.

## Format

Tab-separated, one row per legal frequency sub-range:

| column | meaning |
| --- | --- |
| `license_id` | stable machine key, e.g. `us_general` |
| `license_name` | shown in the dropdown, e.g. "US General" |
| `country_group` | groups/orders the dropdown, e.g. `US`, `Canada`, `Europe` |
| `band` | `160m`, `80m`, `40m`, `30m`, `20m`, `17m`, `15m`, `12m`, `10m`, `6m` |
| `start_hz` / `end_hz` | the sub-range's edges, in Hz |
| `notes` | free text - mode restriction, caveats, etc. |
| `source` | short citation |
| `verified_date` | ISO date this row was last checked against its source |

A band with a mode-restricted split (e.g. US General's 80m has a separate
CW/data segment and phone segment) is just **multiple rows** with the same
`license_id` and `band` but different edges. The app unions them: checking
"80m" in the UI sweeps every segment listed for that band under that
licence.

The `US` country group always sorts first in the dropdown, and `us_general`
is the default selection (see `DEFAULT_LICENSE_ID` in `ftx1_cat.py`). Within
a group, licences keep the TSV's row order (so e.g. Technician / General /
Extra appear in that order, not alphabetically) - list them in the order you
want them to appear.

## What's verified vs. approximate

- **US Technician / General / Extra**: exact, sourced directly from 47 CFR
  §97.301 (the FCC's own table), including the CW/data vs. phone segment
  splits. See `refs/fcc_47_cfr_97.301.pdf`.
- **Canada (Basic w/ Honours, or Advanced)**: ISED's RIC-3 confirms Canada
  does *not* split HF bands by qualification (only transmit power differs,
  which this tool doesn't model) - but RIC-3 itself doesn't publish exact
  MHz edges, so the rows assume the standard ITU Region 2 allocation and are
  flagged accordingly. `ca_basic` (no Honours) correctly gets 6m only, per
  RIC-3's ">30 MHz only" rule.
- **Europe / Japan / Central & South America**: these are `_ref` entries -
  outer-bound *reference* allocations only (the physical ITU Region 1/2/3
  amateur spectrum, taken from the same FCC document's international
  columns), **not** real per-country licence-class tables. There is no
  single "CEPT licence" frequency table to encode: CEPT reciprocity
  (`refs/cept_novice_ecc_rec_05_06.pdf`) just recognizes your *home*
  licence's privileges as translated by whichever country you're visiting -
  it isn't a harmonized band plan. Japan's JARL classes do restrict by both
  frequency and power, but the exact per-class table wasn't available from
  a source reliable enough to encode here. Treat these three groups as "stay
  inside this outer boundary," not as your actual privileges, and correct/
  replace them with real data for your specific country and licence if you
  have it - that's exactly what this file is for.

## Adding your own entries

Add rows for your country/licence class following the pattern above. If you
have a real source (a regulator's published band chart, not a summary
article), cite it in `source` and set today's date in `verified_date`. PRs
or edits that replace a `_ref` placeholder with real per-class data are
especially welcome - the placeholders exist so the tool is usable, not
because the approximation is good enough to trust.
