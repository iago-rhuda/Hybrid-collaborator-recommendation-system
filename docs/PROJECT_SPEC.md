# PROJECT SPEC — Research-oriented, project-centric collaboration recommender

This document is the target-state architecture and roadmap. It is not a description of the live repository as it currently exists.

For the current implementation status, see [CURRENT_STATE_VS_TARGET_STATE.md](CURRENT_STATE_VS_TARGET_STATE.md). For repo-wide rules and Copilot behavior, see `.github/copilot-instructions.md`.

This spec is the single source of truth for the future system. If it conflicts with the current code, the future architecture is still the target, not the current reality.

---

## 1. Objective

Build a project-centric collaboration recommender on top of the existing HAL -> Neo4j research graph. It recommends researchers for a research project based on research-field relevance, capabilities (publication evidence), project requirements, capability gaps/complementarity, semantic similarity and graph evidence.

The LLM is never the decision-maker. Neo4j and deterministic ranking logic provide facts and ranking. LLM/GraphRAG is used only for structured extraction, semantic interpretation, evidence retrieval and grounded explanations.

Final question the system must answer: *"For this research project, which researchers could complement it, and why?"*

---

## 2. Repository reality (derived from the code; re-verify against the live DB in Phase 1)

Stack: Python >= 3.10, `neo4j`, `python-dotenv`, `requests` (urllib fallback). Tests: `unittest` (`PYTHONPATH=src python3 -m unittest discover -s tests`). No LangChain, pydantic, embeddings or vector index yet; check `requirements.txt` and add dependencies explicitly.
Conventions: 2-space indentation, `X | None` typing, imports relative to `src/` (`from models.author import Author`), frozen dataclasses with `to_neo4j_dict()` (camelCase keys), pure transformers in `processing/transformer.py`, parameterised MERGE-based Cypher.

### 2.1 Actual graph schema
Nodes (unique key): `Project{halId}`, `Author{halId}`, `Conference{conferenceId}`, `ResearchDomain{id}`, `Organization{halId}`.
Relationships: `(Author)-[:WROTE]->(Project)`, `(Project)-[:PRESENTED_AT]->(Conference)`, `(Project)-[:HAS_RESEARCH_DOMAIN {primary}]->(ResearchDomain)`, `(ResearchDomain)-[:SUBDOMAIN_OF]->(ResearchDomain)`, `(Project)-[:HAS_ORGANIZATION]->(Organization)`, `(Organization)-[:PART_OF]->(Organization)`.
There is **no** Author->Organization edge (HAL `struct*` fields are record-level).

### 2.2 Terminology
| Term | Meaning in this repo |
|---|---|
| Project | A **HAL publication/document** (`Project.halId`), not a funded research project |
| Person / person_id | `Author` / `Author.halId` (IdHal, or `unknown_<name>` fallback) |
| Target project | An existing `Project.halId` **or** a free-text `ProjectSpec(title, abstract, keywords)` |
| Project members | Authors linked by `WROTE` |

### 2.3 Where earlier assumptions did not match the repo
| Assumption | Reality | Resolution |
|---|---|---|
| "Project" is a research project | It is a publication | Definitions above; evaluation by leave-one-author-out |
| Author identity is reliable | IdHal or `unknown_<name>`; arrays read by position, no length guard (orgs have one); homonyms merge | Measure in Phase 1; decision D2 |
| Author AFFILIATED_WITH Organization | Not in graph; orgs link only to Project | Not used. Possible later ETL change using HAL author–structure field |
| Raw snapshots | None | New `connectors/hal_snapshot.py` wrapper writing JSONL |
| Stable pagination | `start/rows`, no `sort`, no retry, `["response"]` assumed | Snapshot twice and diff; if unstable/truncated add `sort=docid asc` and/or `cursorMark` (smallest change) |
| Data refresh | `ON CREATE SET` only; reruns never update | Report staleness; propose `SET` for scalars as a flagged change |
| Clean organization nodes | `MERGE` of parents from `structIsChildOf_fs` may create nameless nodes | Integrity check |
| `halId` always present | Falls back to `docid`, then `"Unknown"` | Count and flag |
| Abstract/journal data complete | Only first abstract kept; `journalTitle_s`, `openAccess_bool` fetched but dropped | Report; no change this week |
| README: "searches data science" | `HalClient.query` is `*:*` (whole UTC portal) | Report real `numFound` and graph contents; fix README |
| One env var set | `NEO4J_USER` vs `NEO4J_USERNAME`; `GraphQuerier` lacks defaults | Centralise in `src/config.py`, keep `NEO4J_USER` |
| Embeddings/vector store exist | None | Optional `Embedder` interface; resolution works without it |
| `config/` exists | No; `src/config.py` and `orcid_client.py` are empty | Create `config/` |
| Dublin Core review task | No DC transformer exists; doc uses `Article`/`AUTHORED` | Out of scope; optionally `docs/dublin_core_mapping.md` only |
| `Neo4jManager.save_publication_data` usable | Dead and broken | Do not call |

