import argparse
import csv
import json
from pathlib import Path

from processing.transformer import (
    extract_authors_from_hal_record,
    extract_conference_from_hal_record,
    extract_organizations_from_hal_record,
    extract_project_from_hal_record,
    extract_research_domains_from_hal_record,
)
from logger import get_logger

logger = get_logger(__name__)


CSV_SCHEMAS = {
    "projects": [
        "halId",
        "title",
        "abstract",
        "keywords",
        "documentType",
        "language",
        "publicationDate",
        "publicationYear",
        "doi",
        "uri",
    ],
    "authors": [
        "halId",
        "personId",
        "firstName",
        "lastName",
        "fullName",
        "emailDomain",
        "orcidId",
        "googleScholarId",
        "researcherId",
        "idrefId",
    ],
    "conferences": [
        "conferenceId",
        "title",
        "startDate",
        "endDate",
        "city",
        "country",
    ],
    "organizations": [
        "halId",
        "name",
        "acronym",
        "type",
        "country",
        "address",
        "code",
        "status",
        "ror",
        "idref",
        "isni",
        "rnsr",
        "wikidata",
    ],
    "research_domains": [
        "id",
        "name",
        "nameFr",
        "source",
    ],
    "project_authors": [
        "projectHalId",
        "authorHalId",
    ],
    "project_conferences": [
        "projectHalId",
        "conferenceId",
    ],
    "project_organizations": [
        "projectHalId",
        "organizationHalId",
    ],
    "organization_relationships": [
        "sourceId",
        "targetId",
        "type",
    ],
    "project_research_domains": [
        "projectHalId",
        "domainId",
        "primary",
    ],
    "research_domain_hierarchy": [
        "childId",
        "parentId",
    ],
}


def _new_tables():
  return {name: {} for name in CSV_SCHEMAS}


def _put_unique(table: dict, key, row: dict):
  if key not in table:
    table[key] = row


def _serialize_value(value):
  if value is None:
    return ""
  if isinstance(value, (list, dict)):
    return json.dumps(value, ensure_ascii=False)
  return value


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
  with path.open("w", newline="", encoding="utf-8") as csv_file:
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
      writer.writerow({
          field: _serialize_value(row.get(field))
          for field in fieldnames
      })


def build_csv_tables_from_hal_docs(docs: list[dict]) -> dict:
  """Runs the metadata transformers and organizes entities/relations for CSV."""
  tables = _new_tables()

  for doc in docs:
    project = extract_project_from_hal_record(doc).to_neo4j_dict()
    project_id = project["halId"]
    _put_unique(tables["projects"], project_id, project)

    for author in extract_authors_from_hal_record(doc):
      author_data = author.to_neo4j_dict()
      author_id = author_data["halId"]
      _put_unique(tables["authors"], author_id, author_data)
      _put_unique(
          tables["project_authors"],
          (project_id, author_id),
          {
              "projectHalId": project_id,
              "authorHalId": author_id,
          },
      )

    conference = extract_conference_from_hal_record(doc)
    if conference:
      conference_data = conference.to_neo4j_dict()
      conference_id = conference_data["conferenceId"]
      _put_unique(tables["conferences"], conference_id, conference_data)
      _put_unique(
          tables["project_conferences"],
          (project_id, conference_id),
          {
              "projectHalId": project_id,
              "conferenceId": conference_id,
          },
      )

    organization_data = extract_organizations_from_hal_record(doc).to_neo4j_dict()
    for organization in organization_data["organizations"]:
      organization_id = organization["halId"]
      _put_unique(tables["organizations"], organization_id, organization)
      _put_unique(
          tables["project_organizations"],
          (project_id, organization_id),
          {
              "projectHalId": project_id,
              "organizationHalId": organization_id,
          },
      )

    for relationship in organization_data["organization_relationships"]:
      _put_unique(
          tables["organization_relationships"],
          (
              relationship["sourceId"],
              relationship["targetId"],
              relationship["type"],
          ),
          relationship,
      )

    domain_data = extract_research_domains_from_hal_record(doc).to_neo4j_dict()
    for domain in domain_data["research_domains"]:
      _put_unique(tables["research_domains"], domain["id"], domain)

    for relation in domain_data["project_domain_relations"]:
      row = {
          "projectHalId": project_id,
          "domainId": relation["domainId"],
          "primary": relation["primary"],
      }
      _put_unique(
          tables["project_research_domains"],
          (project_id, relation["domainId"]),
          row,
      )

    for relation in domain_data["domain_hierarchy_relations"]:
      _put_unique(
          tables["research_domain_hierarchy"],
          (relation["childId"], relation["parentId"]),
          relation,
      )

  return tables


def write_csv_tables(tables: dict, output_dir: Path) -> dict:
  output_dir.mkdir(parents=True, exist_ok=True)
  written_files = {}

  for table_name, fieldnames in CSV_SCHEMAS.items():
    output_path = output_dir / f"{table_name}.csv"
    rows = list(tables[table_name].values())
    _write_csv(output_path, rows, fieldnames)
    written_files[table_name] = output_path

  return written_files


def export_hal_query_to_csv(query=None, max_rows=1, output_dir=None):
  from connectors.hal_client import HalClient

  client = HalClient()
  docs = client.fetch_publications(query=query, max_rows=max_rows)
  tables = build_csv_tables_from_hal_docs(docs)
  output_dir = Path(output_dir or "exports/pipeline_csv_test")
  return docs, write_csv_tables(tables, output_dir)


def _build_query(args):
  if args.hal_id:
    query = f"halId_s:{args.hal_id}"
  elif args.title:
    query = f'title_t:"{args.title}"'
  else:
    query = args.query

  if args.doc_type:
    doc_type_filter = f"docType_s:{args.doc_type}"
    return f"({query}) AND {doc_type_filter}" if query else doc_type_filter

  return query


def main():
  parser = argparse.ArgumentParser(
      description="Runs the HAL metadata pipeline and writes CSV files."
  )
  parser.add_argument("--query", default=None, help="Raw HAL query.")
  parser.add_argument("--hal-id", default=None, help="HAL id to fetch.")
  parser.add_argument("--title", default=None, help="Exact title text to search.")
  parser.add_argument(
      "--doc-type",
      default=None,
      help="HAL document type filter, for example COMM or ART.",
  )
  parser.add_argument("--rows", type=int, default=1, help="Maximum HAL records.")
  parser.add_argument(
      "--output",
      default="exports/pipeline_csv_test",
      help="Directory where CSV files will be written.",
  )
  args = parser.parse_args()

  docs, files = export_hal_query_to_csv(
      query=_build_query(args),
      max_rows=args.rows,
      output_dir=args.output,
  )

  logger.info(f"Fetched {len(docs)} HAL publication(s).")
  for table_name, path in files.items():
    logger.info(f"{table_name}: {path}")


if __name__ == "__main__":
  main()
