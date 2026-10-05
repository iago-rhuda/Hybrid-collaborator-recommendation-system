# One-week plan — 3 members, sequential relay (A -> B -> C)

Each member owns one **self-contained stage**. A stage starts from a **handoff pack** produced by the previous member and ends with its own handoff pack. Nobody works on someone else's stage; nobody blocks mid-stage waiting for a question.

```
 Day 1-2 (+ morning 3)        Day 3-4 (+ morning 5)           Day 5-7
 ┌──────────────────┐   G1   ┌──────────────────────┐   G2   ┌─────────────────────────┐
 │ A: DATA FOUNDATION│ ─────▶ │ B: SEMANTIC LAYER     │ ─────▶ │ C: RECOMMENDER + RAG     │
 │ verified HAL data │        │ capabilities+require- │        │ gaps, candidates, rank,  │
 │ + graph adapter   │        │ ments, in the graph   │        │ explanation, demo, docs  │
 └──────────────────┘        └──────────────────────┘        └─────────────────────────┘
```

Setup (Day 1, all, ~2h, then A starts alone): copy `copilot-instructions.md` -> `.github/`, `PROJECT_SPEC.md` -> `docs/`. Take decisions D1–D6 (spec §3) and write `docs/DECISIONS.md`. Create branches `stage-a`, `stage-b`, `stage-c` (B branches from A's merged result, C from B's).

While waiting (B on Days 1–2, C on Days 1–4): onboarding only — read the spec, set up `.env`/keys/Neo4j access, run the existing tests, read the stage prompts. No code in the repo, so no conflicts.

## Rules of the relay
1. **Gate = merge.** A stage is finished only when its gate checklist is green, the PR is merged to `main`, and the handoff pack is committed. The next member starts from `main`.
2. **Frozen after handoff.** Earlier stages' code changes only via bug-fix PR approved by its author. Public signatures in `src/graph/adapter.py` are frozen after Gate 1: later stages *implement* methods, they never rename or change them.
3. **Fixtures guarantee independence.** Every stage commits fixtures (JSON) so the next stage can run its tests without Neo4j, an LLM key, or the previous member online.
4. **Slip rule.** If a stage is late at the end of its buffer morning, hand over what is green plus the fixtures, and move the unfinished item to the "Should" list (spec §4). Never cut tests or provenance.
5. **Review.** The next-stage member reviews the previous stage's PR (it is their entrance exam); the previous member reviews nothing later.

---

## STAGE A — Data foundation (Day 1–2, buffer morning 3)

**Goal:** the factual graph is verified and measured, and everything downstream can read it through a stable interface.

**Owns:** `src/validation/`, `src/connectors/hal_snapshot.py`, ETL files (only if a measured problem justifies it), `src/graph/adapter.py`, `fake_adapter.py`, `neo4j_adapter.py` (fact methods), `src/config.py`, `config/graph_mapping.yaml`, `docs/data_flow.md`, `neo4j_schema.md`, `data_quality.md`, `DECISIONS.md`.

**Deliverables**
1. HAL JSONL snapshot + manifest; validator CLI that runs without Neo4j.
2. ETL-vs-Neo4j comparison, Neo4j integrity checks, hierarchy checks, first quality report (all spec §6 metrics).
3. Decision D2 (author identity) taken from measured numbers; minimal ETL fix + regression tests only if needed; dev subset loaded in the dev Neo4j DB.
4. Graph adapter: Protocol + dataclasses for **all** methods (spec §12), `FakeAdapter`, and a real `Neo4jAdapter` implementing the **fact** methods (`get_project`, `iter_projects`, `get_project_members`, `get_project_domains`). Other methods raise `NotImplementedError` with a clear message.
5. `src/config.py` (env vars + yaml loader), `config/graph_mapping.yaml`.

**Gate 1 -> B (all must be true)**
- [ ] `unittest` green; validator and report run end to end.
- [ ] `reports/data_quality_<date>.md` committed; author-identity decision written in `DECISIONS.md`.
- [ ] Dev DB loaded and documented (URI placeholder, counts, how to reload).
- [ ] `tests/fixtures/dev_projects.json` (~30 projects with authors, domains with ancestors, year) committed.
- [ ] Adapter contract tests pass for `FakeAdapter` and `Neo4jAdapter` fact methods.