---

## 3. Decisions to take at kickoff (record in `docs/DECISIONS.md`)
- **D1** Project = publication. Target input = `halId` or `ProjectSpec`. Evaluation: leave-one-author-out on projects with >= 3 authors (hit@k is a sanity check, not ground truth).
- **D2** Author identity. Default: no key change unless Phase 1 shows misalignment/homonym rate above a threshold (e.g. 2% of records). If fixed: length-guarded parallel arrays like organizations; id fallback IdHal -> `person_<authIdPerson_i>` -> `unknown_<name>`; re-ingest dev subset. Owner: Member A.
- **D3** LLM and embedding providers via env vars behind interfaces; disk cache of LLM calls.
- **D4** Develop on a dev subset (500–2000 projects, one snapshot file) in a separate Neo4j database; run on full data only at Day 6–7.
- **D5** Requirements cached as JSON (`data/requirements/`), not written to Neo4j this week.
- **D6** Branch per member, PR per phase, adapter contract changes announced first.

## 4. Scope for the week
- **Must**: Phase 1 validation + report, capabilities v1 with provenance + author aggregation, requirements extraction, adapter, candidates, features, ranking, evidence, CLI demo, grounded explanation with citation check, docs.
- **Should**: leave-one-author-out evaluation, capability v2 rerun proving versioning, Dublin Core mapping doc.
- **Won't**: `ResearchGoal` nodes, `REQUIRES_CAPABILITY` in graph, author–org ETL change, API/UI, learning-to-rank, Neo4j vector index, ORCID connector.

---

## 5. Preserve the existing ETL
Before changing anything: inspect the pipeline, HAL response handling, transformer logic and Neo4j schema. Do not rewrite or substantially modify the ETL unless a concrete problem is identified; then explain why and make the smallest safe change. Only the Phase 1 owner edits ETL files.

---

## 6. Phase 1 — HAL data verification and quality layer (before any recommendation work)

Keep distinct: HAL source facts -> ETL transformations -> Neo4j graph facts -> inferred data. Never treat inferred data as source data. The validation runs independently from the recommender.

### 6.1 HAL API validation
Inspect real responses. Validate HTTP/API errors, response structure, pagination (completeness, stability), required/optional fields, types, identifiers, duplicates, missing/malformed values, dates, language, document type, authors, domains, organizations, conferences, abstracts, keywords, DOI. Do not assume optional fields are populated: **measure missingness**, do not treat it as an error.

### 6.2 Raw snapshots
`HAL API -> raw JSONL snapshot (+ manifest: query, fields, numFound, fetched count, timestamp) -> transformation -> Neo4j`. Reasonable storage (no needless duplication). Required for debugging and provenance.

### 6.3 ETL transformation validation
Compare snapshot records with Neo4j, reusing `build_csv_tables_from_hal_docs` as the expected-state oracle. Check identifier, title, abstract, keyword, author, domain, organization, conference and date preservation; relationship creation/loss; incorrect normalization; duplicate nodes. Report mismatches.

### 6.4 Neo4j integrity (Cypher, parameterised)
Duplicate identifiers, projects without authors/domains, invalid relationships, orphan domains/organizations, bare Organization nodes (no name/type), suspicious missing values, unexpected relationship multiplicity, `unknown_` authors.

### 6.5 ResearchDomain hierarchy
Check duplicate ids, orphans, cycles, inconsistent parent/child (parent must be dotted prefix of child), depth (only levels 0–2 are fetched, so expected max 3 nodes), malformed names, invalid mappings. The HAL taxonomy is authoritative: never change it to suit the recommender.

