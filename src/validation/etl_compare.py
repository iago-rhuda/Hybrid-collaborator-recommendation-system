import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase

from export_pipeline_csv import CSV_SCHEMAS, build_csv_tables_from_hal_docs


ENTITY_CONFIG = {
    "projects": ("Project", "halId"),
    "authors": ("Author", "halId"),
    "conferences": ("Conference", "conferenceId"),
    "organizations": ("Organization", "halId"),
    "research_domains": ("ResearchDomain", "id"),
}

RELATION_CONFIG = {
    "project_authors": (
        "MATCH (source:Author)-[r:WROTE]->(target:Project) "
        "WHERE target.halId IN $project_ids "
        "RETURN target.halId AS source, source.halId AS target, count(r) AS count"
    ),
    "project_conferences": (
        "MATCH (source:Project)-[r:PRESENTED_AT]->(target:Conference) "
        "WHERE source.halId IN $project_ids "
        "RETURN source.halId AS source, target.conferenceId AS target, count(r) AS count"
    ),
    "project_organizations": (
        "MATCH (source:Project)-[r:HAS_ORGANIZATION]->(target:Organization) "
        "WHERE source.halId IN $project_ids "
        "RETURN source.halId AS source, target.halId AS target, count(r) AS count"
    ),
    "project_research_domains": (
        "MATCH (source:Project)-[r:HAS_RESEARCH_DOMAIN]->(target:ResearchDomain) "
        "WHERE source.halId IN $project_ids "
        "RETURN source.halId AS source, target.id AS target, count(r) AS count"
    ),
    "organization_relationships": (
        "MATCH (source:Organization)-[r:PART_OF]->(target:Organization) "
        "WHERE source.halId IN $organization_ids OR target.halId IN $organization_ids "
        "RETURN source.halId AS source, target.halId AS target, count(r) AS count"
    ),
    "research_domain_hierarchy": (
        "MATCH (source:ResearchDomain)-[r:SUBDOMAIN_OF]->(target:ResearchDomain) "
        "WHERE source.id IN $domain_ids OR target.id IN $domain_ids "
        "RETURN source.id AS source, target.id AS target, count(r) AS count"
    ),
}


def _record_to_dict(record: Any) -> dict:
  if isinstance(record, dict):
    return record
  return dict(record)


def _records_for_query(tx, query: str, parameters: dict) -> list[dict]:
  return [
      _record_to_dict(record)
      for record in tx.run(query, **parameters)
  ]


def read_neo4j_state(driver, expected_tables: dict) -> dict:
  """Read only graph facts corresponding to the transformed ETL fixture."""
  state = {"entities": {}, "relationships": {}}

  with driver.session() as session:
    for table_name, (label, key_property) in ENTITY_CONFIG.items():
      expected = expected_tables[table_name]
      keys = list(expected)
      query = (
          f"UNWIND $keys AS key "
          f"OPTIONAL MATCH (n:{label} {{{key_property}: key}}) "
          "RETURN key AS id, count(n) AS count, collect(n{.*}) AS records"
      )
      rows = _records_for_query(session, query, {"keys": keys})
      state["entities"][table_name] = {
          str(row["id"]): {
              "count": row["count"],
              "records": row["records"],
          }
          for row in rows
      }

    project_ids = list(expected_tables["projects"])
    organization_ids = list(expected_tables["organizations"])
    domain_ids = list(expected_tables["research_domains"])

    for table_name, query in RELATION_CONFIG.items():
      if table_name.startswith("project_"):
        parameters = {"project_ids": project_ids}
      elif table_name == "organization_relationships":
        parameters = {"organization_ids": organization_ids}
      else:
        parameters = {"domain_ids": domain_ids}

      rows = _records_for_query(session, query, parameters)
      state["relationships"][table_name] = {
          (str(row["source"]), str(row["target"])): row["count"]
          for row in rows
      }

  return state


def _key_as_string(key) -> str:
  return str(key)


