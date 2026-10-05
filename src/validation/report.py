"""Build and write reproducible HAL/ETL/Neo4j data-quality reports."""

import argparse
import json
from collections import defaultdict
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any

from processing.transformer import extract_authors_from_hal_record
from validation.hal_validator import validate_hal_documents


AUTHOR_ID_FIELDS = (
    "authIdHal_s",
    "authIdPerson_i",
    "authFirstName_s",
    "authLastName_s",
    "authEmailDomain_s",
    "authORCIDIdExt_s",
    "authGoogleScholarIdExt_s",
    "authResearcherIdIdExt_s",
    "authIdRefIdExt_s",
)

MISSINGNESS_FIELDS = {
    "hal_id": ("halId_s", "docid"),
    "title": ("title_s",),
    "abstract": ("abstract_s",),
    "keywords": ("keyword_s",),
    "doi": ("doiId_s",),
    "authors": ("authFullName_s",),
    "domains": ("primaryDomain_s", "domainAllCode_s", "domain_s"),
}

TAXONOMY_POLICY = (
    "HAL ResearchDomain IDs, labels, and hierarchy are authoritative source "
    "facts. Recommendation logic may use this taxonomy for retrieval and "
    "matching, but must not rewrite it; inferred capabilities and "
    "recommendation requirements belong in separate derived data."
)


def _as_list(value: Any) -> list[Any]:
  if value is None:
    return []
  return value if isinstance(value, list) else [value]


def _is_present(value: Any) -> bool:
  if value is None:
    return False
  if isinstance(value, (list, tuple, set)):
    return any(_is_present(item) for item in value)
  return bool(str(value).strip())


def _is_present_author_hal_id(value: Any) -> bool:
  return _is_present(value) and str(value).strip() != "0"


def _field_present(doc: dict, fields: tuple[str, ...]) -> bool:
  return any(_is_present(doc.get(field)) for field in fields)


def _unique_nonblank(values: list[Any]) -> set[str]:
  return {
      str(value).strip()
      for value in values
      if value is not None and str(value).strip()
  }


def _hal_id(doc: dict) -> str | None:
  for field in ("halId_s", "docid"):
    value = doc.get(field)
    if _is_present(value):
      return str(value).strip()
  return None


def _author_ids_and_names(docs: list[dict]) -> tuple[set[str], int, dict[str, set[str]]]:
  author_ids = set()
  unknown_author_count = 0
  name_to_ids: dict[str, set[str]] = defaultdict(set)
  for doc in docs:
    names = _as_list(doc.get("authFullName_s"))
    authors = extract_authors_from_hal_record(doc)
    for name_value, author in zip(names, authors):
      name = str(name_value or "").strip()
      author_id = author.hal_id
      author_ids.add(author_id)
      if author_id.startswith("unknown_"):
        unknown_author_count += 1
      normalized_name = " ".join(name.casefold().split())
      if normalized_name:
        name_to_ids[normalized_name].add(author_id)
  return author_ids, unknown_author_count, name_to_ids


def _validation_report_dict(report: Any) -> dict:
  if report is None:
    return {}
  if is_dataclass(report):
    report = asdict(report)
  if not isinstance(report, dict):
    raise TypeError("HAL validation report must be a dict or dataclass.")

  def issue_dict(issue: Any) -> dict:
    if is_dataclass(issue):
      return asdict(issue)
    if isinstance(issue, dict):
      return issue
    raise TypeError("HAL validation issues must be dicts or dataclasses.")

  result = dict(report)
  for key in ("errors", "warnings"):
    result[key] = [issue_dict(issue) for issue in result.get(key, [])]
  return result


def _check_finding_count(report: Any) -> int:
  if not isinstance(report, dict):
    return 0
  if isinstance(report.get("summary"), dict):
    summary_count = report["summary"].get("finding_count")
    if isinstance(summary_count, int):
      return summary_count
  return sum(
      check.get("finding_count", 0)
      for check in report.get("checks", [])
      if isinstance(check, dict) and isinstance(check.get("finding_count", 0), int)
  )


def _relationship_mismatch_count(etl_comparison: Any) -> int:
  if not isinstance(etl_comparison, dict):
    return 0
  return sum(
      len(relation.get(key, []))
      for relation in etl_comparison.get("relationships", {}).values()
      if isinstance(relation, dict)
      for key in ("missing", "unexpected", "duplicates")
  )


