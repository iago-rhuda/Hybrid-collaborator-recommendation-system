"""Validate the authoritative HAL ResearchDomain hierarchy without rewriting it.

ResearchDomain ids and labels are facts from HAL's taxonomy. Recommendation
logic may consume them as evidence, but must not rename, reparent, or otherwise
modify this source taxonomy to improve recommendation results.
"""

import json
import os
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase


MAX_DOMAIN_LEVELS = 3

DOMAINS_QUERY = (
    "MATCH (d:ResearchDomain) "
    "RETURN d.id AS id, d.name AS name, d.nameFr AS name_fr"
)

HIERARCHY_QUERY = (
    "MATCH (child:ResearchDomain)-[:SUBDOMAIN_OF]->"
    "(parent:ResearchDomain) "
    "RETURN child.id AS child_id, parent.id AS parent_id"
)

PROJECT_ASSOCIATIONS_QUERY = (
    "MATCH (:Project)-[:HAS_RESEARCH_DOMAIN]->(domain:ResearchDomain) "
    "RETURN DISTINCT domain.id AS domain_id"
)


def _value(item: Any, *names: str) -> Any:
  if isinstance(item, dict):
    for name in names:
      if name in item:
        return item[name]
    return None
  for name in names:
    if hasattr(item, name):
      return getattr(item, name)
  return None


def _domain_id(item: Any) -> str | None:
  value = _value(item, "id", "domain_id", "domainId")
  return str(value).strip() if value is not None else None


def _relation_ids(item: Any) -> tuple[str | None, str | None]:
  child = _value(item, "child_id", "childId")
  parent = _value(item, "parent_id", "parentId")
  return (
      str(child).strip() if child is not None else None,
      str(parent).strip() if parent is not None else None,
  )


def _find_cycles(domain_ids: set[str], edges: list[tuple[str, str]]) -> list[list[str]]:
  children_by_parent: dict[str, list[str]] = {domain_id: [] for domain_id in domain_ids}
  for child, parent in edges:
    if child in domain_ids and parent in domain_ids:
      children_by_parent[parent].append(child)

  state: dict[str, int] = {}
  stack: list[str] = []
  cycles: list[list[str]] = []
  seen_cycles: set[tuple[str, ...]] = set()

  def visit(domain_id: str) -> None:
    state[domain_id] = 1
    stack.append(domain_id)
    for child in children_by_parent[domain_id]:
      if state.get(child, 0) == 0:
        visit(child)
      elif state.get(child) == 1:
        cycle_start = stack.index(child)
        cycle = stack[cycle_start:] + [child]
        cycle_key = tuple(cycle)
        if cycle_key not in seen_cycles:
          cycles.append(cycle)
          seen_cycles.add(cycle_key)
    stack.pop()
    state[domain_id] = 2

  for domain_id in sorted(domain_ids):
    if state.get(domain_id, 0) == 0:
      visit(domain_id)
  return cycles


def _domain_depths(
    domain_ids: set[str],
    edges: list[tuple[str, str]],
    cyclic_nodes: set[str],
) -> dict[str, int]:
  parents_by_child: dict[str, list[str]] = {
      domain_id: [] for domain_id in domain_ids
  }
  for child, parent in edges:
    if child in domain_ids and parent in domain_ids:
      parents_by_child[child].append(parent)

  memo: dict[str, int] = {}

  def depth(domain_id: str, active: set[str]) -> int:
    if domain_id in memo:
      return memo[domain_id]
    if domain_id in active or domain_id in cyclic_nodes:
      return 1
    parents = parents_by_child[domain_id]
    if not parents:
      result = 1
    else:
      result = 1 + max(
          depth(parent, active | {domain_id}) for parent in parents
      )
    memo[domain_id] = result
    return result

  return {domain_id: depth(domain_id, set()) for domain_id in domain_ids}


