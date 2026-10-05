# Capability Semantics and Validation Report

## 1. Overview and Semantics

The semantic layer (Stage B) elevates raw publication metadata into structured, versioned, and traceable capabilities associated with publications and authors.

### 1.1 Capability Kinds
Extracted capabilities are categorized into 8 kinds (`CapabilityKind`):
- `METHOD`: High-level scientific methods and paradigms (e.g., *Transformer Architecture*, *Monte Carlo Simulation*).
- `TECHNIQUE`: Concrete algorithmic techniques (e.g., *Gradient Boosting*, *Attention Mechanism*).
- `TECHNOLOGY`: Platforms, runtimes, hardware, or ecosystems (e.g., *CUDA*, *Docker*).
- `TOOL`: Specific software tools, frameworks, and libraries (e.g., *PyTorch*, *Neo4j*).
- `TOPIC`: Focused research themes (distinct from broad disciplinary domains; e.g., *Federated Learning*, *Explainable AI*).
- `METHODOLOGY`: Experimental and evaluation protocols (e.g., *Leave-One-Out Cross-Validation*).
- `DOMAIN`: Specialized subdomains when acting as a competence.
- `UNKNOWN`: Fallback for ambiguous terms.

### 1.2 Normalization and Identity
- **Canonical normalization (`normalize`)**: Strips accents, forces lowercase, collapses punctuation and whitespace into single spaces.
- **Deterministic ID (`to_capability_id`)**: Replaces spaces with underscores to produce safe slug IDs (e.g. `transformer_architecture`).
- **Surface forms and aliases**: Non-English forms (French/English bilingual corpus) and variants (e.g., acronyms like *NLP*) are linked as aliases rather than duplicate nodes.

---

## 2. Manual Review of Dev Subset (~30 Projects)

A manual review was performed on the dev subset (`tests/fixtures/dev_projects.json`, 30 representative projects spanning computer science, AI, computational biology, and signal processing).

### Sample Extraction and Precision Evaluation

| Project ID | Title Excerpt | Extracted Capabilities | Kinds | Precision Assessment |
|---|---|---|---|---|
| `hal-001` | *Cross-Lingual Information Retrieval using Transformer Architecture* | `Transformer Architecture`, `Natural Language Processing` | METHOD, TOPIC | **High (1.00)** — Exact alignment with title/abstract; evidence present. |
| `hal-002` | *Robust Optimization for Microgrid Energy Management* | `Robust Optimization`, `Mixed-Integer Linear Programming` | METHOD, TECHNIQUE | **High (1.00)** — Mathematical methods cleanly separated from energy domain. |
| `hal-003` | *Privacy-Preserving Collaborative Learning Across Edge Devices* | `Federated Learning`, `Differential Privacy` | TOPIC, TECHNIQUE | **High (1.00)** — Core privacy and distributed algorithms extracted. |
| `hal-004` | *Deep Learning for Medical Image Segmentation* | `Deep Learning`, `Convolutional Neural Networks` | METHOD, TECHNIQUE | **High (1.00)** — Medical domain kept as research domain; algorithms as capabilities. |
| `hal-005` | *Distributed Consensus in Heterogeneous Multi-Agent Networks* | `Multi-Agent Systems`, `Consensus Algorithm` | TOPIC, METHOD | **High (1.00)** — Clear methodological distinction. |

### Stoplist Tuning Notes
During initial runs, generic academic vocabulary leaked through (e.g., *"research"*, *"data analysis"*, *"system performance"*, *"framework"*). The stoplist in `config/capability.yaml` was tuned and the normalization logic was augmented to:
1. Reject exact matches against canonical stop words.
2. Reject compound phrases where all tokens are stop words (e.g., *"Data Analysis"*, *"System Evaluation"*).
3. Require verbatim evidence in the input publication text.

---

## 3. Provenance and Coexistence (v1 & v2)

All inferred knowledge in Neo4j contains explicit provenance properties:
- `(:Project)-[r:EVIDENCES_CAPABILITY]->(:Capability)` carries:
  - `inferred: true`
  - `extractionMethod: "llm"`
  - `extractionVersion: "capability-v1"`
  - `model: "gpt-4o-mini"`
  - `promptVersion: "prompt-v1"`
  - `confidence: float`
  - `evidenceText: string`
  - `extractedAt: ISO-8601 timestamp`

### Version Coexistence
`EVIDENCES_CAPABILITY` and `HAS_CAPABILITY` are keyed by their respective extraction/aggregation version attributes:
- Multiple versions (e.g. `capability-v1` and `capability-v2`) coexist as distinct edges in the graph.
- Existing v1 evidence is never overwritten or destroyed by newer runs.
- Tested and verified in `tests/test_capability.py::TestCapabilityRepositoryAndCoexistence`.

---

## 4. Author Capability Aggregation Rules

Aggregating publication evidence to author competencies (`HAS_CAPABILITY`) obeys:
1. **Recency decay**: Configurable half-life ($t_{1/2} = 5$ years by default). A publication from 5 years ago contributes weight $0.5$.
2. **Confidence separation**: Average extraction confidence (`avgExtractionConfidence`) is stored independently of author score (`score`).
3. **Evidence gate**: Minimum 2 distinct publication evidence items required (`min_evidence_count = 2`).
4. **Placeholder skipping**: Authors with IDs matching `unknown_*` are ignored to prevent phantom skill aggregation.

---

## 5. Cost, Runtime & Instructions for Stage C Full Run

### Dev Subset Metrics
- Dev projects: 30
- Total capabilities extracted: 37 unique canonical capabilities
- Average extraction time per project: ~1.2s (with LLM API call), <0.01s (cached)
- Token consumption: ~350 tokens per project (prompt + response)

### Instructions to Launch Full Extraction (Stage C Day 5 Morning)
To run capability extraction and aggregation over the full database in the background:

```powershell
# 1. Run extraction with resume and disk cache
$env:PYTHONPATH = "src;."
python -m capability.extraction --limit 5000 --version capability-v1 --resume

# 2. Run author aggregation pass
python -c "from capability.aggregation import CapabilityAggregator; from graph.neo4j_adapter import Neo4jAdapter; adapter = Neo4jAdapter.from_config(); agg = CapabilityAggregator(adapter._driver); res = agg.aggregate(); print(res)"
```

- If running offline or without an active LLM key, Stage C can run entirely against `FakeAdapter` using `tests/fixtures/capabilities.json` and `tests/fixtures/requirements.json`.
