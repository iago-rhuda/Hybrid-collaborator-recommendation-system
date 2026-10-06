import re
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from config import (
    DEFAULT_GRAPH_MAPPING_PATH,
    load_graph_mapping,
    load_neo4j_settings,
)
from graph.adapter import (
    CandidateRef,
    DomainView,
    EvidenceItem,
    PersonCapability,
    PersonView,
    ProjectRequirements,
    ProjectView,
)


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
def _mapping_value(mapping: dict[str, Any], *keys: str) -> str:
  value: Any = mapping
  for key in keys:
    if not isinstance(value, dict) or key not in value:
      raise ValueError(f"Graph mapping is missing {'.'.join(keys)}")
    value = value[key]
  if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
    raise ValueError(
        f"Graph mapping value for {'.'.join(keys)} must be a safe identifier"
    )
  return value


def _optional_text(value: Any) -> str:
  return "" if value is None else str(value)


def _keywords(value: Any) -> list[str]:
  if value is None:
    return []
  if isinstance(value, list):
    return [str(item) for item in value if item is not None]
  return [str(value)]


def _optional_year(value: Any) -> int | None:
  if value is None:
    return None
  try:
    return int(value)
  except (TypeError, ValueError) as error:
    raise ValueError(f"Invalid publication year returned by Neo4j: {value!r}") from error


def _record_value(record: Any, key: str) -> Any:
  if hasattr(record, "get"):
    return record.get(key)
  return record[key]


