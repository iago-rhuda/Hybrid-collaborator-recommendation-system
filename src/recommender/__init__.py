"""Recommender package — collaboration recommendation and ranking."""

from recommender.candidates import Candidate, find_recommendation_candidates
from recommender.engine import RecommendationResult, recommend_collaborators
from recommender.evaluation import EvaluationResult, evaluate_leave_one_author_out
from recommender.evidence import (
  extract_evidence_ids,
  group_evidence_by_kind,
  retrieve_candidate_evidence,
)
from recommender.features import (
  compute_complementarity,
  compute_domain_relevance,
  compute_gap_match,
  compute_graph_proximity,
  compute_project_similarity,
  compute_recency,
  compute_semantic_similarity,
)
from recommender.gaps import (
  CapabilityGap,
  compute_capability_gaps,
  get_total_gap_importance,
  get_uncovered_gaps,
)
from recommender.ranking import (
  LinearScorer,
  ScoredCandidate,
  Scorer,
  get_default_weights,
  rank_candidates,
)

__all__ = [
    "Candidate",
    "find_recommendation_candidates",
    "CapabilityGap",
    "compute_capability_gaps",
    "get_uncovered_gaps",
    "get_total_gap_importance",
    "compute_gap_match",
    "compute_domain_relevance",
    "compute_semantic_similarity",
    "compute_complementarity",
    "compute_project_similarity",
    "compute_graph_proximity",
    "compute_recency",
    "Scorer",
    "LinearScorer",
    "ScoredCandidate",
    "get_default_weights",
    "rank_candidates",
    "retrieve_candidate_evidence",
    "extract_evidence_ids",
    "group_evidence_by_kind",
    "RecommendationResult",
    "recommend_collaborators",
    "EvaluationResult",
    "evaluate_leave_one_author_out",
]
