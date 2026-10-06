# Hybrid Collaborator Recommendation System

HAL publication ingestion pipeline that fetches records from the UTC HAL portal, transforms them into canonical Python models, exports normalized CSV tables, and can persist them to Neo4j.

This README describes the current implemented repository state. The collaborator recommender is a future target; see [the current-vs-target status document](docs/CURRENT_STATE_VS_TARGET_STATE.md) and [the project spec](docs/PROJECT_SPEC.md) for the staged architecture. The current code separates:

- raw data from external APIs;
- data transformation and normalization;
- canonical domain models;
- Neo4j persistence;
- CSV dry runs before populating the database.

## Overview

The pipeline searches HAL publications related to `data science`, extracts entities and relationships, and can:

- save normalized data to Neo4j;
- export normalized data to CSV for validation before database insertion.

Currently modeled entities:

- `Project`
- `Author`
- `Conference`
- `Organization`
- `ResearchDomain`

Currently extracted relationships:

- `Author` -> `Project`: author wrote a publication/project;
- `Project` -> `Conference`: publication was presented at a conference;
- `Project` -> `Organization`: publication is associated with organizations;
- `Organization` -> `Organization`: `PART_OF` hierarchy;
- `Project` -> `ResearchDomain`: research domain association, with a `primary` relationship property;
- `ResearchDomain` -> `ResearchDomain`: `SUBDOMAIN_OF` hierarchy.

## Project Structure

```text
src/
  connectors/
    hal_client.py          # HAL API client
    orcid_client.py        # Placeholder for ORCID integration
  database/
    neo4j_manager.py       # Neo4j persistence
  models/                  # Canonical entity and extraction dataclasses
    author.py              # Canonical author model
    conference.py          # Canonical conference model
    organization.py        # Canonical organization model
    project.py             # Canonical publication/project model
    research_domain.py     # Canonical research domain model
  processing/
    transformer.py         # HAL -> canonical model transformations
  queries/
    graph_querier.py       # Graph queries
  export_pipeline_csv.py   # HAL-to-CSV validation/export CLI
  pipeline.py              # Neo4j ingestion pipeline

tests/
  test_export_pipeline_csv.py
  test_organization_transformer.py
  test_research_domain_transformer.py
```

`src/capability/`, `src/graph/`, `src/rag/`, `src/recommender/`, and
`src/requirements/` are reserved for future work. `src/validation/` contains
HAL response validation, ETL comparison, and Neo4j integrity checks.
`src/config.py` and `src/connectors/orcid_client.py` are empty placeholders.
The models are in `src/models/` (not `src/graph/models/`).

## Installation

Requires Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Neo4j Configuration

Create a `.env` file at the project root. This file must not be committed.

Example:

```env
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
```

`Neo4jManager` reads `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`, with
local defaults of `bolt://localhost:7687`, `neo4j`, and `password`.
`GraphQuerier` reads the same variables but has no defaults. Set all three
explicitly when using either component. The pipeline writes data; run it only
against the intended database.

## Canonical Models

### Project

Represents a normalized HAL publication/document. The code calls this entity
`Project`; it is not a funded research project.

Fields:

- `hal_id`
- `title`
- `abstract`
- `keywords`
- `document_type`
- `language`
- `publication_date`
- `publication_year`
- `doi`
- `uri`

### Author

Represents publication authors.

Fields:

- `person_id`
- `hal_id`
- `first_name`
- `last_name`
- `email_domain`
- `orcid_id`
- `google_scholar_id`
- `researcher_id`
- `idref_id`

### Conference

Represents conferences when conference metadata exists in the HAL record.

Fields:

- `conference_id`
- `title`
- `start_date`
- `end_date`
- `city`
- `country`

Important: `ART` records are usually journal articles and may not contain conference fields. To test conference extraction, prefer `COMM` records.

### Organization

Represents institutions, laboratories, research teams, departments, and other structures as a single entity type differentiated by the `type` field.

