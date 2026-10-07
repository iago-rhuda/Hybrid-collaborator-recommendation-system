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

For every micro-step below, do the following before moving on:
1. Inspect the relevant code and confirm what is already implemented and what must be reused.
2. Explain to the member: what you inspected, what you changed, why the change is needed, and what assumption or uncertainty remains.
3. Run the smallest relevant validation and report the result.
4. If the requirement is ambiguous, the data is inconsistent, or the repo does not support the expected behavior, use the interactive AI agent to ask a precise clarifying question before proceeding.
5. Do not guess schema details or silently change unrelated code.

**A1.1 Reuse and baseline check**
> Inspect `HalClient`, `transformer.py`, `export_pipeline_csv.py`, and the current tests. List what is already implemented, what should be reused, and what is missing for Stage A. Explain the baseline to the member before writing any new code.

**A1.2 Snapshot writer**
> Create `src/connectors/hal_snapshot.py` to wrap `HalClient.fetch_publications` and write a reproducible JSONL snapshot plus a manifest containing query, requested fields, `numFound`, fetched count, and timestamp. If the HAL response structure is inconsistent, measure it first and explain the mismatch before changing code. Do not modify `HalClient` unless the issue is proven and documented.

**A1.3 HAL validation**
> Create `src/validation/hal_validator.py` to validate response structure, HTTP errors, pagination completeness, required vs optional fields, types, duplicate `halId`, missing abstract/keywords/DOI/authors/domains, malformed dates, language, `docType`, and author/organization parallel-array length mismatches. Treat missing optional values as measured data, not as failing errors. Add tests using malformed fixtures. Report to the member what each validation catches and why it matters.

**A1.4 Snapshot consistency check**
> Run the snapshot logic twice on the same query and compare outputs. Explain any drift, changes in `numFound`, missing rows, or unstable pagination. If a discrepancy appears, use the interactive agent to decide whether to inspect one more real example before proceeding with a minimal fix.

**A2.1 ETL vs Neo4j comparison**
> Create `src/validation/etl_compare.py` to compare the expected transformed state from `build_csv_tables_from_hal_docs` against the real Neo4j data. Check identifiers, titles, abstracts, keywords, authors, domains, organizations, conferences, dates, relationship counts, duplicate records, and relationship losses. Explain mismatches to the member with a clear cause hypothesis before fixing anything.

**A2.2 Integrity checks**
> Create `src/validation/neo4j_integrity.py` with parameterised Cypher checks for duplicate IDs, projects without authors or domains, orphan domains or organizations, bare `Organization` nodes, relationship multiplicity, and `unknown_` authors. Report which checks are preventive vs which are diagnostic.

**A2.3 Hierarchy validation**
> Create `src/validation/hierarchy.py` to validate domain hierarchy for cycles, orphan nodes, dotted-prefix parent rules, depth assumptions, and malformed names. Explain why the taxonomy is treated as authoritative and why no recommender logic should rewrite it.

**A2.4 Data-quality report**
> Create `src/validation/report.py` to write `reports/data_quality_<date>.md/json` with the metrics required by spec §6.6–6.7. Include counts, missingness, duplicate IDs, mismatches, and hierarchy violations. Summarize the report for the member with short, concrete conclusions and open risks.

**A2.5 Schema documentation**
> Document the discovered Neo4j schema in `docs/neo4j_schema.md` using a schema inspection command and counts from the live database. Explain what the schema proves and what remains uncertain.

**A3.1 Author-identity investigation**
> Review the data-quality report and quantify author-array misalignment, homonym collisions, and `unknown_` author rate. Explain the evidence to the member before making any ETL fix. If the numbers are ambiguous or not yet sufficient, use the interactive agent to inspect a concrete sample of records.

**A3.2 Minimal ETL fix**
> If a safe ETL fix is justified, implement the smallest possible change (for example: length-guarded parallel values or a more careful fallback order). Keep the change designed only for the measured problem and do not broaden the scope. Explain exactly why this fix is necessary and why other ETL behaviors are left unchanged.

**A3.3 Regression tests and dev subset**
> Add regression tests for the author-identity fix and re-ingest only the dev subset. Document what was changed, why the dev subset is enough for validation, and what would require a full-data rerun later.

**A4.1 Adapter contract discovery**
> Create `src/graph/adapter.py` with the required Protocol and dataclasses exactly as specified. Note which parts are fact methods and which remain future-only stubs. Explain the contract to the member before implementing the first query method.

**A4.2 Fake adapter and fixtures**
> Create `src/graph/fake_adapter.py` with fixtures containing at least ~30 projects, overlapping authors, domain hierarchy, and placeholder authors. Explain the fixture design choices and why they are sufficient for Stage A contract tests.

**A4.3 Neo4j fact methods**
> Implement `src/graph/neo4j_adapter.py` for the fact methods only (`get_project`, `iter_projects`, `get_project_members`, `get_project_domains`) using parameterised Cypher and the mapping configuration. Keep the implementation strictly limited to current database facts and explain any assumptions in plain language.

