# Current State vs Target State

This document separates the repository as it exists today from the architecture it is designed to reach.

## 1. Current state: implemented repository

The live repository is an ETL and validation pipeline for HAL publications.

### Implemented scope
- Python 3.10+ project using `requests`, `python-dotenv`, and Neo4j.
- HAL client for querying publication records.
- Canonical models for:
  - `Project`
  - `Author`
  - `Conference`
  - `Organization`
  - `ResearchDomain`
- Transformation layer that converts HAL documents into canonical Python objects.
- Neo4j persistence with uniqueness constraints and graph relationships.
- CSV export for dry-run validation before database writes.
- Unit tests covering main transformer and export behaviors.

### Current graph facts
The implemented graph is built around HAL publication data:
- `Project{halId}`
- `Author{halId}`
- `Conference{conferenceId}`
- `ResearchDomain{id}`
- `Organization{halId}`

Relationships currently implemented include:
- `(Author)-[:WROTE]->(Project)`
- `(Project)-[:PRESENTED_AT]->(Conference)`
- `(Project)-[:HAS_RESEARCH_DOMAIN {primary}]->(ResearchDomain)`
- `(ResearchDomain)-[:SUBDOMAIN_OF]->(ResearchDomain)`
- `(Project)-[:HAS_ORGANIZATION]->(Organization)`
- `(Organization)-[:PART_OF]->(Organization)`

### What is not implemented yet
The following layers are described in planning docs but do not exist as live code in this repository:
- capability extraction and resolution
- capability provenance and versioning
- requirements extraction
- recommender ranking
- candidate generation and feature scoring
- GraphRAG explanation layer
- graph adapter contract and mapping config
- recommendation CLI

### Evidence from repository layout
Current implementation folders include:
- `src/connectors/`
- `src/database/`
- `src/models/`
- `src/processing/`
- `src/queries/`
- `tests/`

The future-state folders are still placeholders or empty:
- `src/capability/`
- `src/graph/`
- `src/rag/`
- `src/recommender/`
- `src/requirements/`
- `src/validation/`
- `config/`

## 2. Target state: planned project architecture

The target architecture is a project-centric collaborator recommendation system built on top of the validated HAL/Neo4j graph.

### Target architecture goals
- Use HAL facts as the source of truth.
- Derive inferred capability evidence from publication data.
- Extract project requirements and compare them against team capability coverage.
- Identify capability gaps.
- Rank candidate collaborators using deterministic, explainable features.
- Generate grounded explanations using evidence and explicit citation checks.

### Target layers
- factual ETL layer (already present)
- capability layer
  - `Capability` nodes
  - `EVIDENCES_CAPABILITY` edges
  - `HAS_CAPABILITY` author aggregation
- requirements layer
- recommender layer
  - gap analysis
  - candidate generation
  - feature scoring
  - ranking
- GraphRAG / explanation layer
  - evidence context
  - grounded explanation
  - fallback templates when LLM output fails

### Target principles
- Only deterministic code writes inferred graph data.
- The LLM is not the source of truth.
- Every inferred claim must carry provenance and version metadata.
- Recommendation logic must be explainable and auditable.

## 3. Drift removal rule

The repository should not describe the target architecture as if it were already implemented.

Use this rule:
- `README.md` and the live code describe the current implementation.
- `PROJECT_SPEC.md` describes the target state, architecture, and roadmap.
- this document explains the difference explicitly.

## 4. Recommended reading order

1. Read [README.md](README.md) for the current implemented system.
2. Read [docs/CURRENT_STATE_VS_TARGET_STATE.md](CURRENT_STATE_VS_TARGET_STATE.md) for the current-vs-target boundary.
3. Read [docs/PROJECT_SPEC.md](PROJECT_SPEC.md) for the planned target system and staged roadmap.

## 5. Bottom line

The current repository is a validated HAL publication ingestion and Neo4j graph pipeline.
The recommender architecture is a planned next phase, not a current implementation.

The project should keep these two realities separate in all documentation to avoid drift.