def _analyze_raw_docs(docs: list[dict], manifest: dict | None) -> dict:
  record_count = len(docs)
  missingness = {}
  for name, fields in MISSINGNESS_FIELDS.items():
    missing_count = sum(not _field_present(doc, fields) for doc in docs)
    missingness[name] = {
        "missing_count": missing_count,
        "missing_percent": (
            round(missing_count / record_count * 100, 2) if record_count else 0.0
        ),
    }

  hal_ids = [_hal_id(doc) for doc in docs]
  present_hal_ids = [hal_id for hal_id in hal_ids if hal_id is not None]
  duplicate_counts: dict[str, int] = {}
  for hal_id in present_hal_ids:
    duplicate_counts[hal_id] = duplicate_counts.get(hal_id, 0) + 1
  duplicate_ids = {
      hal_id: count
      for hal_id, count in sorted(duplicate_counts.items())
      if count > 1
  }

  author_ids, unknown_author_count, name_to_ids = _author_ids_and_names(docs)
  homonym_groups = [
      {
          "normalized_name": name,
          "author_ids": sorted(ids),
      }
      for name, ids in sorted(name_to_ids.items())
      if len({author_id for author_id in ids if not author_id.startswith("unknown_")}) > 1
  ]

  domain_ids = set()
  organization_ids = set()
  for doc in docs:
    domain_values = (
        _as_list(doc.get("primaryDomain_s"))
        + _as_list(doc.get("domainAllCode_s"))
        + _as_list(doc.get("domain_s"))
        + _as_list(doc.get("level0_domain_s"))
        + _as_list(doc.get("level1_domain_s"))
        + _as_list(doc.get("level2_domain_s"))
    )
    domain_ids.update(_unique_nonblank(domain_values))
    organization_ids.update(_unique_nonblank(_as_list(doc.get("structId_i"))))

  authors_without_hal_id = sum(
      1
      for doc in docs
      for index, name in enumerate(_as_list(doc.get("authFullName_s")))
      if not _is_present_author_hal_id(
          _as_list(doc.get("authIdHal_s"))[index]
          if index < len(_as_list(doc.get("authIdHal_s")))
          else None
      )
  )
  author_array_mismatches = []
  for index, doc in enumerate(docs):
    author_count = len(_as_list(doc.get("authFullName_s")))
    mismatched_fields = {
        field: len(_as_list(doc.get(field)))
        for field in AUTHOR_ID_FIELDS
        if field in doc and len(_as_list(doc.get(field))) != author_count
    }
    if mismatched_fields:
      author_array_mismatches.append({
          "doc_index": index,
          "author_name_count": author_count,
          "field_lengths": mismatched_fields,
      })

  multi_language_abstracts = [
      index
      for index, doc in enumerate(docs)
      if len(_as_list(doc.get("abstract_s"))) > 1
  ]
  unknown_or_missing_hal_ids = [
      index
      for index, hal_id in enumerate(hal_ids)
      if hal_id is None or hal_id.casefold() == "unknown"
  ]

  manifest = manifest or {}
  num_found = manifest.get("numFound")
  fetched_count = manifest.get("fetched_count", record_count)
  if not isinstance(fetched_count, int):
    fetched_count = record_count
  pagination = {
      "num_found": num_found,
      "fetched_count": fetched_count,
      "difference": (
          num_found - fetched_count
          if isinstance(num_found, int)
          else None
      ),
      "complete": (
          fetched_count >= num_found
          if isinstance(num_found, int)
          else None
      ),
  }

  return {
      "records_retrieved": record_count,
      "counts": {
          "projects": len(set(present_hal_ids)),
          "authors": len(author_ids),
          "research_domains": len(domain_ids),
          "organizations": len(organization_ids),
      },
      "missingness": missingness,
      "duplicate_ids": {
          "hal_project_ids": duplicate_ids,
          "duplicate_record_count": sum(count - 1 for count in duplicate_ids.values()),
      },
      "author_identity": {
          "author_id_count": len(author_ids),
          "unknown_author_count": unknown_author_count,
          "unknown_author_share": (
              round(
                  sum(
                      author_id.startswith("unknown_")
                      for author_id in author_ids
                  ) / len(author_ids),
                  4,
              )
              if author_ids
              else 0.0
          ),
          "authors_without_hal_id": authors_without_hal_id,
          "homonym_collision_groups": homonym_groups,
          "homonym_collision_group_count": len(homonym_groups),
      },
      "author_array_alignment": {
          "mismatched_record_count": len(author_array_mismatches),
          "mismatch_rate": (
              round(len(author_array_mismatches) / record_count, 4)
              if record_count
              else 0.0
          ),
          "mismatches": author_array_mismatches,
      },
      "missing_or_unknown_hal_id_record_indexes": unknown_or_missing_hal_ids,
      "multi_language_abstract_record_indexes": multi_language_abstracts,
      "pagination": pagination,
  }


