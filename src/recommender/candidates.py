"""Candidate generation.

Retrieves candidate researchers through the GraphAdapter based on domain
and capability matches, excluding existing project members and flagging placeholder ids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from graph.adapter import (
  CandidateRef,
  GraphAdapter,
  ProjectRequirements,
)


@dataclass(frozen=True)
class Candidate:
  """Candidate collaborator under consideration for recommendation."""
  person_id: str
  matched_domain_ids: list[str] = field(default_factory=list)
  matched_capability_ids: list[str] = field(default_factory=list)
  is_placeholder: bool = False
  full_name: str = ""


def find_recommendation_candidates(
    adapter: GraphAdapter,
    requirements: ProjectRequirements,
    team_person_ids: Sequence[str],
    limit: int = 200,
) -> list[Candidate]:
  """Generate candidate researchers matching project domains or capabilities.

  Args:
    adapter: Graph adapter to query.
    requirements: Extracted requirements for the target project.
    team_person_ids: Author IDs of the current project members to exclude.
    limit: Maximum number of candidates to retrieve.

  Returns:
    List of Candidate objects with matched domains/capabilities and placeholder flags.
  """
  domain_ids = list(requirements.domain_ids)
  capability_ids = [
      c.capability_id
      for c in requirements.required_capabilities
      if c.capability_id is not None
  ]

  refs = adapter.find_candidates(
      domain_ids=domain_ids,
      capability_ids=capability_ids,
      exclude_person_ids=list(team_person_ids),
      limit=limit,
  )

  candidates: list[Candidate] = []
  for ref in refs:
    is_ph = ref.person_id.startswith("unknown_")
    candidates.append(
        Candidate(
            person_id=ref.person_id,
            matched_domain_ids=ref.matched_domain_ids,
            matched_capability_ids=ref.matched_capability_ids,
            is_placeholder=is_ph,
            full_name=ref.person_id if is_ph else ref.person_id.replace("-", " ").title(),
        )
    )

  return candidates
