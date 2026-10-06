import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase


REQUIRED_UNIQUE_KEYS = {
    ("Project", "halId"),
    ("Author", "halId"),
    ("Conference", "conferenceId"),
    ("ResearchDomain", "id"),
    ("Organization", "halId"),
}

CONSTRAINTS_QUERY = (
    "SHOW CONSTRAINTS YIELD type, entityType, labelsOrTypes, properties "
    "RETURN type, entityType, labelsOrTypes, properties"
)

DUPLICATE_IDS_QUERY = """
MATCH (n:Project)
WHERE n.halId IS NOT NULL
WITH 'Project' AS entity, n.halId AS id, count(*) AS duplicates
WHERE duplicates > 1
RETURN entity, id, duplicates
UNION ALL
MATCH (n:Author)
WHERE n.halId IS NOT NULL
WITH 'Author' AS entity, n.halId AS id, count(*) AS duplicates
WHERE duplicates > 1
RETURN entity, id, duplicates
UNION ALL
MATCH (n:Conference)
WHERE n.conferenceId IS NOT NULL
WITH 'Conference' AS entity, n.conferenceId AS id, count(*) AS duplicates
WHERE duplicates > 1
RETURN entity, id, duplicates
UNION ALL
MATCH (n:ResearchDomain)
WHERE n.id IS NOT NULL
WITH 'ResearchDomain' AS entity, n.id AS id, count(*) AS duplicates
WHERE duplicates > 1
RETURN entity, id, duplicates
UNION ALL
MATCH (n:Organization)
WHERE n.halId IS NOT NULL
WITH 'Organization' AS entity, n.halId AS id, count(*) AS duplicates
WHERE duplicates > 1
RETURN entity, id, duplicates
"""

DIAGNOSTIC_QUERIES = {
    "duplicate_ids": (
        "Find duplicate non-null node identifiers across the repository's "
        "five keyed node labels.",
        DUPLICATE_IDS_QUERY,
        {},
    ),
    "projects_without_authors": (
        "Find Project nodes with no incoming WROTE relationship from Author.",
        "MATCH (p:Project) "
        "WHERE NOT (p)<-[:WROTE]-(:Author) "
        "RETURN p.halId AS project_id",
        {},
    ),
    "projects_without_domains": (
        "Find Project nodes with no outgoing HAS_RESEARCH_DOMAIN relationship.",
        "MATCH (p:Project) "
        "WHERE NOT (p)-[:HAS_RESEARCH_DOMAIN]->(:ResearchDomain) "
        "RETURN p.halId AS project_id",
        {},
    ),
    "orphan_research_domains": (
        "Find ResearchDomain nodes with no project or hierarchy relationship.",
        "MATCH (d:ResearchDomain) "
        "WHERE NOT (:Project)-[:HAS_RESEARCH_DOMAIN]->(d) "
        "AND NOT (d)-[:SUBDOMAIN_OF]-(:ResearchDomain) "
        "RETURN d.id AS domain_id",
        {},
    ),
    "orphan_organizations": (
        "Find Organization nodes with no project association or PART_OF edge.",
        "MATCH (o:Organization) "
        "WHERE NOT (:Project)-[:HAS_ORGANIZATION]->(o) "
        "AND NOT (o)-[:PART_OF]-(:Organization) "
        "RETURN o.halId AS organization_id",
        {},
    ),
    "bare_organizations": (
        "Find Organization nodes missing a non-blank name or type.",
        "MATCH (o:Organization) "
        "WHERE o.name IS NULL OR trim(toString(o.name)) = '' "
        "OR o.type IS NULL OR trim(toString(o.type)) = '' "
        "RETURN o.halId AS organization_id, o.name AS name, o.type AS type",
        {},
    ),
    "relationship_multiplicity": (
        "Find repeated relationships between the same keyed endpoints.",
        """
MATCH (a:Author)-[r:WROTE]->(p:Project)
WITH 'WROTE' AS relationship, a.halId AS source_id,
     p.halId AS target_id, count(r) AS multiplicity
WHERE multiplicity > 1
RETURN relationship, source_id, target_id, multiplicity
UNION ALL
MATCH (p:Project)-[r:HAS_RESEARCH_DOMAIN]->(d:ResearchDomain)
WITH 'HAS_RESEARCH_DOMAIN' AS relationship, p.halId AS source_id,
     d.id AS target_id, count(r) AS multiplicity
WHERE multiplicity > 1
RETURN relationship, source_id, target_id, multiplicity
UNION ALL
MATCH (p:Project)-[r:PRESENTED_AT]->(c:Conference)
WITH 'PRESENTED_AT' AS relationship, p.halId AS source_id,
     c.conferenceId AS target_id, count(r) AS multiplicity
WHERE multiplicity > 1
RETURN relationship, source_id, target_id, multiplicity
UNION ALL
MATCH (p:Project)-[r:HAS_ORGANIZATION]->(o:Organization)
WITH 'HAS_ORGANIZATION' AS relationship, p.halId AS source_id,
     o.halId AS target_id, count(r) AS multiplicity
WHERE multiplicity > 1
RETURN relationship, source_id, target_id, multiplicity
UNION ALL
MATCH (d:ResearchDomain)-[r:SUBDOMAIN_OF]->(parent:ResearchDomain)
WITH 'SUBDOMAIN_OF' AS relationship, d.id AS source_id,
     parent.id AS target_id, count(r) AS multiplicity
WHERE multiplicity > 1
RETURN relationship, source_id, target_id, multiplicity
UNION ALL
MATCH (o:Organization)-[r:PART_OF]->(parent:Organization)
WITH 'PART_OF' AS relationship, o.halId AS source_id,
     parent.halId AS target_id, count(r) AS multiplicity
WHERE multiplicity > 1
RETURN relationship, source_id, target_id, multiplicity
""",
        {},
    ),
    "unknown_authors": (
        "Find Author identifiers generated with the unknown_ fallback prefix.",
        "MATCH (a:Author) "
        "WHERE a.halId STARTS WITH $prefix "
        "RETURN a.halId AS author_id, a.fullName AS full_name",
        {"prefix": "unknown_"},
    ),
}


