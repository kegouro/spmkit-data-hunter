# ADR 0001: Checkpoint after complete pages

## Status

Accepted.

## Context

Long searches must survive interruption without skipping results. Persisting a
next cursor before processing its current page risks permanent data loss.

## Decision

The campaign engine advances a checkpoint only after every record in the page
has been committed. Budgets and pause requests are checked between pages.

## Consequences

A campaign may slightly exceed a soft record/time budget by one page. A crash
may replay a page, but idempotent writes prevent duplicate catalog records.
