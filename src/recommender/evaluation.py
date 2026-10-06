"""Leave-one-author-out evaluation.

Evaluates recommendation quality on projects with >= 3 authors by holding out
one author, recommending collaborators using the remaining authors as the current team,
and measuring hit@k (k=1, 3, 5, 10) and Mean Reciprocal Rank (MRR).

As stated in PROJECT_SPEC.md §3 (D1):
hit@k is a sanity check and benchmark metric, not ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from graph.adapter import (
  DomainView,
  GraphAdapter,
  ProjectRequirements,
)
from recommender.engine import recommend_collaborators


@dataclass(frozen=True)
class EvaluationResult:
  """Aggregated evaluation metrics for leave-one-author-out."""
  total_evaluated: int
  hit_at_1: float
  hit_at_3: float
  hit_at_5: float
  hit_at_10: float
  mrr: float
  details: list[dict] = field(default_factory=list)


def evaluate_leave_one_author_out(
    adapter: GraphAdapter,
    min_authors: int = 3,
    top_k: int = 10,
    limit_projects: int = 50,
    requirements_map: dict[str, ProjectRequirements] | None = None,
) -> EvaluationResult:
  """Run leave-one-author-out evaluation across multi-author publications.

  Args:
    adapter: GraphAdapter to query.
    min_authors: Minimum authors required for a project to be eligible (spec: >= 3).
    top_k: Cut-off for evaluation (default: 10).
    limit_projects: Max projects to evaluate.
    requirements_map: Optional pre-loaded project requirements mapping (project_id -> requirements).

  Returns:
    EvaluationResult containing hit rates and per-project details.
  """
  hits_1 = 0
  hits_3 = 0
  hits_5 = 0
  hits_10 = 0
  rr_sum = 0.0
  total_evals = 0
  details: list[dict] = []

  projects = list(adapter.iter_projects(limit=limit_projects))

  for proj in projects:
    members = adapter.get_project_members(proj.project_id)
    if len(members) < min_authors:
      continue

    # Pick the first author as the held-out author
    held_out = members[0]
    held_out_id = held_out.person_id
    remaining_team_ids = [m.person_id for m in members[1:]]

    # Get requirements
    proj_reqs = None
    if requirements_map and proj.project_id in requirements_map:
      proj_reqs = requirements_map[proj.project_id]
    else:
      domains = adapter.get_project_domains(proj.project_id)
      dom_ids: list[str] = []
      for d in domains:
        dom_ids.append(d.domain_id)
        dom_ids.extend(d.parent_ids)
      proj_reqs = ProjectRequirements(
          project_id=proj.project_id,
          domain_ids=sorted(list(set(dom_ids))),
          required_capabilities=[],
          goals=[],
          extraction_version="eval-v1",
      )

    # Run recommendation excluding the remaining team (held-out is allowed to appear)
    res = recommend_collaborators(
        adapter=adapter,
        project_id=proj.project_id,
        requirements=proj_reqs,
        team_member_ids=remaining_team_ids,
        top_k=top_k,
    )

    rank = None
    for idx, cand in enumerate(res.candidates, start=1):
      if cand.person_id == held_out_id:
        rank = idx
        break

    is_hit_1 = rank is not None and rank <= 1
    is_hit_3 = rank is not None and rank <= 3
    is_hit_5 = rank is not None and rank <= 5
    is_hit_10 = rank is not None and rank <= 10
    rr = (1.0 / rank) if rank is not None else 0.0

    if is_hit_1:
      hits_1 += 1
    if is_hit_3:
      hits_3 += 1
    if is_hit_5:
      hits_5 += 1
    if is_hit_10:
      hits_10 += 1
    rr_sum += rr
    total_evals += 1

    details.append({
        "project_id": proj.project_id,
        "held_out_author": held_out_id,
        "remaining_team": remaining_team_ids,
        "rank": rank,
        "rr": round(rr, 4),
    })

  if total_evals == 0:
    return EvaluationResult(
        total_evaluated=0,
        hit_at_1=0.0,
        hit_at_3=0.0,
        hit_at_5=0.0,
        hit_at_10=0.0,
        mrr=0.0,
        details=[],
    )

  return EvaluationResult(
      total_evaluated=total_evals,
      hit_at_1=round(hits_1 / total_evals, 4),
      hit_at_3=round(hits_3 / total_evals, 4),
      hit_at_5=round(hits_5 / total_evals, 4),
      hit_at_10=round(hits_10 / total_evals, 4),
      mrr=round(rr_sum / total_evals, 4),
      details=details,
  )