def build_data_quality_report(
    docs: list[dict],
    *,
    manifest: dict | None = None,
    hal_validation: Any = None,
    etl_comparison: dict | None = None,
    hierarchy: dict | None = None,
    integrity: dict | None = None,
    stale_node_test: dict | None = None,
    snapshot_comparison: dict | None = None,
    report_date: date | None = None,
) -> dict:
  """Assemble data-quality metrics from a raw HAL snapshot and optional checks."""
  if not isinstance(docs, list) or any(not isinstance(doc, dict) for doc in docs):
    raise TypeError("docs must be a list of HAL document dictionaries.")

  validation = _validation_report_dict(
      hal_validation or validate_hal_documents(
          docs,
          num_found=(manifest or {}).get("numFound"),
      )
  )
  hierarchy = hierarchy or {}
  integrity = integrity or {}
  etl_comparison = etl_comparison or {}
  stale_node_test = stale_node_test or {"status": "not_run"}
  snapshot_comparison = snapshot_comparison or {"status": "not_run"}

  hierarchy_violation_count = _check_finding_count(hierarchy)
  etl_entity_duplicate_count = sum(
      len(entity.get("duplicate_ids", []))
      for entity in etl_comparison.get("entities", {}).values()
      if isinstance(entity, dict)
  )
  etl_mismatch_count = sum(
      len(entity.get("missing_ids", []))
      + len(entity.get("field_mismatches", []))
      for entity in etl_comparison.get("entities", {}).values()
      if isinstance(entity, dict)
  )
  etl_mismatch_count += _relationship_mismatch_count(etl_comparison)
  integrity_checks = integrity.get("checks", [])
  integrity_findings = [
      finding
      for check in integrity_checks
      if isinstance(check, dict)
      for finding in check.get("findings", [])
  ]
  bare_organization_count = next(
      (
          check.get("finding_count", 0)
          for check in integrity_checks
          if check.get("name") == "bare_organizations"
      ),
      0,
  )

  report = {
      "report_date": (report_date or date.today()).isoformat(),
      "snapshot": {
          "query": (manifest or {}).get("query"),
          "timestamp": (manifest or {}).get("timestamp"),
          "requested_fields": (manifest or {}).get("requested_fields", []),
          "num_found": (manifest or {}).get("numFound"),
          "fetched_count": (manifest or {}).get("fetched_count", len(docs)),
          "sort": (manifest or {}).get("sort"),
      },
      "hal": _analyze_raw_docs(docs, manifest),
      "validation": {
          "is_valid": not validation.get("errors", []),
          "error_count": len(validation.get("errors", [])),
          "warning_count": len(validation.get("warnings", [])),
          "errors": validation.get("errors", []),
          "warnings": validation.get("warnings", []),
      },
      "methodology": {
          "missingness_is_error": False,
          "missingness_note": (
              "Missingness percentages measure observed absence; optional HAL "
              "fields being absent is not automatically an error."
          ),
          "homonym_collision_note": (
              "Homonym groups are a signal: identical normalized full names "
              "with distinct non-placeholder author IDs may be distinct people."
          ),
          "unknown_author_share_denominator": (
              "Unique extracted author IDs, including unknown_ fallback IDs."
          ),
      },
      "etl_comparison": {
          "status": "not_run" if not etl_comparison else "completed",
          "summary": etl_comparison.get("summary", {}),
          "entity_mismatch_count": etl_mismatch_count,
          "duplicate_node_count": etl_entity_duplicate_count,
          "relationship_mismatch_count": _relationship_mismatch_count(
              etl_comparison
          ),
          "entities": etl_comparison.get("entities", {}),
          "relationships": etl_comparison.get("relationships", {}),
          "cause_hypotheses": etl_comparison.get("cause_hypotheses", []),
      },
      "neo4j_integrity": {
          "status": "not_run" if not integrity else "completed",
          "summary": integrity.get("summary", {}),
          "finding_count": sum(
              check.get("finding_count", 0)
              for check in integrity_checks
              if isinstance(check, dict)
          ),
          "bare_organization_count": bare_organization_count,
          "checks": integrity_checks,
          "findings": integrity_findings,
      },
      "hierarchy": {
          "status": "not_run" if not hierarchy else "completed",
          "summary": hierarchy.get("summary", {}),
          "violation_count": hierarchy_violation_count,
          "checks": hierarchy.get("checks", []),
          "taxonomy_policy": hierarchy.get("taxonomy_policy") or TAXONOMY_POLICY,
      },
      "known_caveat_checks": {
          "stale_node_test": stale_node_test,
          "snapshot_comparison": snapshot_comparison,
      },
  }
  report["conclusions"], report["open_risks"] = _summarize_report(report)
  return report


