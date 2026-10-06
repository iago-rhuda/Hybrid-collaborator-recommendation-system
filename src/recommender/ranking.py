"""Deterministic candidate ranking.

Ranks candidates according to configurable feature weights, stable tie-breaking,
and full transparency: exposes raw features, weights, contributions, and evidence IDs.
The scoring mechanism is placed behind a Scorer interface to allow future
learned rankers or alternative weighting models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

from config import get_ranking_config


@dataclass(frozen=True)
class ScoredCandidate:
  """Candidate collaborator with computed score, feature values, and evidence."""
  person_id: str
  full_name: str
  total_score: float
  features: dict[str, float]
  weights: dict[str, float]
  contributions: dict[str, float]
  evidence_ids: list[str] = field(default_factory=list)
  is_placeholder: bool = False


class Scorer(Protocol):
  """Interface for scoring candidates given feature values and weights."""

  def score(
      self,
      features: dict[str, float],
      weights: dict[str, float],
  ) -> tuple[float, dict[str, float]]:
    """Return total score and per-feature contributions."""
    ...


class LinearScorer:
  """Standard deterministic linear weighted scorer."""

  def score(
      self,
      features: dict[str, float],
      weights: dict[str, float],
  ) -> tuple[float, dict[str, float]]:
    contributions: dict[str, float] = {}
    total = 0.0
    for name, weight in weights.items():
      val = features.get(name, 0.0)
      contrib = val * weight
      contributions[name] = round(contrib, 6)
      total += contrib
    return round(total, 6), contributions


def get_default_weights() -> dict[str, float]:
  """Load default ranking weights from config/ranking.yaml with fallback defaults."""
  cfg = get_ranking_config()
  weights = cfg.get("weights", {})
  if weights:
    return dict(weights)
  return {
      "gap_match": 0.30,
      "domain_relevance": 0.15,
      "semantic": 0.15,
      "complementarity": 0.15,
      "project_similarity": 0.10,
      "graph": 0.10,
      "recency": 0.05,
  }


def rank_candidates(
    candidates_data: Sequence[dict],
    weights: dict[str, float] | None = None,
    scorer: Scorer | None = None,
    top_k: int = 10,
) -> list[ScoredCandidate]:
  """Rank candidate collaborators deterministically with stable tie-break by person_id.

  Args:
    candidates_data: List of dicts with:
      - person_id (str)
      - full_name (str, optional)
      - is_placeholder (bool, optional)
      - features (dict[str, float])
      - evidence_ids (list[str], optional)
    weights: Optional custom feature weights. Defaults to config/ranking.yaml.
    scorer: Scoring strategy implementing Scorer. Defaults to LinearScorer.
    top_k: Maximum number of ranked candidates to return.

  Returns:
    List of ScoredCandidate objects sorted descending by total_score, tie-broken
    alphabetically by person_id.
  """
  effective_weights = weights if weights is not None else get_default_weights()
  effective_scorer = scorer if scorer is not None else LinearScorer()

  scored_list: list[ScoredCandidate] = []
  for item in candidates_data:
    pid = item["person_id"]
    name = item.get("full_name") or pid
    is_ph = item.get("is_placeholder", pid.startswith("unknown_"))
    feats = item.get("features", {})
    ev_ids = item.get("evidence_ids", [])

    total_score, contributions = effective_scorer.score(feats, effective_weights)

    scored_list.append(
        ScoredCandidate(
            person_id=pid,
            full_name=name,
            total_score=total_score,
            features=dict(feats),
            weights=dict(effective_weights),
            contributions=contributions,
            evidence_ids=list(ev_ids),
            is_placeholder=is_ph,
        )
    )

  # Stable sort: descending by score, ascending by person_id for deterministic tie-breaks
  scored_list.sort(key=lambda c: (-c.total_score, c.person_id))

  return scored_list[:top_k]