**A4.4 Config and dev data**
> Create `src/config.py` and `config/graph_mapping.yaml`, then write `tests/fixtures/dev_projects.json` from the dev subset. Explain what the config centralizes and why the mapping must stay separate from recommender logic.

**A4.5 Final Stage A validation**
> Run the relevant tests and report the results to the member: which checks passed, which failed, and what was changed to correct the issue. Only proceed to Stage B after the Stage A gate is clearly green.

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

For every micro-step below, do the following before moving on:
1. Reuse the Stage A outputs and confirm what is already stable.
2. Explain to the member: what was inspected, what was changed, why the new code is needed, and what remains to validate.
3. Keep diffs narrow and stage-scoped. Do not edit earlier-stage code unless a concrete bug is proven.
4. After each small change, run the relevant tests and report the outcome.
5. If the LLM output, config values, or Neo4j behavior is ambiguous, use the interactive AI agent to clarify or inspect a representative example before continuing.

**B1.1 Reuse Stage A contract**
> Read the Stage A adapter contract, fixtures, and graph assumptions. Confirm what can be reused for capability extraction and which parts are intentionally still unsupported. Give the member a short summary of the contract and the missing pieces before creating any new module.

**B1.2 Capability models**
> Create `src/capability/models.py` with the structured capability models and kind enum. Create `config/capability.yaml` with stoplist entries, threshold values, versioning defaults, recency settings, and minimum evidence rules. Explain why the stoplist is necessary and how the config keeps the behavior adjustable without hard-coding values.

**B1.3 Normalization**
> Implement `src/capability/normalization.py` for lowercase normalization, accent cleanup, whitespace handling, and deterministic English canonical slug generation. Add regression tests for normalization, stable IDs, and generic-term rejection. Report the specific behavior that changed and why it is needed for reliable capability merging.

**B2.1 Extraction draft**
> Implement `src/capability/extraction.py` as a structured extraction flow over title, abstract, keywords, and domain hierarchy. Explain what input context is used and why domain data is not converted into capabilities blindly. Keep the extraction logic independent of the recommender logic.

**B2.2 LLM output validation**
> Validate extraction output against malformed, unsupported, generic, and incomplete responses. Explain to the member which cases are blocked by design and how the system keeps invalid capability claims from entering the graph.

**B2.3 Cache and CLI support**
> Add disk cache keyed by project id, prompt version, and model, plus CLI flags for `--limit`, `--version`, `--dry-run`, and `--resume`. Explain why reproducibility and resumability matter for a long-running extraction pipeline.

**B3.1 Capability resolution**
> Implement `src/capability/resolution.py` with normalize → exact → alias → optional embedding similarity → create logic. Document each step and explain why conservative abbreviation handling is safer than aggressive merging.

**B3.2 Persistence layer**
> Implement `src/capability/repository.py` to write `Capability` nodes and `EVIDENCES_CAPABILITY` edges with provenance and `inferred=true` metadata. Merge only on the relevant identity tuple and explain the exact versioning strategy to the member before persisting results.

**B3.3 Unique constraint and versioning**
> Create the capability unique constraint in a stage-safe manner and verify that rerunning with a new version does not destroy or overwrite v1. Explain the test that proves v1 and v2 coexist.

**B4.1 Author aggregation design**
> Implement `src/capability/aggregation.py` to aggregate author-level capability evidence. Explain the metrics being calculated: publication count, evidence count, average confidence, recent count, and first/last seen year. Justify why extraction confidence is kept separate from author-level scoring.

**B4.2 `unknown_` handling and minimum evidence**
> Add filtering and flagging logic for placeholder authors and minimum-evidence rules. Explain to the member what this prevents and what the expected downstream behavior is.

**B4.3 Adapter capability methods**
> Implement `Neo4jAdapter.get_person_capabilities` and the corresponding fake-adapter fixture support. Explain what the adapter exposes and why this interface stays separate from raw graph details.

**B5.1 Requirements data model**
> Create the requirements models and data layout under `src/requirements/` and `data/requirements/`. Explain the difference between a project requirement and a published research domain and why they are not treated as the same object.

**B5.2 Requirement extraction**
> Implement requirement extraction from a `ProjectSpec` and/or an existing project using the adapter. The LLM only proposes; mapping to domains/capabilities must be deterministic and versioned. Explain exactly how unresolved requirements are kept lower-importance instead of being silently invented.

**B5.3 Requirement fallback**
> Add the domain-only fallback path when the LLM fails or produces unusable output. Explain why this is safe, what data is preserved, and what the system still cannot infer without evidence.

**B5.4 Stage B validation**
> Run the Stage B test set, then report the results to the member: what passed, what failed, what changed, and why the fix was necessary. Only continue once the gate is green.

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