**Handoff pack:** merged PR, report, `docs/neo4j_schema.md`, fixtures, dev DB access notes.

### Copilot prompts — Stage A
**A1 Snapshot + HAL validation**
> Inspect `HalClient`, `transformer.py`, `export_pipeline_csv.py`. Create `src/connectors/hal_snapshot.py` wrapping `HalClient.fetch_publications` to write a reproducible JSONL snapshot (`data/snapshots/hal_<date>.jsonl`) plus manifest (query, fields, numFound, fetched count, timestamp). Do not modify `HalClient` unless a problem is proven (snapshot twice and diff; compare numFound vs fetched). Create `src/validation/hal_validator.py` for response structure/HTTP errors, pagination completeness, required vs optional fields, types, duplicate halId, missing abstract/keywords/DOI/authors/domains, malformed dates, language, docType, and parallel-array length mismatches for authors and organizations. Missing optional values are measured, not errors. Tests with malformed fixtures. CLI must run without Neo4j.

**A2 ETL + Neo4j validation + report**
> Create `src/validation/etl_compare.py` (reuse `build_csv_tables_from_hal_docs` as expected state vs Neo4j: ids, title, abstract, keywords, authors, domains, orgs, conferences, dates, relationship counts/losses, duplicates), `neo4j_integrity.py` (parameterised Cypher: duplicate ids, projects without authors/domains, orphan domains/orgs, bare Organization nodes, relationship multiplicity, `unknown_` authors), `hierarchy.py` (cycles, orphans, dotted-prefix parent rule, depth <= 3, malformed names) and `report.py` writing `reports/data_quality_<date>.md/json` with all spec §6.6–6.7 metrics. Document the discovered schema in `docs/neo4j_schema.md` using `db.schema.visualization()` and counts.

**A3 Author identity + dev load**
> From the report quantify author-array misalignment and homonym/`unknown_` collisions. Propose the smallest safe ETL change (length-guarded parallel values for authors, id fallback order) with justification, add regression tests, and re-ingest only the dev subset. Change nothing else in the ETL.

**A4 Contracts + adapter**
> Create `src/graph/adapter.py` (Protocol + frozen dataclasses exactly as in spec §12, all methods), `fake_adapter.py` with fixtures (>= 30 projects, overlapping authors, domain hierarchy, a few placeholder authors), `src/config.py` and `config/graph_mapping.yaml`, and `neo4j_adapter.py` implementing the fact methods with parameterised Cypher using only the mapping. Contract tests run against both adapters. Write `tests/fixtures/dev_projects.json` from the dev DB.

---

## STAGE B — Semantic layer (Day 3–4, buffer morning 5)

**Goal:** capabilities and project requirements exist in the graph / cache, versioned and traceable.

**Starts from:** Gate 1 pack. B never edits Stage A code except bug-fix PRs.

**Owns:** `src/capability/`, `src/requirements/`, `config/capability.yaml`, `docs/capability_semantics.md`, capability methods in `neo4j_adapter.py` (`get_person_capabilities`), `data/requirements/`.

**Deliverables**
1. Pydantic models, normalization, stoplist config.
2. LangChain extraction (disk cache, `--limit --version --dry-run --resume`), `capability-v1` run on the dev subset.
3. Resolution (exact/alias/optional embedding) and repository writing `Capability`, `EVIDENCES_CAPABILITY` with full provenance; constraint `capability_id`.
4. Author aggregation -> `HAS_CAPABILITY`; versioning proven by a `capability-v2` mini-run that leaves v1 intact.
5. Requirements extraction (`ProjectSpec` or `halId` -> `ProjectRequirements`, mapped to domains/capabilities, JSON cache, domain-only fallback on LLM failure).
6. `Neo4jAdapter.get_person_capabilities` and `FakeAdapter` capability fixtures.