### 6.6 Data-quality report
Reproducible `reports/data_quality_<date>.md/json`: records retrieved, projects/authors/domains counts, missing abstracts/keywords/DOI/authors/domains, duplicate ids, transformation mismatches, hierarchy violations, invalid relationships.

### 6.7 Extra metrics (from the known caveats)
Author-array length mismatch rate per record (`authIdHal_s`, `authIdPerson_i`, `authFirstName_s`, ... vs `authFullName_s`); `unknown_` author share; homonym collisions; records with missing/`Unknown` halId; Organization nodes without name/type; multi-language abstracts; stale-node test (re-ingest changed snapshot and diff); `numFound` vs fetched; snapshot-vs-snapshot instability.

---

## 7. Facts vs inference
Facts (HAL/deterministic): Project title/abstract/keywords/halId, Author halId, `WROTE`, `HAS_RESEARCH_DOMAIN`, `PRESENTED_AT`, `HAS_ORGANIZATION`.
Inferred: `EVIDENCES_CAPABILITY`, `HAS_CAPABILITY` (later: `HAS_GOAL`, `REQUIRES_CAPABILITY`).
Every inferred relationship carries `inferred: true`, provenance and version.

## 8. ResearchDomain vs Capability
`ResearchDomain` = authoritative HAL taxonomy. `Capability` = inferred methods, techniques, technologies, tools, topics supported by publication evidence. Never replace one with the other or convert every domain into a capability. Kinds: DOMAIN, METHOD, TECHNIQUE, TECHNOLOGY, TOOL, TOPIC, METHODOLOGY, UNKNOWN. Wording: "publication evidence related to X", never "expert in X".

---

## 9. Phase 2 — Capability layer

### 9.1 Graph additions (constraint `capability_id` UNIQUE)
```
(:Capability {id, name, kind, aliases})       // id = deterministic slug of normalized English name
(:Project)-[:EVIDENCES_CAPABILITY {inferred, extractionVersion, extractionMethod, model,
            promptVersion, confidence, evidenceText, extractedAt}]->(:Capability)
(:Author)-[:HAS_CAPABILITY {inferred, extractionVersion, aggregationVersion, publicationCount,
            evidenceCount, avgExtractionConfidence, recentPublicationCount,
            firstSeenYear, lastSeenYear, score}]->(:Capability)
```
Identity: evidence = (project, capability, extractionVersion); author capability = (author, capability, extractionVersion, aggregationVersion). Rerunning `capability-v2` must not destroy `capability-v1`. No random or LLM-generated ids.

### 9.2 Extraction (independent, rerunnable, resumable: `--limit --version --dry-run --resume`)
Pipeline: factual graph -> extraction -> resolution -> Project->Capability evidence -> Author aggregation.
Context: title, abstract, keywords, domain hierarchy. Extract only capabilities supported by evidence; reject generic terms (research, data, analysis, study, results...) via configurable stoplist unless genuinely domain-specific; reject capabilities whose `evidence` text is absent from the input. Structured output (Pydantic): `ExtractedCapability{name, normalized_name, kind, evidence, confidence}`, `CapabilityExtractionResult{capabilities[]}`.
The corpus is fr/en: `normalized_name` is English; original surface forms go to `aliases`. Cache LLM outputs on disk keyed by (project id, prompt version, model).

### 9.3 Resolution
normalize -> exact match -> alias match -> embedding similarity (high, configurable threshold, via `Embedder` interface; optional) -> create. One node per capability, never per publication. Merge variants only with evidence; conservative with ambiguous abbreviations.

### 9.4 Provenance
Must answer: why assigned, which project/publication, which extraction version, what confidence, what supporting text. Minimum: confidence, extractionMethod, extractionVersion; also model, promptVersion, evidenceText.

### 9.5 Author aggregation
Author -> Projects -> evidence -> capability profile. No strong capability from one publication (minimum evidence in config). Track publicationCount, evidenceCount, averageExtractionConfidence, recentPublicationCount, firstSeenYear, lastSeenYear. Keep extraction confidence separate from author-level score. Deterministic, configurable aggregation; recency weighting instead of deleting history. Skip or flag `unknown_` authors.

---

## 10. Phases 3–4 — Requirements and recommendation

