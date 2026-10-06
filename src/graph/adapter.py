from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class ProjectView:
  project_id: str
  title: str
  abstract: str
  keywords: list[str]
  year: int | None
  doc_type: str


@dataclass(frozen=True)
class PersonView:
  person_id: str
  full_name: str
  is_placeholder: bool


@dataclass(frozen=True)
class DomainView:
  domain_id: str
  name: str
  parent_ids: list[str]


@dataclass(frozen=True)
class PersonCapability:
  person_id: str
  capability_id: str
  name: str
  kind: str
  publication_count: int
  evidence_count: int
  avg_confidence: float
  last_seen_year: int | None
  extraction_version: str


@dataclass(frozen=True)
class RequiredCapability:
  capability_id: str | None
  name: str
  importance: float
  source: Literal["extracted", "user"]


@dataclass(frozen=True)
class ProjectRequirements:
  project_id: str | None
  domain_ids: list[str]
  required_capabilities: list[RequiredCapability]
  goals: list[str]
  extraction_version: str


@dataclass(frozen=True)
class ProjectSpec:
  title: str
  abstract: str
  keywords: list[str]


@dataclass(frozen=True)
class EvidenceItem:
  kind: Literal["project", "domain", "capability"]
  id: str
  text: str
  project_id: str | None
  year: int | None


@dataclass(frozen=True)
class CandidateRef:
  person_id: str
  matched_domain_ids: list[str]
  matched_capability_ids: list[str]


class GraphAdapter(Protocol):
  """Stable interface between graph storage and the recommender."""

  def get_project(self, project_id: str) -> ProjectView | None:
    """Read a HAL publication and its factual project properties."""
    ...

  def iter_projects(
      self,
      limit: int,
      offset: int = 0,
  ) -> list[ProjectView]:
    """Read a bounded page of HAL publications."""
    ...

  def get_project_members(self, project_id: str) -> list[PersonView]:
    """Read authors connected to a publication by WROTE."""
    ...

  def get_project_domains(self, project_id: str) -> list[DomainView]:
    """Read a publication's HAL domains, including their ancestors."""
    ...

  def get_project_requirements(
      self,
      project_id: str,
  ) -> ProjectRequirements | None:
    """Read previously extracted requirements; this is not a HAL fact method."""
    ...

  def get_person_capabilities(self, person_id: str) -> list[PersonCapability]:
    """Read inferred capability evidence; not implemented in Stage A."""
    ...

  def find_candidates(
      self,
      requirements: ProjectRequirements,
      exclude_person_ids: set[str],
      limit: int,
  ) -> list[CandidateRef]:
    """Find bounded candidate references; not implemented in Stage A."""
    ...

  def get_candidate_evidence(
      self,
      person_id: str,
      project_id: str | None = None,
  ) -> list[EvidenceItem]:
    """Read recommendation evidence; not implemented in Stage A."""
    ...

  def get_coauthor_distance(
      self,
      person_id: str,
      team_person_ids: list[str],
  ) -> int | None:
    """Return the shortest co-authorship distance to the team; not implemented in Stage A."""
    ...