def validate_domain_hierarchy(
    domains: list[Any],
    hierarchy: list[Any],
    project_domain_relations: list[Any] | None = None,
    *,
    max_levels: int = MAX_DOMAIN_LEVELS,
) -> dict:
  """Return hierarchy findings for domain nodes, parent edges, and project links.

  ``domains`` accepts HAL-transformed domain dataclasses or dictionaries with
  ``id``, ``name``, and optionally ``nameFr``/``name_fr``. Hierarchy entries
  use ``child_id``/``parent_id`` or ``childId``/``parentId``. Project
  associations use ``domain_id`` or ``domainId``.
  """
  if max_levels < 1:
    raise ValueError("max_levels must be at least 1.")

  domain_by_id: dict[str, Any] = {}
  domain_id_counts: dict[str, int] = {}
  malformed_names = []
  malformed_ids = []
  for index, domain in enumerate(domains):
    raw_id = _value(domain, "id", "domain_id", "domainId")
    domain_id = _domain_id(domain)
    if domain_id is None or not domain_id:
      malformed_ids.append({
          "index": index,
          "value": raw_id,
          "reason": "Domain id is missing or blank.",
      })
      continue

    domain_id_counts[domain_id] = domain_id_counts.get(domain_id, 0) + 1
    domain_by_id.setdefault(domain_id, domain)
    if any(not part for part in domain_id.split(".")) or any(
        character.isspace() for character in domain_id
    ):
      malformed_ids.append({
          "domain_id": domain_id,
          "reason": "Domain id has whitespace or an empty dotted segment.",
      })

    names = {
        "name": _value(domain, "name"),
        "name_fr": _value(domain, "name_fr", "nameFr"),
    }
    for language, name in names.items():
      if language == "name_fr" and (name is None or name == ""):
        continue
      if name is not None and (not isinstance(name, str) or not name.strip()):
        malformed_names.append({
            "domain_id": domain_id,
            "language": language,
            "value": name,
            "reason": "Domain name is blank or is not text.",
        })
    if names["name"] is None:
      malformed_names.append({
          "domain_id": domain_id,
          "language": "name",
          "value": None,
          "reason": "English domain name is missing.",
      })

  duplicate_domain_ids = [
      {"domain_id": domain_id, "count": count}
      for domain_id, count in sorted(domain_id_counts.items())
      if count > 1
  ]
  domain_ids = set(domain_by_id)
  edge_counts: dict[tuple[str, str], int] = {}
  missing_endpoints = []
  invalid_parent_rules = []
  edges = []
  for index, relation in enumerate(hierarchy):
    child, parent = _relation_ids(relation)
    if not child or not parent:
      missing_endpoints.append({
          "index": index,
          "child_id": child,
          "parent_id": parent,
          "reason": "Hierarchy relation has a missing child or parent id.",
      })
      continue

    edge = (child, parent)
    edge_counts[edge] = edge_counts.get(edge, 0) + 1
    edges.append(edge)
    absent = [domain_id for domain_id in edge if domain_id not in domain_ids]
    if absent:
      missing_endpoints.append({
          "child_id": child,
          "parent_id": parent,
          "missing_domain_ids": absent,
          "reason": "Hierarchy relation references a domain absent from the input.",
      })
    if child == parent or not child.startswith(f"{parent}."):
      invalid_parent_rules.append({
          "child_id": child,
          "parent_id": parent,
          "reason": "Parent id must be a dotted prefix of the child id.",
      })

  duplicate_edges = [
      {"child_id": child, "parent_id": parent, "count": count}
      for (child, parent), count in sorted(edge_counts.items())
      if count > 1
  ]
  cycles = _find_cycles(domain_ids, edges)
  cyclic_nodes = {domain_id for cycle in cycles for domain_id in cycle}
  depths = _domain_depths(domain_ids, edges, cyclic_nodes)
  excessive_depths = [
      {"domain_id": domain_id, "levels": level_count, "maximum": max_levels}
      for domain_id, level_count in sorted(depths.items())
      if level_count > max_levels
  ]

  associated_ids = {
      domain_id
      for relation in (project_domain_relations or [])
      if (domain_id := _domain_id(relation))
  }
  unknown_associations = [
      {"domain_id": domain_id}
      for domain_id in sorted(associated_ids - domain_ids)
  ]
  hierarchy_ids = {
      domain_id for edge in edges for domain_id in edge
  }
  orphan_domains = [
      domain_id
      for domain_id in sorted(domain_ids)
      if domain_id not in associated_ids and domain_id not in hierarchy_ids
  ]

  checks = [
      ("cycles", cycles),
      ("orphan_domains", [{"domain_id": item} for item in orphan_domains]),
      ("missing_hierarchy_endpoints", missing_endpoints),
      ("dotted_prefix_parent_rules", invalid_parent_rules),
      ("duplicate_hierarchy_edges", duplicate_edges),
      ("maximum_depth", excessive_depths),
      ("malformed_domain_ids", malformed_ids),
      ("malformed_domain_names", malformed_names),
      ("duplicate_domain_ids", duplicate_domain_ids),
      ("unknown_project_domain_associations", unknown_associations),
  ]
  report_checks = [
      {
          "name": name,
          "status": "findings" if findings else "pass",
          "finding_count": len(findings),
          "findings": findings,
      }
      for name, findings in checks
  ]
  finding_count = sum(check["finding_count"] for check in report_checks)
  return {
      "summary": {
          "domain_count": len(domain_ids),
          "hierarchy_edge_count": len(edges),
          "maximum_domain_levels": max_levels,
          "check_count": len(report_checks),
          "checks_with_findings": sum(
              check["status"] == "findings" for check in report_checks
          ),
          "finding_count": finding_count,
          "is_valid": finding_count == 0,
      },
      "checks": report_checks,
      "taxonomy_policy": (
          "ResearchDomain ids, labels, and hierarchy are authoritative HAL "
          "source facts. Recommender logic may use this taxonomy for retrieval "
          "and matching, but must not rewrite it; inferred capabilities and "
          "recommendation requirements belong in separate derived data."
      ),
  }


def _records(session: Any, query: str) -> list[dict]:
  return [dict(record) for record in session.run(query)]


def validate_neo4j_hierarchy(
    driver: Any,
    *,
    max_levels: int = MAX_DOMAIN_LEVELS,
) -> dict:
  """Read the repository's ResearchDomain graph and validate it."""
  with driver.session() as session:
    domains = _records(session, DOMAINS_QUERY)
    hierarchy = _records(session, HIERARCHY_QUERY)
    associations = _records(session, PROJECT_ASSOCIATIONS_QUERY)
  return validate_domain_hierarchy(
      domains,
      hierarchy,
      associations,
      max_levels=max_levels,
  )


def main() -> None:
  load_dotenv()
  uri = os.getenv("NEO4J_URI")
  user = os.getenv("NEO4J_USER")
  password = os.getenv("NEO4J_PASSWORD")
  if not all((uri, user, password)):
    raise RuntimeError(
        "Set NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD before checking."
    )

  driver = GraphDatabase.driver(uri, auth=(user, password))
  try:
    driver.verify_connectivity()
    report = validate_neo4j_hierarchy(driver)
  finally:
    driver.close()

  print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
  main()
