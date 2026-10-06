"""Capability gap analysis.

Computes the capability gaps for a target project by subtracting the capabilities
already covered by current project members from the project requirements:
    gaps = required capabilities - covered capabilities

Preserves importance weights and provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from graph.adapter import (
  PersonCapability,
  ProjectRequirements,
  RequiredCapability,
)


@dataclass(frozen=True)
class CapabilityGap:
  """Represents a requirement along with whether the current team covers it."""
  name: str
  importance: float
  source: str
  capability_id: str | None = None
  is_covered: bool = False
  covered_by: list[str] = field(default_factory=list)


def compute_capability_gaps(
    requirements: ProjectRequirements,
    team_capabilities: Sequence[PersonCapability] | dict[str, Sequence[PersonCapability]],
) -> list[CapabilityGap]:
  """Identify capability gaps between project requirements and existing team capabilities.

  Args:
    requirements: The extracted or user-defined project requirements.
    team_capabilities: Either a flat list of PersonCapability objects for the team,
      or a mapping of person_id -> list of PersonCapability objects.

  Returns:
    List of CapabilityGap objects indicating which requirements are covered
    and which remain as gaps.
  """
  # Map capability_id and normalized lowercase names to team member ids
  covered_by_id: dict[str, set[str]] = {}
  covered_by_name: dict[str, set[str]] = {}

  if isinstance(team_capabilities, dict):
    for pid, caps in team_capabilities.items():
      for c in caps:
        covered_by_id.setdefault(c.capability_id, set()).add(pid)
        covered_by_name.setdefault(c.name.strip().lower(), set()).add(pid)
  else:
    for c in team_capabilities:
      covered_by_id.setdefault(c.capability_id, set()).add(c.person_id)
      covered_by_name.setdefault(c.name.strip().lower(), set()).add(c.person_id)

  results: list[CapabilityGap] = []
  for req in requirements.required_capabilities:
    covering_members: set[str] = set()

    if req.capability_id and req.capability_id in covered_by_id:
      covering_members.update(covered_by_id[req.capability_id])

    norm_name = req.name.strip().lower()
    if norm_name in covered_by_name:
      covering_members.update(covered_by_name[norm_name])

    is_covered = len(covering_members) > 0
    results.append(
        CapabilityGap(
            capability_id=req.capability_id,
            name=req.name,
            importance=req.importance,
            source=req.source,
            is_covered=is_covered,
            covered_by=sorted(covering_members),
        )
    )

  return results


def get_uncovered_gaps(gaps: Sequence[CapabilityGap]) -> list[CapabilityGap]:
  """Return only the gaps that are not yet covered by the team."""
  return [g for g in gaps if not g.is_covered]


def get_total_gap_importance(gaps: Sequence[CapabilityGap], uncovered_only: bool = True) -> float:
  """Calculate total importance weight of gaps."""
  target = get_uncovered_gaps(gaps) if uncovered_only else gaps
  return sum(g.importance for g in target)
