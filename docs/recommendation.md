# Recommendation System Architecture and Grounding

This document describes the design, mathematical formulation, evidence linking, and explanation verification of the collaborator recommendation engine implemented in Stage C.

---

## 1. Recommendation Pipeline

The recommendation pipeline answers the core system question:
> *"For this research project, which researchers could complement it, and why?"*

```mermaid
flowchart TD
    Target[Target Project / ProjectSpec] --> Reqs[Project Requirements]
    Target --> Team[Current Team Members]
    Team --> TeamCaps[Team Capabilities in Graph]
    Reqs & TeamCaps --> Gaps[Capability Gap Analysis: Required - Covered]
    Reqs --> CandGen[Candidate Generation: find_candidates]
    CandGen --> CandPool[Candidate Pool: excludes team, flags placeholders]
    CandPool --> Feat[Feature Computation: 7 pure features in [0, 1]]
    Feat --> Rank[Deterministic Ranking: LinearScorer with config weights]
    Rank --> Evid[Evidence Linking: Project, Domain, Capability IDs]
    Evid --> RAG[GraphRAG Grounded Explanation & Citation Verification]
    RAG --> Output[Explainable Top-K Recommendations]
```

### Key Principles:
1. **Facts vs. Inference:**
   - **Facts (from HAL):** Publication nodes (`Project`), author nodes (`Author`), research domains (`ResearchDomain`), co-authorships (`WROTE`), and presentations (`PRESENTED_AT`).
   - **Inference (derived):** Extracted capabilities (`Capability`), capability evidence links (`EVIDENCES_CAPABILITY`), aggregated researcher profiles (`HAS_CAPABILITY`), and requirement mappings. All inferred entities carry `inferred: true`, versioning, and provenance.
2. **Relevance vs. Complementarity:**
   The recommender distinguishes between researchers who simply share the same field (*relevance*) and those who bring skills the current team lacks (*complementarity*). Redundancy is explicitly penalized.
3. **No Free-Form Cypher to LLM:**
   The LLM never queries the database directly, never ranks candidates, and cannot invent skills or relationships.

---

## 2. Feature Mathematical Formulations

All 7 features are implemented as pure, deterministic functions strictly bounded in $[0.0, 1.0]$.

### 2.1 `gap_match` (Importance-weighted gap coverage)
Measures the share of uncovered capability gaps that the candidate possesses:
$$\text{gap\_match} = \frac{\sum_{g \in G_{\text{uncovered}} \cap C_{\text{cand}}} \text{importance}(g)}{\sum_{g \in G_{\text{uncovered}}} \text{importance}(g)}$$
- If there are no uncovered gaps ($G_{\text{uncovered}} = \emptyset$), returns $0.0$.
- Range: $[0.0, 1.0]$.

### 2.2 `domain_relevance` (ResearchDomain overlap)
Computes the Jaccard similarity between the candidate's research domains and the target project's domains (including taxonomic ancestor IDs):
$$\text{domain\_relevance} = \frac{|D_{\text{cand}} \cap D_{\text{target}}|}{|D_{\text{cand}} \cup D_{\text{target}}|}$$
- Returns $0.0$ if both domain sets are empty.
- Range: $[0.0, 1.0]$.

### 2.3 `semantic` (Requirement coverage)
Measures the proportion of project required capabilities matched by the candidate's profile:
$$\text{semantic} = \frac{|C_{\text{cand}} \cap C_{\text{req}}|}{|C_{\text{req}}|}$$
- Returns $0.0$ if no requirements are specified.
- Range: $[0.0, 1.0]$.

### 2.4 `complementarity` (Anti-redundancy)
Measures the share of the candidate's capabilities that are **not** already covered by the team:
$$\text{complementarity} = \frac{|C_{\text{cand, rel}} \setminus C_{\text{team}}|}{|C_{\text{cand, rel}}|}$$
- If a candidate's skills are completely identical to existing team members, complementarity is $0.0$.
- If all of the candidate's relevant skills are new to the team, complementarity is $1.0$.
- Range: $[0.0, 1.0]$.