Pipeline: target project -> research fields -> goals/requirements -> required capabilities -> capabilities already covered by members -> **gaps = required − covered** -> candidates -> features -> deterministic ranking -> evidence -> grounded explanation.
Do not simply recommend people similar to current members. Distinguish **relevance** (works in the field), **capability** (has evidence for a required capability), **complementarity** (provides what the team lacks).

### 10.1 Requirements
`ProjectRequirements` from `ProjectSpec` or an existing project; LLM only proposes; each requirement is mapped to `ResearchDomain` ids and `Capability` ids using the resolver (unresolved ones kept by name with lower importance). Cached as JSON (D5). Fallback on LLM failure: domain-based requirements only. Goals modelled as plain strings for now.

### 10.2 Candidate generation (separate from ranking)
Combine domain matching, capability matching, similar-project evidence, co-authorship signals. Exclude current members; flag `unknown_` ids; bounded by config limits. Never LLM-selected.

### 10.3 Features (all in [0,1], pure, unit-tested)
- `gap_match`: importance-weighted share of gap capabilities the candidate has evidence for.
- `domain_relevance`: overlap between candidate's project domains (with ancestors) and the target's.
- `semantic`: similarity between candidate profile and requirement text/capabilities.
- `complementarity`: share of the candidate's relevant capabilities not already covered by the team.
- `project_similarity`: weighted Tversky/Jaccard overlap of target vs candidate's past projects (domains + capabilities; optional IC/TF-IDF weighting of rare capabilities).
- `graph`: co-authorship proximity to the team from `WROTE` (small, never dominant).
- `recency`: recency-weighted publication evidence.

### 10.4 Ranking
Deterministic and configurable (`config/ranking.yaml`), stable tie-break by person_id. Default weights (engineering defaults only): `gap_match 0.30, domain_relevance 0.15, semantic 0.15, complementarity 0.15, project_similarity 0.10, graph 0.10, recency 0.05`. Output exposes raw features, weights, weighted contributions and evidence ids. Behind an interface so a learned ranker can replace it. The LLM never ranks.

---

## 11. Phase 5 — GraphRAG / LangChain
LangChain orchestrates structured extraction, requirement extraction, retrieval, evidence-subgraph construction and explanation. The LLM is **not** the source of graph facts, the ranker, an unrestricted Cypher writer, or an authority that invents capabilities/relationships. Never expose `execute_cypher(query)`; use controlled tools only.
Explanation prompt: use only supplied evidence; do not invent skills, projects, publications, affiliations or relationships; acknowledge missing evidence. A post-check rejects any explanation citing an id absent from the supplied context and falls back to a template built from the ranking output. Handle LLM, Neo4j, missing-embedding and missing-data failures explicitly.

---

## 12. Graph abstraction and frozen contracts

Recommendation code contains no schema knowledge. Physical labels, relationships, properties and Cypher live in `src/graph/` and `config/graph_mapping.yaml`. A schema change should require changes only to the mapping, adapter queries and tests. Never assume a renamed entity has the same meaning; flag ambiguity. The LLM has no write access; inferred data is written by deterministic code (`src/capability/repository.py`).

**Adapter dataclasses** (`src/graph/adapter.py`):
```
ProjectView(project_id, title, abstract, keywords, year, doc_type)
PersonView(person_id, full_name, is_placeholder)              # placeholder = id starts with "unknown_"
DomainView(domain_id, name, parent_ids)                       # includes ancestors
PersonCapability(person_id, capability_id, name, kind, publication_count, evidence_count,
                 avg_confidence, last_seen_year, extraction_version)
RequiredCapability(capability_id | None, name, importance, source)   # extracted | user
ProjectRequirements(project_id | None, domain_ids, required_capabilities, goals, extraction_version)
ProjectSpec(title, abstract, keywords)
EvidenceItem(kind, id, text, project_id, year)                # project | domain | capability
CandidateRef(person_id, matched_domain_ids, matched_capability_ids)
```
**Methods**: `get_project`, `iter_projects(limit, offset)`, `get_project_members`, `get_project_domains`, `get_person_capabilities`, `find_candidates`, `get_candidate_evidence`, `get_coauthor_distance`. A `FakeAdapter` (in-memory, fixtures) ships on Day 2.
**Config files**: `config/graph_mapping.yaml`, `config/ranking.yaml`, `config/capability.yaml` (stoplist, thresholds, recency half-life, versions); `src/config.py` loads env + yaml.

