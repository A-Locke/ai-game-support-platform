# KI-014 — App crashes exporting a report with more than 10,000 rows

**Status:** Confirmed, fix in progress
**Affects:** All platforms/browsers
**First reported:** Release 1.3.2

## Description

Exporting a report to CSV crashes the app reliably once the report contains more than roughly
10,000 rows. The export gets partway through, then the tab/app becomes unresponsive and crashes.
Reports under 10,000 rows export fine.

## Workaround

Filter the report to a smaller date range or fewer columns to bring it under 10,000 rows, or
export in multiple smaller batches. A permanent fix (streaming export instead of building the
full file in memory) is targeted for an upcoming release.

## Engineering notes

Root cause: the CSV export path buffers the entire result set in memory before writing, which
becomes untenable past ~10k rows on typical browser tab memory limits. Fix in progress: switch
to a streamed/chunked export. Tracked internally; not yet in a public release.