### 2.5 `project_similarity` (Weighted Tversky overlap)
Measures overall alignment between target project features $A$ (domains + keywords/capabilities) and candidate past work profile $B$ (thesis Eq. 5.10):
$$\text{Tversky}(A, B) = \frac{|A \cap B|}{|A \cap B| + \alpha |A \setminus B| + \beta |B \setminus A|}$$
- Default weights: $\alpha = 0.5, \beta = 0.5$ (Dice index).
- Range: $[0.0, 1.0]$.

### 2.6 `graph` (Co-authorship proximity)
Proximity based on shortest path hop distance $d$ across `WROTE` relationships to existing team members:
$$\text{graph} = \begin{cases}
1.0 - \frac{d - 1}{\text{max\_hops}} & \text{if } 1 \le d \le \text{max\_hops} \\
0.0 & \text{if } d > \text{max\_hops} \text{ or unreachable}
\end{cases}$$
- For $\text{max\_hops} = 3$:
  - Distance 1 (direct coauthor): $1.0$
  - Distance 2 (shared coauthor): $0.667$
  - Distance 3: $0.333$
  - Unconnected / None: $0.0$
- Range: $[0.0, 1.0]$.

### 2.7 `recency` (Half-life decay)
Exponential decay weighting candidate's most recent publication evidence:
$$\text{recency} = 2.0^{-\frac{\max(0, \text{current\_year} - \text{last\_seen\_year})}{\text{half\_life}}}$$
- Default $\text{half\_life} = 3.0$ years.
- Publication in current year: $1.0$; 3 years ago: $0.5$; 6 years ago: $0.25$.
- Range: $[0.0, 1.0]$.

---

## 3. Ranking & Transparency

Ranking is configured in `config/ranking.yaml`:
```yaml
weights:
  gap_match: 0.30
  domain_relevance: 0.15
  semantic: 0.15
  complementarity: 0.15
  project_similarity: 0.10
  graph: 0.10
  recency: 0.05
```

Total score is computed via a `LinearScorer`:
$$\text{total\_score} = \sum_{i} w_i \cdot f_i$$

### Stable Tie-Break:
Candidates are sorted descending by `total_score`. Equal scores are tie-broken alphabetically by `person_id`, guaranteeing completely deterministic ranking order.

The output exposes:
- Raw feature values ($f_i$)
- Feature weights ($w_i$)
- Individual contributions ($w_i \cdot f_i$)
- Evidence IDs linked from the graph

---

## 4. GraphRAG Grounded Explanation & Verification

### 4.1 Grounding Constraints
- Prompt strictly adheres to the terminology rule: *"publication evidence related to X"*, never *"expert in X"*.
- Every claim must cite an evidence identifier in square brackets: `[halId]` or `[capability_id]` or `[domain_id]`.

### 4.2 Citation Verification Post-Check
When an LLM generates an explanation:
1. All bracketed citations `\[([a-zA-Z0-9_\.\-]+)\]` are extracted.
2. Every cited ID must be present in the supplied `context.valid_ids`.
3. If **any** unknown or hallucinated ID is detected, the LLM output is immediately rejected and discarded.
4. The system automatically falls back to a deterministic template explanation built from verified graph facts.
5. If the LLM call times out or fails, the template explanation is used seamlessly.

---

## 5. Evaluation: Leave-One-Author-Out

As specified in `PROJECT_SPEC.md` §3 (D1):
- Evaluates publications with $\ge 3$ authors.
- Holds out one author; recommends collaborators using the remaining authors as the current team.
- Measures hit@k ($k=1, 3, 5, 10$) and Mean Reciprocal Rank (MRR).
- Serves as a sanity check and benchmark metric, acknowledging that publications are not complete ground truth for all possible collaborations.