class Neo4jAdapter:
  """Read current HAL facts from Neo4j through the configured graph mapping."""

  def __init__(
      self,
      driver: Any | None = None,
      database: str | None = None,
      mapping_path: str | Path = DEFAULT_GRAPH_MAPPING_PATH,
  ):
    self._mapping = load_graph_mapping(mapping_path)
    self.database = database
    self._owns_driver = driver is None

    if driver is None:
      settings = load_neo4j_settings(database=database)
      driver = GraphDatabase.driver(
          settings.uri,
          auth=(settings.user, settings.password),
      )
    self.driver = driver

  def close(self) -> None:
    if self._owns_driver:
      self.driver.close()

  def _session(self):
    return self.driver.session(database=self.database)

  def get_project(self, project_id: str) -> ProjectView | None:
    project_label = _mapping_value(self._mapping, "nodes", "project", "label")
    project_key = _mapping_value(self._mapping, "nodes", "project", "key")
    property_keys = {
        name: _mapping_value(
            self._mapping,
            "nodes",
            "project",
            "properties",
            name,
        )
        for name in ("title", "abstract", "keywords", "year", "doc_type")
    }
    query = f"""
        MATCH (p:{project_label} {{{project_key}: $project_id}})
        RETURN p.{project_key} AS project_id,
               p.{property_keys["title"]} AS title,
               p.{property_keys["abstract"]} AS abstract,
               p.{property_keys["keywords"]} AS keywords,
               p.{property_keys["year"]} AS year,
               p.{property_keys["doc_type"]} AS doc_type
        """
    with self._session() as session:
      record = session.run(query, project_id=project_id).single()
    if record is None:
      return None
    return ProjectView(
        project_id=_optional_text(_record_value(record, "project_id")),
        title=_optional_text(_record_value(record, "title")),
        abstract=_optional_text(_record_value(record, "abstract")),
        keywords=_keywords(_record_value(record, "keywords")),
        year=_optional_year(_record_value(record, "year")),
        doc_type=_optional_text(_record_value(record, "doc_type")),
    )

  def iter_projects(
      self,
      limit: int,
      offset: int = 0,
  ) -> list[ProjectView]:
    if limit < 0:
      raise ValueError("limit must be non-negative")
    if offset < 0:
      raise ValueError("offset must be non-negative")
    if limit == 0:
      return []

    project_label = _mapping_value(self._mapping, "nodes", "project", "label")
    project_key = _mapping_value(self._mapping, "nodes", "project", "key")
    property_keys = {
        name: _mapping_value(
            self._mapping,
            "nodes",
            "project",
            "properties",
            name,
        )
        for name in ("title", "abstract", "keywords", "year", "doc_type")
    }
    query = f"""
        MATCH (p:{project_label})
        RETURN p.{project_key} AS project_id,
               p.{property_keys["title"]} AS title,
               p.{property_keys["abstract"]} AS abstract,
               p.{property_keys["keywords"]} AS keywords,
               p.{property_keys["year"]} AS year,
               p.{property_keys["doc_type"]} AS doc_type
        ORDER BY p.{project_key}
        SKIP $offset
        LIMIT $limit
        """
    with self._session() as session:
      records = session.run(query, offset=offset, limit=limit)
      return [self._project_from_record(record) for record in records]

  @staticmethod
  def _project_from_record(record: Any) -> ProjectView:
    return ProjectView(
        project_id=_optional_text(_record_value(record, "project_id")),
        title=_optional_text(_record_value(record, "title")),
        abstract=_optional_text(_record_value(record, "abstract")),
        keywords=_keywords(_record_value(record, "keywords")),
        year=_optional_year(_record_value(record, "year")),
        doc_type=_optional_text(_record_value(record, "doc_type")),
    )

  def get_project_members(self, project_id: str) -> list[PersonView]:
    project_label = _mapping_value(self._mapping, "nodes", "project", "label")
    project_key = _mapping_value(self._mapping, "nodes", "project", "key")
    person_label = _mapping_value(self._mapping, "nodes", "person", "label")
    person_key = _mapping_value(self._mapping, "nodes", "person", "key")
    relationship = _mapping_value(
        self._mapping,
        "relationships",
        "authorship",
    )
    properties = {
        name: _mapping_value(
            self._mapping,
            "nodes",
            "person",
            "properties",
            name,
        )
        for name in ("full_name", "first_name", "last_name")
    }
    query = f"""
        MATCH (a:{person_label})-[:{relationship}]->(p:{project_label} {{{project_key}: $project_id}})
        RETURN DISTINCT a.{person_key} AS person_id,
                        a.{properties["full_name"]} AS full_name,
                        a.{properties["first_name"]} AS first_name,
                        a.{properties["last_name"]} AS last_name
        ORDER BY person_id
        """
    with self._session() as session:
      records = session.run(query, project_id=project_id)
      members = []
      for record in records:
        person_id = _optional_text(_record_value(record, "person_id"))
        full_name = _optional_text(_record_value(record, "full_name"))
        if not full_name:
          full_name = " ".join(
              part
              for part in (
                  _optional_text(_record_value(record, "first_name")),
                  _optional_text(_record_value(record, "last_name")),
              )
              if part
          )
        members.append(
            PersonView(
                person_id=person_id,
                full_name=full_name,
                is_placeholder=person_id.startswith("unknown_"),
            )
        )
      return members

  def get_project_domains(self, project_id: str) -> list[DomainView]:
    project_label = _mapping_value(self._mapping, "nodes", "project", "label")
    project_key = _mapping_value(self._mapping, "nodes", "project", "key")
    domain_label = _mapping_value(self._mapping, "nodes", "domain", "label")
    domain_key = _mapping_value(self._mapping, "nodes", "domain", "key")
    domain_name = _mapping_value(
        self._mapping,
        "nodes",
        "domain",
        "properties",
        "name",
    )
    project_domain = _mapping_value(
        self._mapping,
        "relationships",
        "project_domain",
    )
    domain_parent = _mapping_value(
        self._mapping,
        "relationships",
        "domain_parent",
    )
    query = f"""
        MATCH (p:{project_label} {{{project_key}: $project_id}})
              -[:{project_domain}]->(assigned:{domain_label})
        MATCH (assigned)-[:{domain_parent}*0..]->(d:{domain_label})
        WITH DISTINCT d
        OPTIONAL MATCH (d)-[:{domain_parent}*1..]->(ancestor:{domain_label})
        RETURN d.{domain_key} AS domain_id,
               d.{domain_name} AS name,
               collect(DISTINCT ancestor.{domain_key}) AS parent_ids
        ORDER BY domain_id
        """
    with self._session() as session:
      records = session.run(query, project_id=project_id)
      return [
          DomainView(
              domain_id=_optional_text(_record_value(record, "domain_id")),
              name=_optional_text(_record_value(record, "name")),
              parent_ids=[
                  _optional_text(parent_id)
                  for parent_id in (_record_value(record, "parent_ids") or [])
                  if parent_id is not None
              ],
          )
          for record in records
      ]

  def get_project_requirements(
      self,
      project_id: str,
  ) -> ProjectRequirements | None:
    raise NotImplementedError(
        "Neo4jAdapter does not implement inferred requirements in Stage A"
    )

  def get_person_capabilities(self, person_id: str) -> list[PersonCapability]:
    raise NotImplementedError(
        "Neo4jAdapter does not implement inferred capabilities in Stage A"
    )

  def find_candidates(
      self,
      requirements: ProjectRequirements,
      exclude_person_ids: set[str],
      limit: int,
  ) -> list[CandidateRef]:
    raise NotImplementedError(
        "Neo4jAdapter does not implement candidate search in Stage A"
    )

  def get_candidate_evidence(
      self,
      person_id: str,
      project_id: str | None = None,
  ) -> list[EvidenceItem]:
    raise NotImplementedError(
        "Neo4jAdapter does not implement recommendation evidence in Stage A"
    )

  def get_coauthor_distance(
      self,
      person_id: str,
      team_person_ids: list[str],
  ) -> int | None:
    raise NotImplementedError(
        "Neo4jAdapter does not implement co-author distance in Stage A"
    )
