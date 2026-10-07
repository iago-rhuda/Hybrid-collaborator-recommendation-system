"""Recommendation feature extractors.

Implements the 7 pure recommendation features defined in PROJECT_SPEC.md §10.3:
  1. gap_match: importance-weighted share of gap capabilities the candidate has evidence for.
  2. domain_relevance: Jaccard overlap between candidate's project domains and target's domains.
  3. semantic: similarity between candidate capability profile and project requirements.
  4. complementarity: share of candidate's relevant capabilities not already covered by the team.
  5. project_similarity: weighted Tversky overlap of target vs candidate's past project profile.
  6. graph: co-authorship proximity to the team from WROTE relations.
  7. recency: recency-weighted publication evidence with half-life decay.

All feature functions are pure, deterministic, and return floats strictly within [0.0, 1.0].
"""

from __future__ import annotations

import math
from typing import Sequence, Set

from recommender.gaps import CapabilityGap


def compute_gap_match(
    candidate_capability_ids: Set[str] | Sequence[str],
    gaps: Sequence[CapabilityGap],
) -> float:
  """Compute importance-weighted share of uncovered gap capabilities matched by candidate.

  Formula:
      gap_match = sum(importance(g) for g in uncovered_gaps if g in candidate_caps)
                  / sum(importance(g) for g in uncovered_gaps)

  If there are no uncovered gaps, returns 0.0.

  Args:
    candidate_capability_ids: Capabilities possessed by the candidate.
    gaps: CapabilityGap objects for the project.

  Returns:
    Float in [0.0, 1.0].
  """
  uncovered = [g for g in gaps if not g.is_covered]
  if not uncovered:
    return 0.0

  total_importance = sum(g.importance for g in uncovered)
  if total_importance <= 0.0:
    return 0.0

  cand_caps = set(candidate_capability_ids)
  matched_importance = sum(
      g.importance
      for g in uncovered
      if (g.capability_id and g.capability_id in cand_caps)
      or (g.name.strip().lower() in {c.lower() for c in cand_caps})
  )

  return max(0.0, min(1.0, matched_importance / total_importance))


def compute_domain_relevance(
    candidate_domain_ids: Set[str] | Sequence[str],
    target_domain_ids: Set[str] | Sequence[str],
) -> float:
  """Compute Jaccard overlap between candidate's domains and target project's domains.

  Formula:
      domain_relevance = |D_cand ∩ D_target| / |D_cand ∪ D_target|

  Both domain sets are expected to include ancestor/parent domain IDs.
  Returns 0.0 if both sets are empty.

  Args:
    candidate_domain_ids: Research domain IDs associated with candidate.
    target_domain_ids: Research domain IDs of the target project.

  Returns:
    Float in [0.0, 1.0].
  """
  cand_set = set(candidate_domain_ids)
  target_set = set(target_domain_ids)

  union_len = len(cand_set | target_set)
  if union_len == 0:
    return 0.0

  inter_len = len(cand_set & target_set)
  return max(0.0, min(1.0, inter_len / union_len))


def compute_semantic_similarity(
    candidate_capability_ids: Set[str] | Sequence[str],
    required_capability_ids: Set[str] | Sequence[str],
) -> float:
  """Compute semantic requirement coverage from candidate's capability profile.

  Formula:
      semantic = |C_cand ∩ C_req| / |C_req|

  Returns 0.0 if required_capability_ids is empty.

  Args:
    candidate_capability_ids: Set/sequence of candidate capability IDs.
    required_capability_ids: Set/sequence of required capability IDs.

  Returns:
    Float in [0.0, 1.0].
  """
  cand_set = set(candidate_capability_ids)
  req_set = set(required_capability_ids)

  if not req_set:
    return 0.0

  overlap = len(cand_set & req_set)
  return max(0.0, min(1.0, overlap / len(req_set)))


