"""Graph adapter — stable interface contract between the recommendation code and Neo4j.

All recommendation code talks only to these dataclasses and methods.
Physical labels, relationship types, property names and Cypher live exclusively in
neo4j_adapter.py and config/graph_mapping.yaml.

Rules:
- Frozen dataclasses only; no mutable state.
- The Protocol is the single source of truth for method signatures.
- Never import from neo4j_adapter.py in any module outside src/graph/.
- A schema change requires only mapping + adapter changes, not recommendation logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Protocol


# ---------------------------------------------------------------------------
# Shared dataclasses (frozen, value-object semantics)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProjectView:
  """Read-only view of a project (HAL publication) node."""
  project_id: str          # halId
  title: str
  abstract: str
  keywords: list[str]
  year: int | None
  doc_type: str


@dataclass(frozen=True)
class PersonView:
  """Read-only view of an author node."""
  person_id: str           # Author.halId
  full_name: str
  is_placeholder: bool     # True when person_id starts with "unknown_"


@dataclass(frozen=True)
class DomainView:
  """Read-only view of a research domain, including its ancestor ids."""
  domain_id: str
  name: str
  parent_ids: list[str]    # All ancestor domain ids (closest first)


@dataclass(frozen=True)
class PersonCapability:
  """Aggregated capability evidence for one author."""
  person_id: str
  capability_id: str
  name: str
  kind: str                # CapabilityKind value
  publication_count: int
  evidence_count: int
  avg_confidence: float
  last_seen_year: int | None
  extraction_version: str


@dataclass(frozen=True)
class RequiredCapability:
  """A capability required by a project, sourced from extraction or user input."""
  name: str
  importance: float        # [0, 1]
  source: str              # "extracted" | "user"
  capability_id: str | None = None   # None when not yet resolved


@dataclass(frozen=True)
class ProjectSpec:
  """Free-text description of a target project (used when no halId is available)."""
  title: str
  abstract: str
  keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProjectRequirements:
  """Extracted requirements for a project (target or spec)."""
  project_id: str | None           # None when derived from a ProjectSpec
  domain_ids: list[str]
  required_capabilities: list[RequiredCapability]
  goals: list[str]
  extraction_version: str


@dataclass(frozen=True)
class EvidenceItem:
  """A single piece of evidence retrieved from the graph."""
  kind: str                # "project" | "domain" | "capability"
  id: str
  text: str
  project_id: str | None
  year: int | None


@dataclass(frozen=True)
class CandidateRef:
  """A candidate person returned by find_candidates before ranking."""
  person_id: str
  matched_domain_ids: list[str]
  matched_capability_ids: list[str]


# ---------------------------------------------------------------------------
# Adapter Protocol — the only interface the recommendation code sees
# ---------------------------------------------------------------------------

class GraphAdapter(Protocol):
  """Stable read interface over the research collaboration graph.

  All method signatures are frozen after Gate 1.  Implementations must never
  raise unless explicitly documented (e.g. NotImplementedError for Stage-C
  methods during Stage B).
  """

  def get_project(self, project_id: str) -> ProjectView | None:
    """Return project data for *project_id*, or None if not found."""
    ...

  def iter_projects(
      self,
      limit: int = 100,
      offset: int = 0,
  ) -> Iterator[ProjectView]:
    """Yield projects in stable order, paginated by *limit* and *offset*."""
    ...

  def get_project_members(self, project_id: str) -> list[PersonView]:
    """Return all authors (members) of the given project."""
    ...

  def get_project_domains(self, project_id: str) -> list[DomainView]:
    """Return all research domains of the project, including ancestor ids."""
    ...

  def get_person_capabilities(self, person_id: str) -> list[PersonCapability]:
    """Return all aggregated capabilities for the given author."""
    ...

  def find_candidates(
      self,
      domain_ids: list[str],
      capability_ids: list[str],
      exclude_person_ids: list[str],
      limit: int = 200,
  ) -> list[CandidateRef]:
    """Find candidate authors matching the given domains/capabilities.

    Excludes authors whose person_id is in *exclude_person_ids*.
    """
    ...

  def get_candidate_evidence(
      self,
      person_id: str,
      domain_ids: list[str],
      capability_ids: list[str],
  ) -> list[EvidenceItem]:
    """Retrieve supporting evidence items for a candidate."""
    ...

  def get_coauthor_distance(
      self,
      person_id: str,
      team_person_ids: list[str],
  ) -> int | None:
    """Return minimum co-authorship hop distance between person and any team member.

    Returns None when no path exists within the search limit.
    """
    ...
