# KI-014 — Crash entering the Cathedral after obtaining the third relic

**Status:** Confirmed, fix in progress
**Affects:** PC and console, all difficulty levels
**First reported:** Patch 1.3.2

## Description

Players who collect the third relic (of any of the four relic sets) before entering the
Cathedral zone experience a reliable crash to desktop within a few seconds of the zone finishing
its load transition. The crash does not occur if the Cathedral is entered before the third
relic is collected.

## Workaround

Collect the third relic *after* first visiting the Cathedral at least once, if possible. There
is currently no workaround for players who have already triggered the state — a hotfix is
targeted for the next patch.

## Engineering notes

Root cause suspected to be a save-state ordering issue between the relic-count trigger and the
Cathedral zone's scripted intro sequence. Tracked internally; not yet in a public patch.