---

## 13. Collaboration-context ontology (thesis) — inspiration only
Contextual dimensions: Goal, Collaborator, Activity, Resource, Time, Location, Relation, Satisfaction. First implementation uses Goal, Collaborator, ResearchField, Capability, Project, Time; defer the rest.
- Post-filtering (PoF) idea: cheap candidate generation, then context re-scoring -> supports "generation separate from ranking".
- `project_similarity`: weighted Tversky/Jaccard overlap (thesis Eq. 5.10). Do not port PMF or the full S1+S2 formula without showing they fit.
- `graph`: co-authorship frequency as in the thesis rating matrix. If reusing Eq. 5.8, normalise as `e / Emax` (the printed `(e−1)/(Emax−1)` is negative for e=0 and divides by zero when Emax=1).
- The thesis identifies a serendipity problem (only people from similar collaborations get recommended); gap coverage and complementarity are this project's answer.

---

## 14. Testing (unittest; mirror `src/` under `tests/`)
- **HAL validation**: malformed response, missing fields, duplicates, invalid dates, pagination, optional fields.
- **ETL**: identifier/field/relationship preservation, duplicate prevention, mismatches.
- **Graph**: duplicate nodes, broken relationships, hierarchy cycles, orphan domains, invalid organization hierarchy.
- **Capability**: valid extraction, unsupported rejection, generic-term rejection, structured-output validation, normalization, duplicate prevention.
- **Provenance**: traceability, extraction version, confidence preserved, v1 and v2 coexist.
- **Aggregation**: multiple publications, repeated evidence, recency, confidence.
- **Recommendation**: domain matching, capability matching, gap detection, complementarity, deterministic ranking, evidence retrieval.
- **Grounding**: every explanation claim traceable to supplied graph evidence; LLM-failure fallback; no Cypher exposure.

## 15. Implementation order
1. **Phase 1** inspect repo/HAL/ETL/graph; validation, integrity, first report. 2. **Phase 2** Capability model, constraint, extraction, resolution, evidence, provenance, aggregation, tests. 3. **Phase 3** requirement representation, extraction, mapping, gaps. 4. **Phase 4** candidates, features, ranking, evidence, tests. 5. **Phase 5** evidence context, grounded explanations, support check. Do not implement everything at once.

## 16. Coding-agent workflow (per phase)
Inspect existing code; explain the plan; list files to change/create; implement the smallest coherent change; run tests and validation; show changed files; report assumptions. No silent changes to unrelated components, no large rewrites without a concrete reason. When unsure about HAL or Neo4j schema, inspect real responses or the graph; never guess. Parameterise Cypher, never expose credentials, never let the LLM modify Neo4j.

## 17. Code layout
```
src/validation/    hal_validator.py, etl_compare.py, neo4j_integrity.py, hierarchy.py, report.py
src/connectors/    hal_snapshot.py
src/capability/    models.py, normalization.py, extraction.py, resolution.py, aggregation.py, repository.py
src/requirements/  models.py, extraction.py
src/graph/         adapter.py, neo4j_adapter.py, fake_adapter.py
src/recommender/   candidates.py, gaps.py, features.py, ranking.py, evidence.py, evaluation.py
src/rag/           context.py, explain.py
config/            graph_mapping.yaml, ranking.yaml, capability.yaml
docs/              PROJECT_SPEC.md, DECISIONS.md, data_flow.md, neo4j_schema.md, data_quality.md,
                   capability_semantics.md, recommendation.md
```

## 18. Required documentation
Current HAL data flow; Neo4j schema; HAL validation and data-quality metrics; ResearchDomain and Capability semantics; fact vs inference (state clearly what comes from HAL and what is inferred); extraction, provenance, author aggregation; recommendation architecture and ranking features.

## 19. Success criteria
An answer to the final question based on verified HAL data, domain evidence, publication-derived capability evidence, requirements, gaps, deterministic ranking, graph evidence and a grounded explanation. Auditable end to end:
`HAL record -> Project -> ResearchDomain / publication evidence -> Capability -> Author -> ranking feature -> final explanation`.