def _record_to_dict(record: Any) -> dict:
  if isinstance(record, dict):
    return record
  return dict(record)


def _run_query(session: Any, query: str, parameters: dict) -> list[dict]:
  return [
      _record_to_dict(record)
      for record in session.run(query, **parameters)
  ]


def _check_unique_constraints(session: Any) -> dict:
  records = _run_query(session, CONSTRAINTS_QUERY, {})
  present_keys = {
      (labels[0], properties[0])
      for record in records
      if record.get("type") == "UNIQUENESS"
      and record.get("entityType") == "NODE"
      and isinstance((labels := record.get("labelsOrTypes")), list)
      and len(labels) == 1
      and isinstance((properties := record.get("properties")), list)
      and len(properties) == 1
  }
  missing = [
      {"label": label, "property": property_name}
      for label, property_name in sorted(REQUIRED_UNIQUE_KEYS - present_keys)
  ]
  return {
      "name": "unique_id_constraints",
      "classification": "preventive",
      "purpose": (
          "Verify that uniqueness constraints prevent future duplicate "
          "identifiers for the five keyed node labels."
      ),
      "status": "findings" if missing else "pass",
      "finding_count": len(missing),
      "findings": missing,
  }


def run_integrity_checks(driver: Any) -> dict:
  """Run read-only Neo4j integrity checks and classify controls and findings."""
  checks = []
  with driver.session() as session:
    checks.append(_check_unique_constraints(session))
    for name, (purpose, query, parameters) in DIAGNOSTIC_QUERIES.items():
      findings = _run_query(session, query, parameters)
      checks.append({
          "name": name,
          "classification": "diagnostic",
          "purpose": purpose,
          "status": "findings" if findings else "pass",
          "finding_count": len(findings),
          "findings": findings,
      })

  return {
      "summary": {
          "check_count": len(checks),
          "preventive_check_count": sum(
              check["classification"] == "preventive" for check in checks
          ),
          "diagnostic_check_count": sum(
              check["classification"] == "diagnostic" for check in checks
          ),
          "checks_with_findings": sum(
              check["status"] == "findings" for check in checks
          ),
          "finding_count": sum(check["finding_count"] for check in checks),
      },
      "checks": checks,
  }


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
    report = run_integrity_checks(driver)
  finally:
    driver.close()

    reports_dir = Path(__file__).resolve().parents[2] / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "neo4j_integrity_report.json"
    report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
  main()
