# Stage A data quality and handoff

This page summarizes the Stage A evidence available to Stage B. Counts
describe the exact input/report snapshot and should not be treated as timeless
database totals.

## Availability in GitHub

The repository's `.gitignore` excludes both `exports/` and `reports/`.
Therefore raw HAL snapshots and generated JSON/Markdown reports are local
artifacts: links or paths into those directories will not resolve for a
Stage B contributor who clones the GitHub repository.

The aggregate figures recorded on this page are the committed handoff
summary. To inspect individual records or full findings, each contributor
must generate a fresh local snapshot/report using their own approved HAL and
Neo4j access. Do not commit `.env`, credentials, or raw snapshots to work
around the ignore rules. If Stage B needs shared detailed output, attach it
through an approved private project channel or commit a reviewed,
credential-free and appropriately minimized summary under `docs/`.

## HAL snapshot and validation

The snapshot used for the current full-corpus validation was the local,
ignored artifact `exports/hal_snapshot/hal_snapshot_20261005T225231Z/`.
It is not included in GitHub. Its recorded characteristics were:

- Query: `*:*`
- HAL `numFound`: **11,956**
- Fetched records: **11,956**
- Sort: `halId_s asc`
- Validation: **0 errors**, **75,336 warnings**

The warnings measure source-data conditions; they do not mean that all
records are unusable. Counts by warning code:

| Warning | Count |
|---|---:|
| Parallel-array length mismatch | 57,297 |
| Malformed date | 5,063 |
| Missing keywords | 4,507 |
| Missing DOI | 4,337 |
| Missing abstract | 2,835 |
| Multiple title values | 1,063 |
| Missing ResearchDomain fields | 231 |
| Malformed language | 3 |

The validator reports absent optional metadata as warnings, consistent with
the specification. Review individual array differences against the HAL
record semantics; padded values are not proof that parallel values were
originally aligned.

The detailed validation JSON and composite Markdown/JSON reports were
generated under the ignored local `reports/` directory and are not available
from GitHub. Regenerate a local snapshot and quality report with:

```powershell
$env:PYTHONPATH = "$PWD\src"
& .\.venv\Scripts\python.exe -m connectors.hal_snapshot --query '*:*'
& .\.venv\Scripts\python.exe -m validation.report `
  exports\hal_snapshot\<new-snapshot-directory>\records.jsonl `
  --manifest exports\hal_snapshot\<new-snapshot-directory>\manifest.json `
  --output-dir reports
```

The command writes the report locally. The report CLI accepts optional
`--integrity`, `--etl-comparison`, and `--hierarchy` JSON inputs; these inputs
must be generated for the same intended database/snapshot before combining
them.

## Author identity decision (D2)

The D2 decision and rationale are recorded in
[`DECISIONS.md`](DECISIONS.md). On the measured snapshot, 5,321/11,956
records (44.51%) contained a uniquely name-matched cross-position HAL author
ID. The transformer corrects only those unambiguous matches. It does not
guess ambiguous identities; missing IDs fall back to `person_<id>`, then
`unknown_<name>`.

The bounded 1,000-record D2 import was reported in the decision record as
loaded into the development graph. It checked the modified extractor and
write path, but does not establish full-corpus identity accuracy.

## Live Neo4j integrity reports

Two read-only integrity reports were generated locally on 2026-10-06. Their
summaries were:

| Local report file (not in GitHub) | Findings | Missing expected unique constraints | Projects without domains | `unknown_` authors |
|---|---:|---:|---:|---:|
| `neo4j_integrity_2026-10-06.json` | 1,367 | 5 | 187 | 1,175 |
| `neo4j_integrity_report.json` | 13,420 | 5 | 231 | 13,184 |

Both also report that the remaining integrity checks had no findings. The
reports do not record the database name or a database fingerprint, and their
counts differ substantially. Do not combine them or claim either is the
definitive state of the Stage B development database until the target database
is identified and a fresh report is captured with that identity documented
(but without credentials).

The integrity checker prints its JSON result to stdout. A contributor can run
it locally after configuring `.env` and preserve that output under their
ignored `reports/` directory:

```powershell
$env:PYTHONPATH = "$PWD\src"
$env:PYTHONIOENCODING = "utf-8"
& .\.venv\Scripts\python.exe -m validation.neo4j_integrity |
  Set-Content -Encoding utf8 reports\neo4j_integrity_local.json
```

Confirm the script is pointed at the intended database before treating its
results as a Stage B baseline; never share the `.env` file. Note that the
current integrity CLI opens a default Neo4j session and does not explicitly
select `NEO4J_DATABASE`; verify that the server's default database is the
intended target, or update the checker to accept the database explicitly
before using this command as a database-specific baseline.

The missing five constraints are the expected uniqueness constraints for
`Project.halId`, `Author.halId`, `Conference.conferenceId`,
`ResearchDomain.id`, and `Organization.halId`. Confirm the selected
development database and resolve this before relying on uniqueness for Stage
B inferred nodes/relationships. Do not create constraints on a shared
database without confirming existing duplicate-key data and approval.

The 187/231 projects without domains and 1,175/13,184 placeholder authors are
diagnostic findings, not identities or taxonomy values to invent. Compare
them to the corresponding HAL snapshot and record which database was checked.

## Stage B integration smoke test

The project owner confirms that the live adapter test was performed and
worked as intended. GitHub contains no redacted test transcript, selected
project ID, returned rows, or a database identifier tied to that test.
Therefore this is owner-confirmed evidence, not a reproducible checked-in
integration test. Before future live troubleshooting, record those safe
details in the handoff notes; never include URI credentials or passwords.

The checked-in `unittest` suite most recently passed **65 tests**. Its adapter
contract tests use a fake driver; the owner-reported live check supplements
but does not replace them.

## Remaining verification for Stage B

1. Identify and record the exact development database used for Stage B without
   recording credentials.
2. Rerun the integrity check against that database and preserve the report
   with its database identity, check timestamp, and target-environment label.
3. Resolve or explicitly accept the missing uniqueness constraints before
   writing inferred data. Check existing duplicate keys first.
4. Review projects without domains and placeholder authors as data-quality
   cases; do not fabricate ResearchDomains or author identities.
5. Keep existing ETL identities and schema stable. Any Stage A code change
   requires a concrete bug and the Stage A owner's approval.