**Gate 2 -> C (COMPLETED)**
- [x] `unittest` green without LLM key or Neo4j (fake LLM, fake adapter).
- [x] Dev DB contains capabilities v1 with provenance; manual review of ~30 projects recorded in `docs/capability_semantics.md` (precision notes, stoplist tuning).
- [x] v1 and v2 coexist (test).
- [x] `tests/fixtures/capabilities.json` and `tests/fixtures/requirements.json` committed (>= 10 projects each).
- [x] 3 example `ProjectRequirements` JSON files in `data/requirements/examples/`.
- [x] Cost/time note: how to run the full extraction and how long it took on the dev subset.


**Handoff pack:** merged PR, fixtures, examples, capability docs, instructions to run the full extraction (C launches it in the background on Day 5).

### Copilot prompts — Stage B
**B1 Models + normalization**
> Create `src/capability/models.py` (Pydantic `ExtractedCapability{name, normalized_name, kind, evidence, confidence}`, `CapabilityExtractionResult`, kind enum DOMAIN/METHOD/TECHNIQUE/TECHNOLOGY/TOOL/TOPIC/METHODOLOGY/UNKNOWN), `config/capability.yaml` (stoplist, thresholds, versions, recency half-life, minimum evidence) and `normalization.py` (lowercase, accents, whitespace, English canonical slug -> deterministic `id`). Add dependencies to requirements. Tests: normalization, deterministic ids, generic-term rejection.

**B2 Extraction**
> Implement `extraction.py`: LangChain chain over title + abstract + keywords + domain hierarchy (via adapter `iter_projects`/`get_project_domains`; FakeAdapter in tests). Corpus is fr/en: English `normalized_name`, original term kept as alias. Reject capabilities whose `evidence` is not in the input text. Do not convert domains to capabilities. Disk cache keyed by (project id, prompt version, model). CLI flags `--limit --version --dry-run --resume`. Tests with a fake LLM: valid, unsupported, generic, malformed output.

**B3 Resolution + persistence**
> Implement `resolution.py` (normalize -> exact -> alias -> embedding similarity above configurable threshold via an `Embedder` interface -> create; conservative on abbreviations) and `repository.py` writing `Capability` nodes and `EVIDENCES_CAPABILITY` with `inferred=true` and all provenance properties, MERGE on (project, capability, extractionVersion). Create constraint `capability_id` from this module (do not edit `neo4j_manager.py`). Tests: duplicate prevention, variants merge, ambiguity not merged, rerun with v2 keeps v1.

**B4 Aggregation + adapter**
> Implement `aggregation.py`: Author -> Projects -> evidence -> `HAS_CAPABILITY` with publicationCount, evidenceCount, avgExtractionConfidence, recentPublicationCount, firstSeenYear, lastSeenYear and configurable recency-weighted `score`. Minimum evidence from config; skip/flag `unknown_` authors; keep extraction confidence separate from author score. Implement `Neo4jAdapter.get_person_capabilities` and FakeAdapter data. Tests: multiple publications, repeated evidence, recency, confidence, versions.

**B5 Requirements**
> In `src/requirements/` implement extraction of `ProjectRequirements` from a `ProjectSpec` or an existing project via the adapter. LLM only proposes; map each requirement to `ResearchDomain` ids and `Capability` ids with the B3 resolver (unresolved ones kept by name, lower importance). Cache in `data/requirements/`. Tests: structured-output validation, generic/unsupported rejection, domain mapping, LLM-failure fallback.

---

## STAGE C — Recommender and explanation (Day 5–7)

**Goal:** end-to-end "project in, ranked and explained collaborators out", on full data.

**Starts from:** Gate 2 pack. Day 5 morning: launch the full-data capability extraction in the background using B's instructions, while building on dev DB/fixtures.

**Owns:** `src/recommender/`, `src/rag/`, `src/recommend_cli.py`, `config/ranking.yaml`, `docs/recommendation.md`, remaining adapter methods (`find_candidates`, `get_candidate_evidence`, `get_coauthor_distance`), final docs and README fixes.

