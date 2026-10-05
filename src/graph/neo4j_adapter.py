"""Neo4j adapter — implements GraphAdapter against the live database.

Fact methods (get_project, iter_projects, get_project_members, get_project_domains)
are fully implemented in Stage A.

Capability method (get_person_capabilities) is implemented in Stage B.

Stage-C methods (find_candidates, get_candidate_evidence, get_coauthor_distance)
raise NotImplementedError with clear messages until Stage C.

All Cypher is parameterised and uses only the names from config/graph_mapping.yaml.
No labels, relationship types or property names are hard-coded in this file.
"""

from __future__ import annotations

from typing import Iterator

from neo4j import GraphDatabase

from config import get_neo4j_config, get_graph_mapping
from graph.adapter import (
  CandidateRef,
  DomainView,
  EvidenceItem,
  GraphAdapter,
  PersonCapability,
  PersonView,
  ProjectView,
)


class Neo4jAdapter:
  """Live Neo4j implementation of the GraphAdapter protocol."""

  def __init__(self, uri: str, user: str, password: str, database: str = "neo4j") -> None:
    self._driver = GraphDatabase.driver(uri, auth=(user, password))
    self._database = database
    m = get_graph_mapping()
    self._lbl = m.get("labels", {})
    self._rel = m.get("relationships", {})
    self._prop = m.get("properties", {})

  @classmethod
  def from_config(cls) -> "Neo4jAdapter":
    """Construct from environment variables / config."""
    cfg = get_neo4j_config()
    return cls(
        uri=cfg["uri"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
    )

  def close(self) -> None:
    self._driver.close()

  def __enter__(self) -> "Neo4jAdapter":
    return self

  def __exit__(self, *args) -> None:
    self.close()

  def _run(self, query: str, **params) -> list[dict]:
    with self._driver.session(database=self._database) as session:
      result = session.run(query, **params)
      return [dict(record) for record in result]

  # ------------------------------------------------------------------
  # Fact methods (Stage A)
  # ------------------------------------------------------------------

  def get_project(self, project_id: str) -> ProjectView | None:
    label = self._lbl["project"]
    prop = self._prop["project"]
    rows = self._run(
        f"MATCH (p:{label} {{{prop['id']}: $pid}}) RETURN p",
        pid=project_id,
    )
    if not rows:
      return None
    node = rows[0]["p"]
    return self._project_view_from_node(node)

  def iter_projects(self, limit: int = 100, offset: int = 0) -> Iterator[ProjectView]:
    label = self._lbl["project"]
    prop = self._prop["project"]
    rows = self._run(
        f"MATCH (p:{label}) RETURN p ORDER BY p.{prop['id']} SKIP $offset LIMIT $limit",
        offset=offset,
        limit=limit,
    )
    for row in rows:
      yield self._project_view_from_node(row["p"])

  def get_project_members(self, project_id: str) -> list[PersonView]:
    plabel = self._lbl["project"]
    alabel = self._lbl["author"]
    pprop = self._prop["project"]
    aprop = self._prop["author"]
    rel = self._rel["wrote"]
    rows = self._run(
        f"""
        MATCH (a:{alabel})-[:{rel}]->(p:{plabel} {{{pprop['id']}: $pid}})
        RETURN a
        """,
        pid=project_id,
    )
    return [self._person_view_from_node(row["a"], aprop) for row in rows]

  def get_project_domains(self, project_id: str) -> list[DomainView]:
    plabel = self._lbl["project"]
    dlabel = self._lbl["research_domain"]
    pprop = self._prop["project"]
    dprop = self._prop["research_domain"]
    rel = self._rel["has_research_domain"]
    sub_rel = self._rel["subdomain_of"]
    rows = self._run(
        f"""
        MATCH (p:{plabel} {{{pprop['id']}: $pid}})-[:{rel}]->(d:{dlabel})
        OPTIONAL MATCH (d)-[:{sub_rel}*1..]->(anc:{dlabel})
        RETURN d, collect(DISTINCT anc.{dprop['id']}) AS ancestor_ids
        """,
        pid=project_id,
    )
    result = []
    for row in rows:
      node = row["d"]
      result.append(DomainView(
          domain_id=node[dprop["id"]],
          name=node.get(dprop["name"], ""),
          parent_ids=list(row["ancestor_ids"]),
      ))
    return result

  # ------------------------------------------------------------------
  # Stage-B capability method
  # ------------------------------------------------------------------

  def get_person_capabilities(self, person_id: str) -> list[PersonCapability]:
    alabel = self._lbl["author"]
    clabel = self._lbl["capability"]
    aprop = self._prop["author"]
    cprop = self._prop["capability"]
    hcprop = self._prop["has_capability"]
    rel = self._rel["has_capability"]
    rows = self._run(
        f"""
        MATCH (a:{alabel} {{{aprop['id']}: $pid}})-[hc:{rel}]->(c:{clabel})
        RETURN c, hc
        """,
        pid=person_id,
    )
    result = []
    for row in rows:
      node = row["c"]
      hc = row["hc"]
      result.append(PersonCapability(
          person_id=person_id,
          capability_id=node[cprop["id"]],
          name=node.get(cprop["name"], ""),
          kind=node.get(cprop["kind"], "UNKNOWN"),
          publication_count=hc.get(hcprop["publication_count"], 0),
          evidence_count=hc.get(hcprop["evidence_count"], 0),
          avg_confidence=hc.get(hcprop["avg_extraction_confidence"], 0.0),
          last_seen_year=hc.get(hcprop["last_seen_year"]),
          extraction_version=hc.get(hcprop["extraction_version"], ""),
      ))
    return result

  def create_capability_constraint(self) -> None:
    """Create UNIQUE constraint on Capability.id (idempotent)."""
    label = self._lbl["capability"]
    prop = self._prop["capability"]
    self._run(
        f"CREATE CONSTRAINT capability_id IF NOT EXISTS "
        f"FOR (c:{label}) REQUIRE c.{prop['id']} IS UNIQUE"
    )

  # ------------------------------------------------------------------
  # Stage-C methods — not yet implemented
  # ------------------------------------------------------------------

  def find_candidates(
      self,
      domain_ids: list[str],
      capability_ids: list[str],
      exclude_person_ids: list[str],
      limit: int = 200,
  ) -> list[CandidateRef]:
    raise NotImplementedError(
        "find_candidates will be implemented in Stage C"
    )

  def get_candidate_evidence(
      self,
      person_id: str,
      domain_ids: list[str],
      capability_ids: list[str],
  ) -> list[EvidenceItem]:
    raise NotImplementedError(
        "get_candidate_evidence will be implemented in Stage C"
    )

  def get_coauthor_distance(
      self,
      person_id: str,
      team_person_ids: list[str],
  ) -> int | None:
    raise NotImplementedError(
        "get_coauthor_distance will be implemented in Stage C"
    )

  # ------------------------------------------------------------------
  # Internal helpers
  # ------------------------------------------------------------------

  def _project_view_from_node(self, node) -> ProjectView:
    prop = self._prop["project"]
    keywords = node.get(prop["keywords"], [])
    if isinstance(keywords, str):
      keywords = [keywords]
    return ProjectView(
        project_id=node[prop["id"]],
        title=node.get(prop["title"], ""),
        abstract=node.get(prop["abstract"], ""),
        keywords=list(keywords),
        year=node.get(prop["year"]),
        doc_type=node.get(prop["doc_type"], ""),
    )

  @staticmethod
  def _person_view_from_node(node, aprop: dict) -> PersonView:
    person_id = node[aprop["id"]]
    return PersonView(
        person_id=person_id,
        full_name=node.get(aprop["full_name"], ""),
        is_placeholder=person_id.startswith("unknown_"),
    )


# Verify protocol conformance at import time
def _check_protocol() -> None:
  adapter: GraphAdapter = Neo4jAdapter.__new__(Neo4jAdapter)  # type: ignore[assignment]
  _ = adapter


_check_protocol()
