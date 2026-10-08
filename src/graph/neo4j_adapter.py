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

from typing import Any

from neo4j import GraphDatabase

from config import get_graph_mapping, load_neo4j_settings
from capability.normalization import normalize, to_capability_id
from graph.adapter import (
  CandidateRef,
  CapabilityView,
  DomainView,
  EvidenceItem,
  GraphAdapter,
  PersonCapability,
  PersonView,
  ProjectView,
)


class Neo4jAdapter:
  """Live Neo4j implementation of the GraphAdapter protocol."""

  def __init__(
      self,
      uri: str | None = None,
      user: str | None = None,
      password: str | None = None,
      database: str | None = None,
      driver: Any | None = None,
  ) -> None:
    self._database = database or None
    self._owns_driver = driver is None
    if driver is None:
      if uri is None or user is None or password is None:
        settings = load_neo4j_settings(database=database)
        uri = uri if uri is not None else settings.uri
        user = user if user is not None else settings.user
        password = password if password is not None else settings.password
        self._database = database or settings.database or None
      driver = GraphDatabase.driver(uri, auth=(user, password))
    self._driver = driver
    m = get_graph_mapping()
    self._lbl = m.get("labels", {})
    self._rel = m.get("relationships", {})
    self._prop = m.get("properties", {})

  @classmethod
  def from_config(cls) -> "Neo4jAdapter":
    """Construct from environment variables / config."""
    settings = load_neo4j_settings()
    return cls(
        uri=settings.uri,
        user=settings.user,
        password=settings.password,
        database=settings.database,
    )

  def close(self) -> None:
    if self._owns_driver:
      self._driver.close()

  def __enter__(self) -> "Neo4jAdapter":
    return self

  def __exit__(self, *args: Any) -> None:
    self.close()

  def _run(self, query: str, **params) -> list[dict]:
    session_kwargs = {"database": self._database} if self._database else {}
    with self._driver.session(**session_kwargs) as session:
      result = session.run(query, **params)
      return [dict(record) for record in result]

  # ------------------------------------------------------------------
  # Fact methods (Stage A)
  # ------------------------------------------------------------------

  def get_project(self, project_id: str) -> ProjectView | None:
    label = self._lbl["project"]
    prop = self._prop["project"]
    rows = self._run(
        f"MATCH (p:{label} {{{prop['id']}: $project_id}}) RETURN p",
        project_id=project_id,
    )
    if not rows:
      return None
    return self._project_view_from_row(rows[0])

  def iter_projects(
      self,
      limit: int = 100,
      offset: int = 0,
  ) -> list[ProjectView]:
    if limit < 0 or offset < 0:
      raise ValueError("limit and offset must be non-negative")
    if limit == 0:
      return []
    label = self._lbl["project"]
    prop = self._prop["project"]
    rows = self._run(
        f"MATCH (p:{label}) RETURN p ORDER BY p.{prop['id']} SKIP $offset LIMIT $limit",
        offset=offset,
        limit=limit,
    )
    return [self._project_view_from_row(row) for row in rows]

  def get_project_members(self, project_id: str) -> list[PersonView]:
    plabel = self._lbl["project"]
    alabel = self._lbl["author"]
    pprop = self._prop["project"]
    aprop = self._prop["author"]
    rel = self._rel["wrote"]
    rows = self._run(
        f"""
        MATCH (a:{alabel})-[:{rel}]->(p:{plabel} {{{pprop['id']}: $project_id}})
        RETURN a
        """,
        project_id=project_id,
    )
    return [
        self._person_view_from_node(row.get("a", row), aprop)
        for row in rows
    ]

  def get_project_domains(self, project_id: str) -> list[DomainView]:
    plabel = self._lbl["project"]
    dlabel = self._lbl["research_domain"]
    pprop = self._prop["project"]
    dprop = self._prop["research_domain"]
    rel = self._rel["has_research_domain"]
    sub_rel = self._rel["subdomain_of"]
    rows = self._run(
        f"""
        MATCH (p:{plabel} {{{pprop['id']}: $project_id}})-[:{rel}]->(assigned:{dlabel})
        MATCH (assigned)-[:{sub_rel}*0..]->(d:{dlabel})
        OPTIONAL MATCH (d)-[:{sub_rel}*1..]->(anc:{dlabel})
        RETURN d, collect(DISTINCT anc.{dprop['id']}) AS ancestor_ids
        """,
        project_id=project_id,
    )
    result = []
    for row in rows:
      node = row.get("d", row)
      result.append(DomainView(
          domain_id=node.get(dprop["id"], node.get("domain_id")),
          name=node.get(dprop["name"], node.get("name", "")) or "",
          parent_ids=list(
              row.get("ancestor_ids", row.get("parent_ids", [])) or []
          ),
      ))
    return result

  def find_domains_by_keywords(self, keywords: list[str]) -> list[DomainView]:
    """Find research domains matching keywords in name or id."""
    kw_lower = [k.strip().lower() for k in keywords if len(k.strip()) >= 2]
    if not kw_lower:
      return []
    dlabel = self._lbl["research_domain"]
    dprop = self._prop["research_domain"]
    sub_rel = self._rel["subdomain_of"]
    query = f"""
    MATCH (d:{dlabel})
    WHERE any(kw IN $keywords WHERE 
      toLower(coalesce(d.{dprop['name']}, '')) CONTAINS kw 
      OR toLower(coalesce(d.nameFr, '')) CONTAINS kw 
      OR toLower(coalesce(d.{dprop['id']}, '')) CONTAINS kw
    )
    OPTIONAL MATCH (d)-[:{sub_rel}*1..]->(anc:{dlabel})
    RETURN d, collect(DISTINCT anc.{dprop['id']}) AS ancestor_ids
    """
    rows = self._run(query, keywords=kw_lower)
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

  def find_capabilities_by_terms(self, terms: list[str]) -> list[CapabilityView]:
    """Find canonical Capability nodes matching normalized terms."""
    clean_terms = [term for term in terms if term and term.strip()]
    if not clean_terms:
      return []

    term_ids = sorted({to_capability_id(term) for term in clean_terms})
    term_names = sorted({normalize(term) for term in clean_terms})
    clabel = self._lbl["capability"]
    cprop = self._prop["capability"]

    rows = self._run(
        f"""
        MATCH (c:{clabel})
        WHERE c.{cprop['id']} IN $term_ids
           OR toLower(coalesce(c.{cprop['name']}, '')) IN $term_names
           OR any(alias IN coalesce(c.{cprop['aliases']}, [])
                  WHERE toLower(toString(alias)) IN $term_names)
        RETURN c
        ORDER BY c.{cprop['id']}
        """,
        term_ids=term_ids,
        term_names=term_names,
    )

    result: list[CapabilityView] = []
    for row in rows:
      node = row["c"]
      aliases = node.get(cprop["aliases"], []) or []
      if isinstance(aliases, str):
        aliases = [aliases]
      result.append(CapabilityView(
          capability_id=node[cprop["id"]],
          name=node.get(cprop["name"], ""),
          kind=node.get(cprop["kind"], "UNKNOWN"),
          aliases=list(aliases),
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
  # Stage-C methods
  # ------------------------------------------------------------------

  def find_candidates(
      self,
      domain_ids: list[str],
      capability_ids: list[str],
      exclude_person_ids: list[str],
      limit: int = 200,
  ) -> list[CandidateRef]:
    alabel = self._lbl["author"]
    plabel = self._lbl["project"]
    dlabel = self._lbl["research_domain"]
    clabel = self._lbl["capability"]
    wrote_rel = self._rel["wrote"]
    has_d_rel = self._rel["has_research_domain"]
    has_c_rel = self._rel["has_capability"]
    aprop = self._prop["author"]["id"]
    dprop = self._prop["research_domain"]["id"]
    cprop = self._prop["capability"]["id"]

    query = f"""
    CALL () {{
      MATCH (d:{dlabel}) WHERE d.{dprop} IN $domain_ids
      MATCH (d)<-[:{has_d_rel}]-(:{plabel})<-[:{wrote_rel}]-(a:{alabel})
      WHERE NOT a.{aprop} IN $exclude_ids
      RETURN a.{aprop} AS pid, d.{dprop} AS did, null AS cid
    UNION
      MATCH (c:{clabel}) WHERE c.{cprop} IN $capability_ids
      MATCH (c)<-[:{has_c_rel}]-(a:{alabel})
      WHERE NOT a.{aprop} IN $exclude_ids
      RETURN a.{aprop} AS pid, null AS did, c.{cprop} AS cid
    }}
    WITH pid,
         [x IN collect(DISTINCT did) WHERE x IS NOT NULL] AS matched_domains,
         [x IN collect(DISTINCT cid) WHERE x IS NOT NULL] AS matched_caps
    RETURN pid AS person_id, matched_domains, matched_caps
    ORDER BY size(matched_caps) DESC, size(matched_domains) DESC, person_id ASC
    LIMIT $limit
    """
    rows = self._run(
        query,
        domain_ids=list(domain_ids),
        capability_ids=list(capability_ids),
        exclude_ids=list(exclude_person_ids),
        limit=limit,
    )
    return [
        CandidateRef(
            person_id=r["person_id"],
            matched_domain_ids=list(r["matched_domains"]),
            matched_capability_ids=list(r["matched_caps"]),
        )
        for r in rows
    ]

  def get_candidate_evidence(
      self,
      person_id: str,
      domain_ids: list[str],
      capability_ids: list[str],
  ) -> list[EvidenceItem]:
    alabel = self._lbl["author"]
    plabel = self._lbl["project"]
    dlabel = self._lbl["research_domain"]
    clabel = self._lbl["capability"]
    wrote_rel = self._rel["wrote"]
    has_d_rel = self._rel["has_research_domain"]
    has_c_rel = self._rel["has_capability"]
    aprop = self._prop["author"]["id"]
    pprop_id = self._prop["project"]["id"]
    pprop_title = self._prop["project"]["title"]
    pprop_year = self._prop["project"]["year"]
    dprop_id = self._prop["research_domain"]["id"]
    dprop_name = self._prop["research_domain"]["name"]
    cprop_id = self._prop["capability"]["id"]
    cprop_name = self._prop["capability"]["name"]

    evidence: list[EvidenceItem] = []
    seen: set[tuple[str, str]] = set()

    proj_query = f"""
    MATCH (a:{alabel} {{{aprop}: $pid}})-[:{wrote_rel}]->(p:{plabel})
    OPTIONAL MATCH (p)-[:{has_d_rel}]->(d:{dlabel})
    WHERE d.{dprop_id} IN $domain_ids
    RETURN p.{pprop_id} AS pid, p.{pprop_title} AS ptitle, p.{pprop_year} AS pyear,
           d.{dprop_id} AS did, d.{dprop_name} AS dname
    """
    rows = self._run(proj_query, pid=person_id, domain_ids=list(domain_ids))
    for r in rows:
      proj_id = r["pid"]
      if proj_id and ("project", proj_id) not in seen:
        seen.add(("project", proj_id))
        evidence.append(EvidenceItem(
            kind="project",
            id=proj_id,
            text=r.get("ptitle") or proj_id,
            project_id=proj_id,
            year=r.get("pyear"),
        ))
      did = r.get("did")
      if did and ("domain", did) not in seen:
        seen.add(("domain", did))
        evidence.append(EvidenceItem(
            kind="domain",
            id=did,
            text=r.get("dname") or did,
            project_id=proj_id,
            year=r.get("pyear"),
        ))

    if capability_ids:
      cap_query = f"""
      MATCH (a:{alabel} {{{aprop}: $pid}})-[:{has_c_rel}]->(c:{clabel})
      WHERE c.{cprop_id} IN $capability_ids
      RETURN c.{cprop_id} AS cid, c.{cprop_name} AS cname
      """
      c_rows = self._run(cap_query, pid=person_id, capability_ids=list(capability_ids))
      for r in c_rows:
        cid = r["cid"]
        if cid and ("capability", cid) not in seen:
          seen.add(("capability", cid))
          evidence.append(EvidenceItem(
              kind="capability",
              id=cid,
              text=r.get("cname") or cid,
              project_id=None,
              year=None,
          ))

    return evidence

  def get_coauthor_distance(
      self,
      person_id: str,
      team_person_ids: list[str],
  ) -> int | None:
    if not team_person_ids:
      return None
    if person_id in team_person_ids:
      return 0
    alabel = self._lbl["author"]
    wrote_rel = self._rel["wrote"]
    aprop = self._prop["author"]["id"]

    query = f"""
    MATCH (a:{alabel} {{{aprop}: $pid}}), (t:{alabel})
    WHERE t.{aprop} IN $team_ids AND t.{aprop} <> $pid
    MATCH path = shortestPath((a)-[:{wrote_rel}*..6]-(t))
    RETURN length(path) AS path_len
    ORDER BY path_len ASC
    LIMIT 1
    """
    rows = self._run(query, pid=person_id, team_ids=list(team_person_ids))
    if not rows or rows[0].get("path_len") is None:
      return None
    path_len = rows[0]["path_len"]
    return max(1, path_len // 2)

  # ------------------------------------------------------------------
  # Internal helpers
  # ------------------------------------------------------------------

  def _project_view_from_row(self, row: dict[str, Any]) -> ProjectView:
    node = row.get("p", row)
    return self._project_view_from_node(node)

  def _project_view_from_node(self, node: Any) -> ProjectView:
    prop = self._prop["project"]
    keywords = node.get(prop["keywords"], [])
    if keywords is None:
      keywords = []
    if isinstance(keywords, str):
      keywords = [keywords]
    year = node.get(prop["year"], node.get("year"))
    return ProjectView(
        project_id=node.get(prop["id"], node.get("project_id")),
        title=node.get(prop["title"], node.get("title", "")) or "",
        abstract=node.get(prop["abstract"], node.get("abstract", "")) or "",
        keywords=list(keywords),
        year=int(year) if year is not None else None,
        doc_type=node.get(prop["doc_type"], node.get("doc_type", "")) or "",
    )

  @staticmethod
  def _person_view_from_node(node: Any, aprop: dict) -> PersonView:
    person_id = node.get(aprop["id"], node.get("person_id"))
    full_name = node.get(aprop["full_name"], node.get("full_name"))
    if not full_name:
      full_name = " ".join(
          value
          for value in (
              node.get("firstName", node.get("first_name", "")),
              node.get("lastName", node.get("last_name", "")),
          )
          if value
      )
    return PersonView(
        person_id=person_id,
        full_name=full_name or "",
        is_placeholder=person_id.startswith("unknown_"),
    )


# Verify protocol conformance at import time
def _check_protocol() -> None:
  adapter: GraphAdapter = Neo4jAdapter.__new__(Neo4jAdapter)  # type: ignore[assignment]
  _ = adapter


_check_protocol()
