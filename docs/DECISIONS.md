# Decisions

## D2 — Correct HAL author identities

| | |
|---|---|
| **Decision** | Correct only author IDs that can be matched unambiguously to a different name in the same HAL record. |
| **Status** | Implemented; regression-tested and exercised on 1,000 records in the Aura dev database. |
| **Why** | The snapshot showed widespread positional ID/name shifts and name-based fallback collisions. |
| **Full-data rollout** | Not done. Requires a separately reviewed migration or clean rebuild, followed by full-snapshot checks. |

### Why this change was needed

In the 2026-10-05 snapshot:

- **5,321 of 11,956 records (44.51%)** had at least one HAL author ID that
  uniquely matched a different author's name in that record.
- There were **8,683** such matches among **18,268** nonzero HAL IDs.
- **34,903 of 53,171 author appearances (65.64%)** had no usable HAL ID.
- **160** `unknown_<name>` fallback keys were associated with multiple
  nonzero HAL person IDs, appearing in **1,910 records**.

The report's zero array-length mismatch count did not rule this out: padding
can make arrays the same length without putting each ID beside the right name.
Repeated names are only a warning signal; they do not prove that two records
refer to the same person.

### What the ETL now does

1. Keeps `authFullName_s` as the author sequence.
2. If any ID uniquely matches a different name in the record, treats the
   record as shifted and assigns only unique name/ID matches to those names.
   It does not guess the owner of ambiguous or unmatched IDs.
3. If no shift is confirmed, keeps the existing positional IDs.
4. When an author has no usable HAL ID, uses `person_<authIdPerson_i>` if a
   nonzero person ID is available; otherwise uses `unknown_<name>`.
5. Uses the same author transformer for identity metrics in future
   data-quality reports.

The Neo4j schema is unchanged. Some author keys and their `WROTE` links may
change as a result. Project fields, organization and domain extraction,
relationship types, and property refresh behavior were not changed.

### Validation completed

- Regression tests cover confirmed shifts, ambiguous/no-shift behavior, and
  both fallback steps.
- The full unit test suite most recently passed: **65 tests** on 2026-10-06.
- The first **1,000** records of the stable, sorted snapshot were imported
  into Aura dev database `31f9ca9f`.
- Before import, the dev graph was cleared (**1,544 nodes** and
  **3,080 relationships**); afterward, the clear was verified as empty.
- After import: **1,000 projects**, **1,867 authors**, **4,106 `WROTE` links**,
  and **zero projects without authors**.

The bounded import is a repeatable integration smoke test: it checks that
real snapshot records pass through the changed extractor and Neo4j write
path. Together with focused regression tests, it is sufficient to validate
these code paths without reloading the full corpus. It does **not** certify
identity quality across all records or replace full-data checks.

### Stage A live adapter check

The project owner reports that the live Neo4j adapter smoke test described in
the Stage A handoff was run successfully. The exact project ID, returned
values, database identity, and redacted transcript were not provided for
check-in, so this is recorded as owner-confirmed rather than as a
reproducible test artifact. No credentials belong in the test record.

The separate integrity reports generated under local `reports/` are not
attributable to a specific database and disagree in finding totals. They do
not change the D2 bounded-import result; obtain a fresh, database-identified
integrity baseline before Stage B writes inferred data. Both `reports/` and
`exports/` are ignored by Git, so those raw files are not available on GitHub;
the committed aggregate findings and regeneration guidance are in
[`data_quality.md`](data_quality.md). The current integrity CLI uses the
server-default Neo4j database rather than explicitly selecting
`NEO4J_DATABASE`; confirm the target when capturing the next baseline.

### Before any full-data rerun

Persistence uses `MERGE` and `ON CREATE SET`. Re-ingestion alone will not
refresh existing author properties or remove stale author nodes and `WROTE`
links. Before a full rollout:

1. Review and approve a migration or clean-rebuild plan for old and corrected
   author identities and relationships.
2. Ingest the complete, validated snapshot into the intended database.
3. Recompute full-snapshot data-quality metrics and run ETL comparison and
   Neo4j integrity checks, including duplicate identities, author links, and
   remaining `unknown_` authors.
4. Compare before/after counts and investigate unexpected changes.
