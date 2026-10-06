"""Candidate evidence retrieval.

Retrieves and organizes supporting evidence items for candidates from the graph
(publications, research domains, capabilities) for auditing and grounded explanation.
"""

from __future__ import annotations

from typing import Sequence

from graph.adapter import (
  EvidenceItem,
  GraphAdapter,
)


def retrieve_candidate_evidence(
    adapter: GraphAdapter,
    person_id: str,
    domain_ids: Sequence[str],
    capability_ids: Sequence[str],
) -> list[EvidenceItem]:
  """Retrieve supporting evidence items for a candidate author from the graph."""
  return adapter.get_candidate_evidence(
      person_id=person_id,
      domain_ids=list(domain_ids),
      capability_ids=list(capability_ids),
  )


def extract_evidence_ids(evidence_items: Sequence[EvidenceItem]) -> list[str]:
  """Extract ordered, unique IDs from a list of EvidenceItem objects."""
  seen: set[str] = set()
  result: list[str] = []
  for item in evidence_items:
    if item.id and item.id not in seen:
      seen.add(item.id)
      result.append(item.id)
  return result


def group_evidence_by_kind(
    evidence_items: Sequence[EvidenceItem],
) -> dict[str, list[EvidenceItem]]:
  """Group evidence items by their kind ('project', 'domain', 'capability')."""
  grouped: dict[str, list[EvidenceItem]] = {
      "project": [],
      "domain": [],
      "capability": [],
  }
  for item in evidence_items:
    grouped.setdefault(item.kind, []).append(item)
  return grouped