def _summarize_report(report: dict) -> tuple[list[str], list[str]]:
  conclusions = []
  risks = []
  hal = report["hal"]
  validation = report["validation"]
  if validation["error_count"]:
    conclusions.append(
        f"HAL validation found {validation['error_count']} error(s) in "
        f"{validation['error_count'] + validation['warning_count']} reported issue(s)."
    )
  else:
    conclusions.append("HAL validation found no errors in the supplied snapshot.")

  if hal["duplicate_ids"]["duplicate_record_count"]:
    conclusions.append(
        f"HAL input contains {hal['duplicate_ids']['duplicate_record_count']} "
        "duplicate project record(s)."
    )
  unknown_share = hal["author_identity"]["unknown_author_share"]
  if unknown_share:
    conclusions.append(
        f"{unknown_share:.1%} of extracted author identities use the unknown_ fallback."
    )
  if report["etl_comparison"]["status"] == "completed":
    conclusions.append(
        f"ETL comparison found {report['etl_comparison']['entity_mismatch_count']} "
        "entity/property/relationship mismatch(es)."
    )
  if report["hierarchy"]["status"] == "completed":
    conclusions.append(
        f"Hierarchy validation found {report['hierarchy']['violation_count']} violation(s)."
    )
  if report["neo4j_integrity"]["status"] == "completed":
    conclusions.append(
        f"Neo4j integrity checks found {report['neo4j_integrity']['finding_count']} finding(s)."
    )
  pagination = hal["pagination"]
  if pagination["complete"] is False:
    risks.append(
        f"Snapshot fetched {pagination['fetched_count']} of "
        f"{pagination['num_found']} records reported by HAL."
    )
  if hal["author_array_alignment"]["mismatched_record_count"]:
    risks.append(
        f"Author arrays differ in length on "
        f"{hal['author_array_alignment']['mismatched_record_count']} record(s); "
        "author identity fields may be misaligned."
    )
  if hal["missing_or_unknown_hal_id_record_indexes"]:
    risks.append(
        f"{len(hal['missing_or_unknown_hal_id_record_indexes'])} record(s) lack "
        "a usable HAL identifier or use 'Unknown'."
    )
  if report["neo4j_integrity"]["bare_organization_count"]:
    risks.append(
        f"{report['neo4j_integrity']['bare_organization_count']} Organization "
        "node(s) are missing a name or type."
    )
  for section, label in (
      ("etl_comparison", "ETL-to-Neo4j comparison"),
      ("neo4j_integrity", "Neo4j integrity checks"),
      ("hierarchy", "ResearchDomain hierarchy validation"),
  ):
    if report[section]["status"] == "not_run":
      risks.append(f"{label} was not run for this report.")
  if report["known_caveat_checks"]["stale_node_test"].get("status") == "not_run":
    risks.append(
        "Stale-node behavior was not tested; existing properties may not refresh "
        "because persistence uses ON CREATE SET."
    )
  if report["known_caveat_checks"]["snapshot_comparison"].get("status") == "not_run":
    risks.append("Snapshot-to-snapshot instability was not measured.")

  if not conclusions:
    conclusions.append("No quality conclusions could be derived from the supplied inputs.")
  return conclusions, risks


