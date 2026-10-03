# Copilot Instructions — Project-centric collaboration recommender

> Place at `.github/copilot-instructions.md`.
> Companion document: `docs/PROJECT_SPEC.md` (single spec). **If they conflict, the spec wins.**

## 1. Repository reality (derived from the code; re-verify against the live DB in Phase 1)

Stack: Python >= 3.10, `neo4j` driver, `python-dotenv`, `requests` (urllib fallback).
Tests: `unittest` -> `PYTHONPATH=src python3 -m unittest discover -s tests`.
No LangChain, pydantic, embeddings or vector index exist yet. Check `requirements.txt` and add new dependencies explicitly.

Conventions (follow them):
- 2-space indentation, type hints, `from __future__`-free Python 3.10 syntax (`X | None`).
- Top-level imports relative to `src/` (`from models.author import Author`).
- Models are `@dataclass(frozen=True)` with `to_neo4j_dict()` returning camelCase keys.
- Transformers are pure functions in `processing/transformer.py`.
- Cypher is parameterised and MERGE-based. Use `unittest`, not pytest.

### Actual graph schema (from `neo4j_manager.py`)
Nodes (unique key): `Project{halId}`, `Author{halId}`, `Conference{conferenceId}`, `ResearchDomain{id}`, `Organization{halId}`.
Relationships: `(Author)-[:WROTE]->(Project)`, `(Project)-[:PRESENTED_AT]->(Conference)`,
`(Project)-[:HAS_RESEARCH_DOMAIN {primary}]->(ResearchDomain)`, `(ResearchDomain)-[:SUBDOMAIN_OF]->(ResearchDomain)`,
`(Project)-[:HAS_ORGANIZATION]->(Organization)`, `(Organization)-[:PART_OF]->(Organization)`.
There is **no** Author->Organization edge (HAL struct fields are record-level).

### Terminology (do not confuse)
| Term in specs | Meaning in this repo |
|---|---|
| Project | A **HAL publication/document** (`Project.halId`), not a funded research project |
| Person / person_id | `Author` / `Author.halId` (IdHal, or `unknown_<name>` fallback — unreliable, see caveats) |
| Target project | Either an existing `Project.halId`, or a free-text `ProjectSpec(title, abstract, keywords)` |
| Project members | Authors linked by `WROTE` |

### Known ETL caveats (do NOT silently "fix"; measure first, then make the smallest change and explain it)
1. `extract_authors_from_hal_record` reads `authIdHal_s` / `authIdPerson_i` etc. **by position** against `authFullName_s` with no length check (organizations use `_get_parallel_value`, authors do not). Possible misalignment.
2. Author fallback id `unknown_<fullName>` merges homonyms and splits the same person across records.
3. Persistence uses `ON CREATE SET`: re-running never refreshes existing nodes.
4. `MERGE` of parent organizations in `structIsChildOf_fs` can create Organization nodes without name/type.
5. `HalClient` pages with `start/rows` and no `sort`; no retry; `["response"]` assumed present; `HalClient.query` defaults to `*:*` while the README says "data science".
6. `halId` falls back to `docid`, then `"Unknown"`.
7. Only the first abstract is kept; `journalTitle_s` and `openAccess_bool` are fetched but dropped.
8. `NEO4J_USER` vs `NEO4J_USERNAME` in README; `GraphQuerier` has no env defaults.
9. `Neo4jManager.save_publication_data` is a dead, broken wrapper. Do not call it.

## 2. Critical rules
- Never assume a generic Neo4j schema. Never invent labels, relationships, properties or IDs.
- Do not rewrite working ETL. ETL edits are allowed only for a concrete, documented problem, and only by the owner of Phase 1.
- Facts vs inference: HAL/ETL data is fact. Everything the system derives is inference and must carry `inferred: true`, `extractionVersion`, `extractionMethod`, `confidence` and, where relevant, `model`, `promptVersion`, `evidenceText`. Never overwrite older versions.
- `ResearchDomain` (HAL taxonomy, authoritative) is separate from `Capability` (inferred). Do not convert domains into capabilities. Do not change the taxonomy.
- Wording: "publication evidence related to X", never "expert in X".

## 3. Architecture and responsibilities
```
HAL API -> raw snapshot (JSONL) -> transformer -> Neo4j (facts)
Neo4j -> capability extraction -> resolution -> Project->Capability evidence -> Author aggregation (inferred)
Target project -> requirements -> gaps -> candidates -> features -> ranking -> evidence -> grounded explanation
```
- ETL creates the factual graph. Neo4j is the source of truth.
- **Graph adapter** (`src/graph/`) is the only place with labels, relationship names, property names and Cypher. Mapping lives in `config/graph_mapping.yaml`. Recommendation code uses only the stable interface: `get_project`, `get_project_members`, `get_project_domains`, `get_project_requirements`, `get_person_capabilities`, `find_candidates`, `get_candidate_evidence`, `get_coauthor_distance`.
- Writes of inferred data happen in deterministic code (`src/capability/repository.py`), never by the LLM. The LLM gets no write access and no free-form Cypher.
- The LLM may only: extract structured capabilities/requirements, and write grounded explanations. It never ranks or selects candidates.
- A schema change should require changing only `graph_mapping.yaml`, adapter queries and tests. Flag semantic ambiguity instead of assuming renamed things mean the same.

