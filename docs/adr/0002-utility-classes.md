# ADR 0002: Separate utility class from Gold/Silver/Bronze

## Status

Accepted.

## Context

A raw file is valuable for reader testing but cannot validate an analysis
algorithm without an independent reference.

## Decision

Every record receives a scientific utility class. Gold/Silver/Bronze remain
secondary heuristic labels.

## Consequences

Raw-only records are retained as `reader_fixture` and remain Bronze regardless
of a high metadata score.
