# Hybrid Collaborator Recommendation System

Data engineering pipeline for collecting publication metadata from the HAL API, normalizing it into canonical domain models, and preparing it for insertion into a Neo4j knowledge graph.

The project is still evolving. The current architectural rule is to keep these concerns separate:

- raw data from external APIs;
- data transformation and normalization;
- canonical domain models;
- Neo4j persistence;
- CSV dry runs before populating the database.

## Overview

The pipeline ingests publications from the HAL API (default query is `*:*`, harvesting the UTC repository, or filtered queries), extracts entities and relationships, extracts and aggregates research capabilities, and powers a research collaboration recommender.

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
  models/
    author.py              # Canonical author model
    conference.py          # Canonical conference model
    organization.py        # Canonical organization model
    project.py             # Canonical publication/project model
    research_domain.py     # Canonical research domain model
  processing/
    transformer.py         # HAL -> canonical model transformations
  queries/
    graph_querier.py       # Graph queries
  export_pipeline_csv.py   # Pipeline dry run exporting CSV files
  pipeline.py              # Neo4j ingestion pipeline

tests/
  test_export_pipeline_csv.py
  test_organization_transformer.py
  test_research_domain_transformer.py
```

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
NEO4J_USERNAME=neo4j
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
NEO4J_DATABASE=neo4j
AURA_INSTANCEID=your-instance-id
AURA_INSTANCENAME=your-instance-name
```

Note: the current `Neo4jManager` reads `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`.

## Canonical Models

### Project

Represents the normalized HAL publication/document.

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

Run the default search with only one publication:

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

The pipeline:

1. Fetches publications from HAL.
2. Normalizes metadata using `processing/transformer.py`.
3. Creates Neo4j uniqueness constraints.
4. Saves graph nodes and relationships.

## Collaborator Recommendation (Stage C)

Run collaborator recommendations using the CLI:

```bash
# Recommend for an existing publication (using in-memory fixtures)
PYTHONPATH=src python3 src/recommend_cli.py --project-id hal-001 --use-fake-adapter --top-k 5

# Recommend for a new free-text project specification
PYTHONPATH=src python3 src/recommend_cli.py \
  --title "Privacy-Preserving Federated Learning" \
  --keywords "federated learning, differential privacy" \
  --use-fake-adapter --top-k 3

# Recommend on live Neo4j database
PYTHONPATH=src python3 src/recommend_cli.py --project-id anses-03212886 --top-k 5
```

### End-to-End Demo

Run the comprehensive demo script:

```bash
# Demo with static fixtures
PYTHONPATH=src python3 demo.py

# Demo connecting to live Neo4j
PYTHONPATH=src python3 demo.py --live
```

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
- HAL parallel array alignment;
- deduplication by HAL identifier;
- CSV pipeline export.

## Important Notes

- `Organization` replaces separate models such as `University` and `Laboratory`.
- The organization type comes from `structType_s`, for example `institution`, `laboratory`, or `researchteam`.
- Hierarchical relationships are not stored as internal entity properties.
- Conferences only appear when HAL returns fields such as `conferenceTitle_s`; journal articles (`ART`) usually do not have conference metadata.
- Organization external identifiers, such as ROR and IdRef, are associated by array position only when HAL returns arrays with the same length as `structId_i`. When the association is not reliable, the field is left empty.