def compute_complementarity(
    candidate_capability_ids: Set[str] | Sequence[str],
    team_capability_ids: Set[str] | Sequence[str],
    relevant_capability_ids: Set[str] | Sequence[str] | None = None,
) -> float:
  """Compute the share of candidate's relevant capabilities not already covered by the team.

  Formula:
      C_rel = C_cand ∩ C_target_relevant (or C_cand if relevant is None)
      complementarity = |C_rel \\ C_team| / |C_rel|

  Penalises redundancy: a candidate whose capabilities duplicate what the team
  already has will score 0.0, whereas a candidate bringing uniquely missing skills
  scores 1.0.

  Args:
    candidate_capability_ids: Capabilities possessed by the candidate.
    team_capability_ids: Capabilities currently possessed by team members.
    relevant_capability_ids: Optional set of capabilities deemed relevant to the project.

  Returns:
    Float in [0.0, 1.0].
  """
  cand_set = set(candidate_capability_ids)
  team_set = set(team_capability_ids)

  if relevant_capability_ids is not None:
    rel_set = set(relevant_capability_ids)
    active_cand = cand_set & rel_set
  else:
    active_cand = cand_set

  if not active_cand:
    return 0.0

  uncovered_by_team = active_cand - team_set
  return max(0.0, min(1.0, len(uncovered_by_team) / len(active_cand)))


def compute_project_similarity(
    target_features: Set[str] | Sequence[str],
    candidate_features: Set[str] | Sequence[str],
    alpha: float = 0.5,
    beta: float = 0.5,
) -> float:
  """Compute weighted Tversky similarity between target project and candidate profile.

  Formula (thesis Eq. 5.10):
      Tversky(A, B) = |A ∩ B| / (|A ∩ B| + alpha * |A \\ B| + beta * |B \\ A|)

  When alpha = beta = 0.5, this corresponds to Dice's coefficient;
  when alpha = beta = 1.0, this is Jaccard similarity.

  Args:
    target_features: Feature identifiers (domains, keywords, capabilities) for target.
    candidate_features: Feature identifiers for candidate's past work.
    alpha: Weight for target features missing in candidate.
    beta: Weight for candidate features missing in target.

  Returns:
    Float in [0.0, 1.0].
  """
  a = set(target_features)
  b = set(candidate_features)

  inter_len = len(a & b)
  a_diff = len(a - b)
  b_diff = len(b - a)

  denominator = inter_len + (alpha * a_diff) + (beta * b_diff)
  if denominator <= 0.0:
    return 0.0

  return max(0.0, min(1.0, inter_len / denominator))


def compute_graph_proximity(
    coauthor_distance: int | None,
    max_hops: int = 3,
) -> float:
  """Compute co-authorship proximity to the team from WROTE relations.

  Formula:
      graph = 1.0 - (coauthor_distance - 1) / max_hops   if 1 <= distance <= max_hops
              0.0                                        if distance is None or > max_hops

  Hop distance mapping:
      distance 1 (direct coauthor): 1.0
      distance 2 (co-author of co-author): 0.667 (when max_hops=3)
      distance 3: 0.333
      distance > 3 or None: 0.0

  Args:
    coauthor_distance: Minimum co-authorship hop distance to any team member.
    max_hops: Search horizon for co-authorship hops.

  Returns:
    Float in [0.0, 1.0].
  """
  if coauthor_distance is None or coauthor_distance <= 0 or coauthor_distance > max_hops:
    return 0.0

  proximity = 1.0 - ((coauthor_distance - 1) / max_hops)
  return max(0.0, min(1.0, proximity))


def compute_recency(
    last_seen_year: int | None,
    current_year: int = 2024,
    half_life: float = 3.0,
) -> float:
  """Compute publication recency using exponential half-life decay.

  Formula:
      recency = 2 ** (- (max(0, current_year - last_seen_year) / half_life))

  Args:
    last_seen_year: Most recent publication year for the candidate.
    current_year: Reference year.
    half_life: Number of years for evidence weight to halve.

  Returns:
    Float in [0.0, 1.0]. Returns 0.0 if last_seen_year is None.
  """
  if last_seen_year is None or half_life <= 0:
    return 0.0

  delta_years = max(0, current_year - last_seen_year)
  score = math.pow(2.0, - (delta_years / half_life))
  return max(0.0, min(1.0, score))
