"""Deterministic synthetic graph data for adapter contract tests and demos."""

from graph.adapter import (
    CandidateRef,
    DomainView,
    EvidenceItem,
    GraphAdapter,
    PersonCapability,
    PersonView,
    ProjectRequirements,
    ProjectView,
)


_PEOPLE = (
    ("author-001", "Ada Martin"),
    ("author-002", "Benoit Laurent"),
    ("author-003", "Chloe Bernard"),
    ("author-004", "David Petit"),
    ("author-005", "Emma Robert"),
    ("author-006", "Farid Richard"),
    ("author-007", "Gabrielle Durand"),
    ("author-008", "Hugo Dubois"),
    ("author-009", "Ines Moreau"),
    ("author-010", "Jules Simon"),
    ("author-011", "Karim Michel"),
    ("author-012", "Lea Lefebvre"),
    ("unknown_Pierre Leroy", "Pierre Leroy"),
    ("unknown_Sarah Faure", "Sarah Faure"),
)

_DOMAIN_ROWS = (
    ("fixture.1", "Engineering", ()),
    ("fixture.1.1", "Computer science", ("fixture.1",)),
    ("fixture.1.1.1", "Distributed systems", ("fixture.1", "fixture.1.1")),
    ("fixture.1.1.2", "Data management", ("fixture.1", "fixture.1.1")),
    ("fixture.2", "Environmental science", ()),
    ("fixture.2.1", "Climate research", ("fixture.2",)),
    ("fixture.2.1.1", "Climate modelling", ("fixture.2", "fixture.2.1")),
    ("fixture.2.1.2", "Remote sensing", ("fixture.2", "fixture.2.1")),
)

_DOMAIN_IDS_BY_PROJECT_GROUP = (
    "fixture.1.1.1",
    "fixture.1.1.2",
    "fixture.2.1.1",
    "fixture.2.1.2",
)


class FakeAdapter(GraphAdapter):
  """In-memory Stage A adapter backed by 36 reproducible synthetic projects.

  The fixture deliberately reuses authors across projects, includes placeholder
  author IDs, and models two three-level domain branches.
  """

  def __init__(self):
    self._projects = tuple(
        ProjectView(
            project_id=f"fixture-hal-{index:04d}",
            title=f"Synthetic research publication {index:02d}",
            abstract=f"Synthetic abstract for publication {index:02d}.",
            keywords=["synthetic", f"topic-{(index - 1) % 4 + 1}"],
            year=2010 + (index - 1) % 15,
            doc_type="ART",
        )
        for index in range(1, 37)
    )
    self._people = {
        person_id: PersonView(
            person_id=person_id,
            full_name=full_name,
            is_placeholder=person_id.startswith("unknown_"),
        )
        for person_id, full_name in _PEOPLE
    }
    self._members_by_project = {
        project.project_id: self._project_member_ids(index)
        for index, project in enumerate(self._projects, start=1)
    }
    self._domains = {
        domain_id: DomainView(
            domain_id=domain_id,
            name=name,
            parent_ids=list(parent_ids),
        )
        for domain_id, name, parent_ids in _DOMAIN_ROWS
    }
    self._domain_ids_by_project = {
        project.project_id: (_DOMAIN_IDS_BY_PROJECT_GROUP[(index - 1) % 4],)
        for index, project in enumerate(self._projects, start=1)
    }

  @staticmethod
  def _project_member_ids(index: int) -> tuple[str, ...]:
    first_person = (index - 1) % 12
    member_ids = [
        _PEOPLE[first_person][0],
        _PEOPLE[(first_person + 1) % 12][0],
    ]
    if index % 6 == 0:
      member_ids.append(_PEOPLE[12 + (index // 6) % 2][0])
    return tuple(member_ids)

  @staticmethod
  def _copy_project(project: ProjectView) -> ProjectView:
    return ProjectView(
        project_id=project.project_id,
        title=project.title,
        abstract=project.abstract,
        keywords=list(project.keywords),
        year=project.year,
        doc_type=project.doc_type,
    )

  @staticmethod
  def _copy_domain(domain: DomainView) -> DomainView:
    return DomainView(
        domain_id=domain.domain_id,
        name=domain.name,
        parent_ids=list(domain.parent_ids),
    )

  def get_project(self, project_id: str) -> ProjectView | None:
    for project in self._projects:
      if project.project_id == project_id:
        return self._copy_project(project)
    return None

  def iter_projects(
      self,
      limit: int,
      offset: int = 0,
  ) -> list[ProjectView]:
    if limit < 0:
      raise ValueError("limit must be non-negative")
    if offset < 0:
      raise ValueError("offset must be non-negative")
    return [
        self._copy_project(project)
        for project in self._projects[offset:offset + limit]
    ]

  def get_project_members(self, project_id: str) -> list[PersonView]:
    return [
        self._people[person_id]
        for person_id in self._members_by_project.get(project_id, ())
    ]

  def get_project_domains(self, project_id: str) -> list[DomainView]:
    domain_ids = self._domain_ids_by_project.get(project_id, ())
    included_ids = set(domain_ids)
    for domain_id in domain_ids:
      included_ids.update(self._domains[domain_id].parent_ids)
    return [
        self._copy_domain(self._domains[domain_id])
        for domain_id in self._domains
        if domain_id in included_ids
    ]

  def get_project_requirements(
      self,
      project_id: str,
  ) -> ProjectRequirements | None:
    raise NotImplementedError(
        "FakeAdapter does not implement inferred project requirements in Stage A"
    )

  def get_person_capabilities(self, person_id: str) -> list[PersonCapability]:
    raise NotImplementedError(
        "FakeAdapter does not implement inferred person capabilities in Stage A"
    )

  def find_candidates(
      self,
      requirements: ProjectRequirements,
      exclude_person_ids: set[str],
      limit: int,
  ) -> list[CandidateRef]:
    raise NotImplementedError(
        "FakeAdapter does not implement recommendation candidate search in Stage A"
    )

  def get_candidate_evidence(
      self,
      person_id: str,
      project_id: str | None = None,
  ) -> list[EvidenceItem]:
    raise NotImplementedError(
        "FakeAdapter does not implement recommendation evidence in Stage A"
    )

  def get_coauthor_distance(
      self,
      person_id: str,
      team_person_ids: list[str],
  ) -> int | None:
    raise NotImplementedError(
        "FakeAdapter does not implement co-author distance in Stage A"
    )