Fields:

- `hal_id`
- `name`
- `acronym`
- `type`
- `country`
- `address`
- `code`
- `status`
- `ror`
- `idref`
- `isni`
- `rnsr`
- `wikidata`

Organization hierarchy is kept separately as `PART_OF` relationships.

### ResearchDomain

Represents research domains independently from HAL-specific field names.

Fields:

- `id`
- `name`
- `name_fr`
- `source`

Research domain hierarchy is kept separately as `SUBDOMAIN_OF` relationships. The model does not store a `level` property.

## HAL Fields

The HAL client requests the required fields in `src/connectors/hal_client.py`.

Main field groups:

- publication: `halId_s`, `title_s`, `abstract_s`, `keyword_s`, `docType_s`, `language_s`, `producedDate_s`, `publicationDateY_i`, `doiId_s`, `uri_s`;
- authors: `authFullName_s`, `authIdPerson_i`, `authIdHal_s`, `authFirstName_s`, `authLastName_s`, `authEmailDomain_s`, `authORCIDIdExt_s`, `authGoogleScholarIdExt_s`, `authResearcherIdIdExt_s`, `authIdRefIdExt_s`;
- organizations: `structId_i`, `structName_s`, `structAcronym_s`, `structType_s`, `structCountry_s`, `structAddress_s`, `structCode_s`, `structValid_s`, `structRorIdExt_s`, `structIdrefIdExt_s`, `structIsniIdExt_s`, `structRnsrIdExt_s`, `structWikidataIdExt_s`, `structIsChildOf_fs`;
- conferences: `conferenceTitle_s`, `conferenceStartDate_s`, `conferenceEndDate_s`, `city_s`, `country_s`;
- research domains: `primaryDomain_s`, `domainAllCode_s`, `en_domainAllCodeLabel_fs`, `fr_domainAllCodeLabel_fs`, `level0_domain_s`, `level1_domain_s`, `level2_domain_s`.

## CSV Dry Run

Before populating Neo4j, use the CSV exporter to inspect the generated instances.

Run the default HAL query with at most one publication:

```bash
python3 src/export_pipeline_csv.py --rows 1 --output exports/pipeline_csv_test
```

Fetch a specific HAL article:

```bash
python3 src/export_pipeline_csv.py --hal-id hal-03002550 --rows 1 --output exports/pipeline_csv_test
```

Fetch only conference/communication publications:

```bash
python3 src/export_pipeline_csv.py --query '("data science" OR "science de données")' --doc-type COMM --rows 1 --output exports/pipeline_csv_comm_test
```

Generated CSV files:

- `projects.csv`
- `authors.csv`
- `conferences.csv`
- `organizations.csv`
- `research_domains.csv`
- `project_authors.csv`
- `project_conferences.csv`
- `project_organizations.csv`
- `organization_relationships.csv`
- `project_research_domains.csv`
- `research_domain_hierarchy.csv`

## Populate Neo4j

After validating the CSV output and configuring `.env`, run:

```bash
PYTHONPATH=src python3 src/pipeline.py
```

The pipeline currently:

1. Fetches publications from HAL.
2. Normalizes metadata using `processing/transformer.py`.
3. Creates Neo4j uniqueness constraints.
4. Saves graph nodes and relationships.

`HalClient` defaults to the HAL query `*:*` on the UTC portal. The CSV
exporter defaults to one record, but `pipeline.py` fetches all matching
records; it has no row limit or dry-run mode. Start with the CSV exporter
when checking data. Existing graph properties are set with `ON CREATE SET`,
so re-running ingestion does not refresh properties on nodes that already
exist.

### Validate an author-identity change on a dev subset

The author extractor now repairs only uniquely name-matched cross-position
HAL IDs and uses `authIdPerson_i` before the name-based fallback. To exercise
the changed path without fetching or ingesting the whole corpus, provide a
snapshot, an explicit limit of at most 2,000 records, and a dedicated,
isolated Neo4j dev database:

```powershell
$env:PYTHONPATH = "$PWD\src"
& .\.venv\Scripts\python.exe src\pipeline.py `
  --snapshot exports\hal_snapshot\hal_snapshot_20261005T191317Z\records.jsonl `
  --limit 1000 `
  --database author_identity_dev
```

The snapshot is ordered by `halId_s`; the first 1,000 records make this a
repeatable integration smoke test of the transformer and graph writes. Unit
tests separately exercise the confirmed shift, fallback, and ambiguous-match
cases. This bounded subset is sufficient to catch failures in those changed
paths and the persistence call, but it is not a new full-corpus quality
estimate. Run only against a dev database, not the shared or production
database.

Neo4j writes use `MERGE` and `ON CREATE SET`; re-ingestion does not remove old
author-to-project relationships or refresh existing author properties. A
full-data rollout therefore requires a separately reviewed migration or
rebuild strategy for previously persisted author identities, followed by
re-ingestion of the complete snapshot and full integrity/data-quality checks.
Do not treat a successful 1,000-record dev run as authorization for that
full-data operation.

## Check Neo4j integrity

Run the read-only integrity checks after configuring the `.env` Neo4j
connection:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m validation.neo4j_integrity
```

The JSON report marks uniqueness-constraint verification as a **preventive**
control and graph scans (duplicate nodes, missing links, orphan or bare
nodes, repeated relationships, and `unknown_` authors) as **diagnostic**
checks. Findings are reported; the command does not modify the graph.

## Validate the ResearchDomain hierarchy

Run the read-only hierarchy checks against Neo4j with the same connection
settings:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m validation.hierarchy
```

The checker validates cycles, orphan domain nodes, missing edge endpoints,
dotted-prefix parent rules, duplicate edges, the expected maximum of three
domain levels, and malformed IDs or labels. HAL's `ResearchDomain` taxonomy
is authoritative source data; recommendation logic may use it but must not
rewrite it. Inferred capabilities and project requirements are separate data,
so they cannot silently alter the taxonomy's meaning.

## Generate a data-quality report

Build date-stamped Markdown and JSON reports from a HAL snapshot. The HAL
validation runs automatically; previously generated ETL, hierarchy, and
Neo4j integrity JSON results can be included as optional inputs:

Snapshot records pad requested or present `auth*` arrays to the author count,
using numeric `0` where a corresponding author value is missing. Reports treat
that author-ID placeholder as missing.

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m validation.report .\exports\hal_snapshot\<snapshot>\records.jsonl `
  --manifest .\exports\hal_snapshot\<snapshot>\manifest.json
```

The output is written to `reports/data_quality_<date>.json` and `.md`.
Supply existing check results with `--etl-comparison`, `--hierarchy`, and
`--integrity` when available. Omit checks that have not been run; the report
marks them as `not_run` and lists them as open risks rather than implying they
passed. Missingness is reported as a measured rate and does not itself mean
an optional HAL field is invalid.

## Tests

Run all tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

Validate syntax/compilation:

```bash
python3 -m compileall src tests
```

Current tests cover:

- research domain extraction;
- research domain hierarchy;
- organization extraction;
- organization parallel-array alignment and sparse identifiers.

There are no recommender, capability extraction, graph-adapter, or Dublin
Core transformation tests because those features are not implemented.
- deduplication by HAL identifier;
- CSV pipeline export.

## Important Notes

- `Organization` replaces separate models such as `University` and `Laboratory`.
- The organization type comes from `structType_s`, for example `institution`, `laboratory`, or `researchteam`.
- Hierarchical relationships are not stored as internal entity properties.
- Conferences only appear when HAL returns fields such as `conferenceTitle_s`; journal articles (`ART`) usually do not have conference metadata.
- Organization external identifiers, such as ROR and IdRef, are associated by array position only when HAL returns arrays with the same length as `structId_i`. When the association is not reliable, the field is left empty.