**Gate 3 = Definition of done (COMPLETED)**
- [x] `unittest` green; validation CLI runs independently of the recommender.
- [x] Recommendation output shows features, weights, contributions, evidence ids.
- [x] Every explanation sentence traces to supplied evidence ids; unknown ids rejected; LLM failure falls back to template.
- [x] Capabilities carry provenance; v1/v2 coexistence documented.
- [x] Docs state what comes from HAL vs what is inferred.
- [x] Demo script runs on a real project.

### Copilot prompts — Stage C

For every micro-step below, do the following before moving on:
1. Start from the validated Stage A/B outputs and explicitly list what is reused.
2. Explain to the member: what was inspected, what changed, why the change is needed, and which assumptions remain open.
3. Keep the work stage-scoped; do not silently change earlier modules.
4. After each small change, run the relevant tests and report the outcome.
5. If the ranking logic, explanation evidence, or LLM output is ambiguous, use the interactive AI agent to inspect the exact evidence and ask a tight clarifying question before proceeding.

**C1.1 Reuse Stage A/B contracts**
> Review the fact adapter, capability layer, and requirement outputs from earlier stages. Confirm what is safe to reuse, what is still missing, and how the ranker should depend only on the stable interfaces. Explain the reuse plan to the member before writing any code.

**C1.2 Gap computation**
> Implement `src/recommender/gaps.py` to compute required minus covered capabilities, weighted by importance, using `ProjectRequirements` and members’ `PersonCapability` data. Explain the logic in plain terms: what counts as a gap, what counts as already covered, and why the current team is excluded from being treated as a candidate.

**C1.3 Candidate generation**
> Implement `src/recommender/candidates.py` using adapter data to find candidate researchers by domain and capability overlap while excluding current members and flagging placeholder IDs. Keep the search bounded by config limits and explain the reason for the cutoff.

**C1.4 Adapter methods for candidate search**
> Implement the remaining adapter methods (`find_candidates`, `get_candidate_evidence`, `get_coauthor_distance`) with parameterised Cypher and explain which graph facts they rely on. Add focused tests on FakeAdapter fixtures covering empty gaps, missing capabilities, and placeholder authors.

**C2.1 Feature definitions**
> Implement `src/recommender/features.py` with the seven required features: `gap_match`, `domain_relevance`, `semantic`, `complementarity`, `project_similarity`, `graph`, and `recency`. Document each formula in the docstrings and explain the purpose of each feature to the member before validating the math.

**C2.2 Feature tests**
> Add per-feature unit tests, including missing-data handling and one case where the most similar person is not the best complement. Explain the failure mode and why complementarity matters more than raw similarity in some cases.

**C3.1 Ranking design**
> Implement `src/recommender/ranking.py` and read `config/ranking.yaml` to compute the weighted score. Make the ranker deterministic, with a stable tie-break on `person_id`, and expose raw features, weights, contributions, and supporting evidence IDs. Explain how the weights map to the specification and why the output must be auditable.

**C3.2 Evidence retrieval**
> Implement `src/recommender/evidence.py` to fetch per-candidate evidence and package it for ranking output. Explain which evidence is necessary for a defensible recommendation and which parts are only supportive context.

**C3.3 CLI and evaluation**
> Add `src/recommend_cli.py` and `evaluation.py` for project-based recommendation and leave-one-author-out evaluation on projects with at least three authors. Report the evaluation logic to the member and explain how hit@k is being used as a sanity check, not as ground truth.

**C3.4 Ranking validation**
> Run deterministic ranking tests and a weight-change check. Explain to the member whether the new ordering matches the intended prioritization and why that is or is not expected.

**C4.1 Evidence-context builder**
> Implement `src/rag/context.py` to collect and limit the candidate evidence subgraph according to config. Explain which IDs are included and why the context must be bounded to avoid noisy or irrelevant evidence.

**C4.2 Explanation generation**
> Implement `src/rag/explain.py` with the grounded explanation flow. The prompt must instruct the model to use only supplied evidence and must forbid invented skills, projects, affiliations, or relationships. Explain to the member what the LLM is allowed to say and what is intentionally blocked.

**C4.3 Citation validation**
> After generation, verify every cited ID is present in the supplied context. If a citation is unknown, discard it and fall back to a template explanation derived from the ranking output. Explain the reasoning behind this safeguard and why it prevents hallucinated recommendations.

**C4.4 LLM failure handling**
> Add failure paths for missing LLM output, missing embeddings, missing data, and Neo4j errors. Explain what fallback behavior is expected and how the system preserves user trust even when the assistive component fails.

**C5.1 Final validation run**
> Run the full validation CLI and report the outputs for the database or dev subset. Explain what was checked and what the result means for the final recommendation system.

**C5.2 Final documentation update**
> Update `docs/recommendation.md`, `data_flow.md`, `capability_semantics.md`, and the README so they describe the correct current state, including query scope and env configuration. Explain what changed and why the docs must remain aligned with the actual implementation.

**C5.3 Demo script and final gate review**
> Write the demo script and run the final Stage C review against the definition of done. Report the final status to the member in a short checklist: what is implemented, what is validated, what remains intentionally out of scope, and what assumptions still need human confirmation.

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