def render_markdown_report(report: dict) -> str:
  """Render a concise Markdown summary with key metrics and open risks."""
  hal = report["hal"]
  lines = [
      f"# Data quality report — {report['report_date']}",
      "",
      "## Snapshot",
      "",
      f"- Query: `{report['snapshot'].get('query') or 'not recorded'}`",
      f"- Retrieved: {hal['records_retrieved']} record(s)",
      f"- HAL numFound: {hal['pagination'].get('num_found')}",
      f"- Fetched count: {hal['pagination']['fetched_count']}",
      f"- Projects/authors/domains: {hal['counts']['projects']} / "
      f"{hal['counts']['authors']} / {hal['counts']['research_domains']}",
      "",
      "## Missingness",
      "",
      "Missingness is measured for quality analysis; absent optional HAL values "
      "are not automatically validation errors.",
      "",
      "| Field | Missing | Percent |",
      "|---|---:|---:|",
  ]
  for field, metric in hal["missingness"].items():
    lines.append(
        f"| {field} | {metric['missing_count']} | "
        f"{metric['missing_percent']:.2f}% |"
    )
  lines.extend([
      "",
      "## Validation results",
      "",
      f"- HAL errors/warnings: {report['validation']['error_count']} / "
      f"{report['validation']['warning_count']}",
      f"- Duplicate HAL project records: "
      f"{hal['duplicate_ids']['duplicate_record_count']}",
      f"- Author-array mismatch records: "
      f"{hal['author_array_alignment']['mismatched_record_count']} "
      f"({hal['author_array_alignment']['mismatch_rate']:.2%})",
      f"- Unknown author share: "
      f"{hal['author_identity']['unknown_author_share']:.2%}",
      f"- Homonym collision groups: "
      f"{hal['author_identity']['homonym_collision_group_count']}",
      f"- Multi-language abstracts: "
      f"{len(hal['multi_language_abstract_record_indexes'])}",
      f"- ETL mismatches: {report['etl_comparison']['entity_mismatch_count']} "
      f"({report['etl_comparison']['status']})",
      f"- Neo4j integrity findings: "
      f"{report['neo4j_integrity']['finding_count']} "
      f"({report['neo4j_integrity']['status']})",
      f"- Hierarchy violations: {report['hierarchy']['violation_count']} "
      f"({report['hierarchy']['status']})",
      "",
      "## Conclusions",
      "",
  ])
  lines.extend(f"- {conclusion}" for conclusion in report["conclusions"])
  lines.extend(["", "## Open risks", ""])
  if report["open_risks"]:
    lines.extend(f"- {risk}" for risk in report["open_risks"])
  else:
    lines.append("- None identified from the supplied checks.")
  lines.extend([
      "",
      "## Taxonomy policy",
      "",
      report["hierarchy"]["taxonomy_policy"],
      "",
      "## Detailed metrics",
      "",
      "See the companion JSON report for issue details, mismatches, hierarchy "
      "violations, and optional check results.",
      "",
  ])
  return "\n".join(lines)


def write_data_quality_report(
    report: dict,
    output_dir: str | Path = "reports",
) -> dict[str, Path]:
  """Write date-stamped JSON and Markdown reports and return their paths."""
  output_dir = Path(output_dir)
  output_dir.mkdir(parents=True, exist_ok=True)
  report_date = report["report_date"]
  date.fromisoformat(report_date)
  json_path = output_dir / f"data_quality_{report_date}.json"
  markdown_path = output_dir / f"data_quality_{report_date}.md"
  json_path.write_text(
      json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
      encoding="utf-8",
  )
  markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
  return {"json": json_path, "markdown": markdown_path}


def _load_json(path: Path) -> Any:
  with path.open(encoding="utf-8") as source:
    return json.load(source)


def main() -> None:
  parser = argparse.ArgumentParser(
      description="Build Markdown and JSON data-quality reports from a HAL snapshot."
  )
  parser.add_argument("snapshot", type=Path, help="HAL records JSONL file.")
  parser.add_argument("--manifest", type=Path, help="Optional snapshot manifest JSON.")
  parser.add_argument("--etl-comparison", type=Path, help="Optional ETL comparison JSON.")
  parser.add_argument("--hierarchy", type=Path, help="Optional hierarchy check JSON.")
  parser.add_argument("--integrity", type=Path, help="Optional Neo4j integrity JSON.")
  parser.add_argument("--stale-node-test", type=Path, help="Optional stale-node test JSON.")
  parser.add_argument("--snapshot-comparison", type=Path, help="Optional snapshot comparison JSON.")
  parser.add_argument("--output-dir", type=Path, default=Path("reports"))
  parser.add_argument("--date", type=date.fromisoformat, help="Report date (YYYY-MM-DD).")
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

  def optional_json(path: Path | None) -> Any:
    return _load_json(path) if path else None

  manifest = optional_json(args.manifest)
  report = build_data_quality_report(
      docs,
      manifest=manifest,
      etl_comparison=optional_json(args.etl_comparison),
      hierarchy=optional_json(args.hierarchy),
      integrity=optional_json(args.integrity),
      stale_node_test=optional_json(args.stale_node_test),
      snapshot_comparison=optional_json(args.snapshot_comparison),
      report_date=args.date,
  )
  paths = write_data_quality_report(report, args.output_dir)
  print("\n".join(report["conclusions"]))
  print("\nOpen risks:")
  if report["open_risks"]:
    print("\n".join(f"- {risk}" for risk in report["open_risks"]))
  else:
    print("- None identified from the supplied checks.")
  print(f"\nJSON report: {paths['json']}")
  print(f"Markdown report: {paths['markdown']}")


if __name__ == "__main__":
  main()
