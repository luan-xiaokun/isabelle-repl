# 01. Incremental Localizer and Snapshot

## Objective

Replace one-shot localization and repeated full replay with incremental
localization over snapshot-held execution anchors.

## Module Decisions

- `localizer` discovers failures incrementally.
- `snapshot` stores:
  - current anchor state id
  - command cursor
  - applied replacements
  - last failure digest
  - minimal proof context

## Fallback Strategy

Trigger fallback replay when:

- execute result indicates context drift/mismatch
- mode/proof-level deviates from snapshot expectation

## Acceptance Criteria

- localizer progresses without header-level full replay per task in nominal path
- drift fallback is explicit and testable
- snapshot state can reconstruct the next localization step deterministically