## 4. Capability layer
- `(:Capability {id, name, kind, aliases})`, `id` = deterministic slug of the normalized English name, UNIQUE constraint. No random or LLM-generated ids.
- `(:Project)-[:EVIDENCES_CAPABILITY {inferred, extractionVersion, extractionMethod, model, promptVersion, confidence, evidenceText, extractedAt}]->(:Capability)`; identity = (project, capability, extractionVersion).
- `(:Author)-[:HAS_CAPABILITY {inferred, extractionVersion, aggregationVersion, publicationCount, evidenceCount, avgExtractionConfidence, recentPublicationCount, firstSeenYear, lastSeenYear, score}]->(:Capability)`.
- Corpus is bilingual (fr/en): `normalized_name` is English; original surface forms go to `aliases`.
- Resolution order: normalize -> exact -> alias -> embedding similarity above a high, configurable threshold -> else create. Be conservative with abbreviations.
- Reject generic terms (research, data, analysis, study, results...) via a configurable stoplist; reject capabilities whose `evidence` text is not found in the input text.
- Cache LLM outputs on disk keyed by (project id, prompt version, model) so reruns are reproducible and cheap.
- Extraction must be independently rerunnable and resumable (`--limit`, `--version`, `--dry-run`).

## 5. Recommendation principles
Pipeline: target project -> requirements -> covered capabilities (from members) -> **gaps = required − covered** -> candidates -> features -> deterministic ranking -> evidence -> explanation.
Do not assume the most similar person is the best collaborator. Exclude current members. Flag candidates with `unknown_` ids.

Features (all in [0,1], each unit-tested):
- `gap_match`: importance-weighted share of gap capabilities the candidate has evidence for.
- `domain_relevance`: overlap of candidate's project domains (with ancestors) and the target's domains.
- `semantic`: similarity between candidate capability profile and requirement text/capabilities.
- `complementarity`: share of candidate's relevant capabilities **not** already covered by the team (penalises redundancy).
- `project_similarity`: weighted Tversky/Jaccard overlap between target and candidate's past projects (domains + capabilities).
- `graph`: co-authorship proximity to the team from `WROTE` (small, never dominant).
- `recency`: recency-weighted publication evidence.

Default weights (engineering defaults, in config, not code):
`gap_match 0.30, domain_relevance 0.15, semantic 0.15, complementarity 0.15, project_similarity 0.10, graph 0.10, recency 0.05`.
Ranking output must expose raw features, weights, weighted contributions and the evidence ids. Keep the scorer behind an interface so a learned ranker can replace it.

## 6. GraphRAG / LangChain
LangChain orchestrates structured extraction and explanation only. The explanation prompt must say: use only supplied evidence; do not invent skills, projects, publications, affiliations or relationships; state missing evidence explicitly. Every claim in an explanation must cite an evidence id (HAL id, domain id, capability id) that exists in the supplied context; a post-check rejects explanations citing unknown ids.
Handle LLM failure, Neo4j failure, missing embeddings and missing data with explicit, tested fallbacks (explanation falls back to a template built from the ranking output).

## 7. Safety
Parameterised Cypher only. No credentials in code or logs. Configurable retrieval limits. Tests before declaring done.

## 8. New code layout (do not scatter)
```
src/validation/    hal_validator.py, snapshot comparison, neo4j_integrity.py, hierarchy.py, report.py
src/connectors/hal_snapshot.py
src/capability/    models.py, extraction.py, resolution.py, aggregation.py, repository.py
src/requirements/  models.py, extraction.py
src/graph/         adapter.py (Protocol+dataclasses), neo4j_adapter.py, fake_adapter.py
src/recommender/   candidates.py, gaps.py, features.py, ranking.py, evidence.py
src/rag/           context.py, explain.py
config/            graph_mapping.yaml, ranking.yaml, capability.yaml
docs/              data_flow.md, neo4j_schema.md, data_quality.md, capability_semantics.md, recommendation.md
tests/             mirrors src/
```

## 9. Workflow for every task
1. Inspect existing code; say what will be reused. 2. List files to change/create. 3. Implement the smallest coherent change. 4. Run `unittest` and the relevant validation. 5. Show changed files and assumptions. 6. Touch only files owned by the current task; never silently modify unrelated components or duplicate existing functionality.
