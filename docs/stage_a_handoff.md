# Stage A handoff to Stage B

Stage B can begin capability/requirement implementation against the stable
Stage A contract. This handoff describes what is implemented, what is
synthetic, and which live-graph questions remain open.

**Handoff status:** the Stage A contract and documentation are available, and
the project owner reports a successful live adapter smoke test. Do not treat
the live graph as cleared for inferred-data writes yet: the 2026-10-06
integrity reports disagree, do not identify their database targets, and both
report missing uniqueness constraints.

## Stable Stage A artifacts

- Contract: [`src/graph/adapter.py`](../src/graph/adapter.py)
- Synthetic in-memory adapter: [`src/graph/fake_adapter.py`](../src/graph/fake_adapter.py)
- Neo4j fact adapter: [`src/graph/neo4j_adapter.py`](../src/graph/neo4j_adapter.py)
- Physical schema mapping: [`config/graph_mapping.yaml`](../config/graph_mapping.yaml)
- Environment and mapping loader: [`src/config.py`](../src/config.py)
- Synthetic 36-project fixture: [`tests/fixtures/dev_projects.json`](../tests/fixtures/dev_projects.json)
- Database schema notes: [`neo4j_schema.md`](neo4j_schema.md)
- HAL data flow: [`data_flow.md`](data_flow.md)
- Data-quality results and caveats: [`data_quality.md`](data_quality.md)
- Decisions and author identity D2: [`DECISIONS.md`](DECISIONS.md)
- Target architecture and inference rules: [`PROJECT_SPEC.md`](PROJECT_SPEC.md)

## Adapter contract

The four implemented Stage A fact reads are:

| Method | Meaning and source facts |
|---|---|
| `get_project(project_id)` | HAL Project fields keyed by `Project.halId`; returns `None` if absent. |
| `iter_projects(limit, offset=0)` | Bounded, stable page ordered by project ID. |
| `get_project_members(project_id)` | Authors connected by `WROTE`; `unknown_` IDs are flagged as placeholders. |
| `get_project_domains(project_id)` | Project-assigned HAL ResearchDomains and their ancestors via `SUBDOMAIN_OF`. |

The stable protocol also declares `get_project_requirements`,
`get_person_capabilities`, `find_candidates`, `get_candidate_evidence`, and
`get_coauthor_distance`. They are not implemented in Stage A. In particular,
Stage B owns capability/requirement behavior and the
`get_person_capabilities` implementation/fixtures; candidate generation and
recommendation evidence belong to Stage C.

Cypher and physical schema identifiers stay inside the graph adapter and
mapping. Capability writes must be deterministic repository code, not LLM
generated queries or writes. ResearchDomain is factual HAL taxonomy;
Capability and requirements are inferred and must carry provenance/version
metadata as specified.

## Environment and development data

Use a local `.env` with `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, and
`NEO4J_DATABASE`. Do not commit `.env`, paste credentials into documentation,
or include credential values in reports. Use the named database from the
approved dev environment; the integrity reports currently do not tie their
results to a recorded database name.

The 36-project JSON fixture is synthetic and exists for offline contract
tests. The separate D2 record documents a 1,000-HAL-record dev import and its
observed counts. Do not treat the synthetic fixture as an export of that HAL
subset.

## GitHub availability of snapshots and reports

The repository's `.gitignore` excludes `exports/` and `reports/`. HAL
snapshots and generated report files are therefore local-only and are not
included when Stage B contributors clone this repository. The aggregate
results and caveats in [`data_quality.md`](data_quality.md) are the committed
summary. Contributors needing raw records or full reports must regenerate
them locally with approved access; see that document for commands. Do not
remove the ignore rules or commit credentials/raw HAL snapshots. Share
detailed results only through an approved private channel or as a reviewed,
credential-free summary in tracked documentation.

## Verification and caveats

- Most recent recorded unit test run: **65 tests passed** with
  `PYTHONPATH=src python -m unittest discover -s tests`.
- The project owner reports that a live adapter smoke test completed
  successfully. The exact selected project and outputs were not checked in.
- Full HAL validation used 11,956/11,956 records and recorded 0 errors plus
  75,336 warnings; see [`data_quality.md`](data_quality.md).
- The two 2026-10-06 integrity reports disagree in finding totals and do not
  identify their database targets. Both report all five expected unique
  constraints missing. Confirm the Stage B dev database and capture one
  attributable baseline before inferred-data writes.
- Existing ETL uses `MERGE` and `ON CREATE SET`: matching keys prevent
  duplicate entities/relationships on rerun, but existing properties are not
  refreshed and stale nodes/edges are not deleted.

Stage B should preserve the contract and use fake adapters/fixtures in its
offline tests. Do not modify Stage A files except for a proven bug through an
approved Stage A bug-fix change.