**Deliverables**
1. `gaps.py`, `candidates.py`, `features.py` (7 features), `ranking.py` (config weights, explainable output), `evidence.py`.
2. `recommend_cli.py --project-id | --title/--abstract/--keywords --top-k`.
3. `evaluation.py` leave-one-author-out hit@k.
4. GraphRAG `context.py` + `explain.py` with citation check and template fallback.
5. Full-data run: rerun A's validation/report, final quality report; final docs; README corrected (query scope, env vars).

**Gate 3 = Definition of done**
- [ ] `unittest` green; validation CLI runs independently of the recommender.
- [ ] Recommendation output shows features, weights, contributions, evidence ids.
- [ ] Every explanation sentence traces to supplied evidence ids; unknown ids rejected; LLM failure falls back to template.
- [ ] Capabilities carry provenance; v1/v2 coexistence documented.
- [ ] Docs state what comes from HAL vs what is inferred.
- [ ] Demo script runs on a real project.

### Copilot prompts — Stage C
**C1 Gaps + candidates**
> In `src/recommender/` implement `gaps.py` (required − covered capabilities, importance-weighted, from `ProjectRequirements` and members' `PersonCapability`) and `candidates.py` (domain/capability match through the adapter, excludes members, flags placeholder ids, bounded by config limits). Implement `Neo4jAdapter.find_candidates`, `get_candidate_evidence`, `get_coauthor_distance` with parameterised Cypher via the mapping. Tests on FakeAdapter fixtures, including empty gaps and missing capabilities.

**C2 Features**
> Implement `features.py` with the 7 features in spec §10.3 as pure functions in [0,1] (`gap_match`, `domain_relevance`, `semantic`, `complementarity`, `project_similarity` as weighted Tversky overlap, `graph` from co-author distance, `recency`). Document each formula in docstrings. Tests per feature, including missing data, and one case where the most similar person is not the best complement.

**C3 Ranking, evidence, CLI, evaluation**
> Implement `ranking.py` reading `config/ranking.yaml` (default weights in spec §10.4): deterministic weighted score, stable tie-break by person_id, output with raw features, weights, contributions and evidence ids; scorer behind an interface. `evidence.py` retrieves per-candidate evidence. Add `src/recommend_cli.py` and `evaluation.py` (leave-one-author-out on projects with >= 3 authors, hit@k). Tests: determinism, weight-change effect, evidence retrieval.

**C4 GraphRAG**
> In `src/rag/` build `context.py` (evidence subgraph limited by config) and `explain.py` (LangChain; prompt rules from spec §11). After generation, verify every cited id exists in the supplied context; otherwise discard and use a template explanation built from the ranking output. Tests: no invented ids, missing evidence acknowledged, LLM failure fallback, no Cypher exposed to the LLM.

**C5 Final run + docs**
> Run the validation CLI and report on the full database, run evaluation, and update `docs/recommendation.md`, `data_flow.md`, `capability_semantics.md` and README (correct query scope and env vars). Write the demo script.

---

## Start of every Copilot session (paste first)
> Read `.github/copilot-instructions.md` and `docs/PROJECT_SPEC.md` (the spec wins on conflicts). Follow repo conventions (2-space indent, unittest, frozen dataclasses, imports relative to `src/`). First inspect the existing code and propose a plan: what you reuse, files to create/modify. Wait for my OK, then implement in small steps, run `PYTHONPATH=src python3 -m unittest discover -s tests` after each step, and list changed files and assumptions. I am working on **Stage <A|B|C>**; only touch the files that stage owns.

## Timeline summary
| Day | A | B | C |
|---|---|---|---|
| 1 | Setup meeting, A1 | onboarding | onboarding |
| 2 | A2, A3, A4 | onboarding | onboarding |
| 3 | buffer morning, **Gate 1** | B1, B2 (starts after Gate 1) | onboarding |
| 4 | free (reviews B's PRs, helps with manual review) | B3, B4 | onboarding |
| 5 | free | B5, buffer morning, **Gate 2** | C1; launch full extraction |
| 6 | free | free (answers C's bug reports) | C2, C3 |
| 7 | free | free | C4, C5, demo, **Gate 3** |

Free days are not wasted: the member who has finished reviews the next stage's PRs, fixes bugs in their own stage, and prepares the demo data. If a stage ends early, hand over early.