def _expected_relation_counts(table: dict, source_field: str, target_field: str):
  counts = Counter(
      (
          _key_as_string(row[source_field]),
          _key_as_string(row[target_field]),
      )
      for row in table.values()
  )
  return dict(counts)


def compare_expected_to_neo4j(
    expected_tables: dict,
    neo4j_state: dict,
    raw_docs: list[dict] | None = None,
) -> dict:
  """Compare transformed CSV tables with a state snapshot read from Neo4j."""
  report = {
      "summary": {
          "expected_project_count": len(expected_tables["projects"]),
          "errors": 0,
          "warnings": 0,
      },
      "entities": {},
      "relationships": {},
      "source_duplicates": {},
  }
  errors = []
  warnings = []

  for table_name, (_label, key_property) in ENTITY_CONFIG.items():
    expected_entities = expected_tables[table_name]
    actual_entities = neo4j_state["entities"].get(table_name, {})
    entity_report = {
        "expected_count": len(expected_entities),
        "matched_count": 0,
        "missing_ids": [],
        "duplicate_ids": [],
        "field_mismatches": [],
    }
    fields = [field for field in CSV_SCHEMAS[table_name] if field != key_property]

    for key, expected in expected_entities.items():
      string_key = _key_as_string(key)
      actual = actual_entities.get(string_key, {"count": 0, "records": []})
      actual_count = actual["count"]
      actual_records = actual["records"] or []
      if actual_count == 0:
        entity_report["missing_ids"].append(string_key)
        errors.append((table_name, string_key, "missing_node"))
        continue
      entity_report["matched_count"] += 1
      if actual_count > 1:
        entity_report["duplicate_ids"].append({
            "id": string_key,
            "count": actual_count,
        })
        errors.append((table_name, string_key, "duplicate_node"))
      if not actual_records:
        continue

      actual_record = actual_records[0]
      mismatched_fields = {}
      for field_name in fields:
        expected_value = expected.get(field_name)
        actual_value = actual_record.get(field_name)
        if expected_value != actual_value:
          mismatched_fields[field_name] = {
              "expected": expected_value,
              "actual": actual_value,
          }
      if mismatched_fields:
        entity_report["field_mismatches"].append({
            "id": string_key,
            "fields": mismatched_fields,
        })
        errors.append((table_name, string_key, "field_mismatch"))

    report["entities"][table_name] = entity_report

  relation_specs = {
      "project_authors": ("projectHalId", "authorHalId"),
      "project_conferences": ("projectHalId", "conferenceId"),
      "project_organizations": ("projectHalId", "organizationHalId"),
      "project_research_domains": ("projectHalId", "domainId"),
      "organization_relationships": ("sourceId", "targetId"),
      "research_domain_hierarchy": ("childId", "parentId"),
  }
  for table_name, (source_field, target_field) in relation_specs.items():
    expected_counts = _expected_relation_counts(
        expected_tables[table_name],
        source_field,
        target_field,
    )
    actual_counts = neo4j_state["relationships"].get(table_name, {})
    missing = []
    unexpected = []
    duplicates = []

    for pair, expected_count in expected_counts.items():
      actual_count = actual_counts.get(pair, 0)
      if actual_count < expected_count:
        missing.append({
            "source": pair[0],
            "target": pair[1],
            "expected_count": expected_count,
            "actual_count": actual_count,
        })
      elif actual_count > expected_count:
        duplicates.append({
            "source": pair[0],
            "target": pair[1],
            "expected_count": expected_count,
            "actual_count": actual_count,
        })

    for pair, actual_count in actual_counts.items():
      if pair not in expected_counts:
        unexpected.append({
            "source": pair[0],
            "target": pair[1],
            "actual_count": actual_count,
        })

    relation_report = {
        "expected_count": sum(expected_counts.values()),
        "actual_count": sum(actual_counts.values()),
        "missing": missing,
        "unexpected": unexpected,
        "duplicates": duplicates,
    }
    report["relationships"][table_name] = relation_report
    if missing or unexpected or duplicates:
      errors.append((table_name, "", "relationship_mismatch"))

  if raw_docs is not None:
    project_ids = [
        _key_as_string(doc.get("halId_s", doc.get("docid", "Unknown")))
        for doc in raw_docs
    ]
    duplicate_projects = {
        project_id: count
        for project_id, count in Counter(project_ids).items()
        if count > 1
    }
    report["source_duplicates"]["project_ids"] = duplicate_projects
    report["source_duplicates"]["duplicate_project_record_count"] = sum(
        count - 1 for count in duplicate_projects.values()
    )
    if duplicate_projects:
      warnings.append(("projects", "duplicate_input_records"))

  report["summary"]["errors"] = len(errors)
  report["summary"]["warnings"] = len(warnings)
  report["summary"]["error_categories"] = [
      {"table": table, "id": key, "code": code}
      for table, key, code in errors
  ]
  report["summary"]["warning_categories"] = [
      {"table": table, "code": code}
      for table, code in warnings
  ]
  hypotheses = []
  if any(code == "missing_node" for _, _, code in errors):
    hypotheses.append(
        "Expected nodes absent from this Neo4j instance may indicate an "
        "incomplete or different database load, or a snapshot outside the "
        "database's loaded corpus."
    )
  if any(code == "field_mismatch" for _, _, code in errors):
    hypotheses.append(
        "Property mismatches may be stale values: the current persistence "
        "queries use ON CREATE SET and do not refresh existing nodes."
    )
  if any(code == "duplicate_node" for _, _, code in errors):
    hypotheses.append(
        "Repeated nodes with one business identifier may indicate missing or "
        "previously unenforced uniqueness constraints, or legacy duplicate data."
    )
  if any(code == "relationship_mismatch" for _, _, code in errors):
    hypotheses.append(
        "Missing expected relationships may indicate a partial load or a "
        "transform/persistence loss; unexpected relationships may come from "
        "other corpus records because the graph comparison is scoped to the "
        "selected snapshot's project and endpoint identifiers."
    )
  if report["source_duplicates"].get("duplicate_project_record_count", 0):
    hypotheses.append(
        "Duplicate project IDs in the HAL input can be collapsed by the CSV "
        "table builder's key-based deduplication, so inspect the raw snapshot "
        "before interpreting transformed row counts."
    )
  report["cause_hypotheses"] = hypotheses
  return report


def compare_hal_docs_to_neo4j(docs: list[dict], driver) -> dict:
  """Transform HAL documents and compare them with Neo4j."""
  expected_tables = build_csv_tables_from_hal_docs(docs)
  neo4j_state = read_neo4j_state(driver, expected_tables)
  return compare_expected_to_neo4j(expected_tables, neo4j_state, docs)


def _write_report(report: dict, output_path: Path) -> None:
  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(
      json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
      encoding="utf-8",
  )


def main():
  parser = argparse.ArgumentParser(
      description="Compare transformed HAL snapshot data with Neo4j."
  )
  parser.add_argument("snapshot", type=Path, help="HAL snapshot JSONL file.")
  parser.add_argument(
      "--output",
      type=Path,
      default=Path("reports/etl_compare.json"),
      help="Path to the JSON comparison report.",
  )
  args = parser.parse_args()

  docs = []
  with args.snapshot.open(encoding="utf-8") as snapshot_file:
    for line_number, line in enumerate(snapshot_file, start=1):
      if not line.strip():
        continue
      try:
        docs.append(json.loads(line))
      except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid JSON on snapshot line {line_number}: {error}"
        ) from error

  load_dotenv()
  uri = os.getenv("NEO4J_URI")
  user = os.getenv("NEO4J_USER")
  password = os.getenv("NEO4J_PASSWORD")
  if not all((uri, user, password)):
    raise RuntimeError(
        "Set NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD before comparing."
    )

  driver = GraphDatabase.driver(uri, auth=(user, password))
  try:
    driver.verify_connectivity()
    report = compare_hal_docs_to_neo4j(docs, driver)
  finally:
    driver.close()

  _write_report(report, args.output)
  print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
  print(f"Detailed comparison written to {args.output}")


if __name__ == "__main__":
  main()
