import argparse
import json
from pathlib import Path

from connectors.hal_client import HalClient
from database.neo4j_manager import Neo4jManager
from processing.transformer import (
    extract_authors_from_hal_record,
    extract_conference_from_hal_record,
    extract_organizations_from_hal_record,
    extract_project_from_hal_record,
    extract_research_domains_from_hal_record,
)
from logger import get_logger

logger = get_logger(__name__)

MAX_DEV_SUBSET_SIZE = 2000


def _load_snapshot_docs(snapshot_path: str | Path, limit: int) -> list[dict]:
  if limit < 1 or limit > MAX_DEV_SUBSET_SIZE:
    raise ValueError(
        f"Snapshot ingestion limit must be between 1 and "
        f"{MAX_DEV_SUBSET_SIZE}."
    )

  docs = []
  with Path(snapshot_path).open(encoding="utf-8") as snapshot_file:
    for line_number, line in enumerate(snapshot_file, start=1):
      if len(docs) >= limit:
        break
      if not line.strip():
        continue
      doc = json.loads(line)
      if not isinstance(doc, dict):
        raise ValueError(
            f"Snapshot record on line {line_number} must be a JSON object."
        )
      docs.append(doc)
  if not docs:
    raise ValueError(f"Snapshot contains no records: {snapshot_path}")
  return docs


def _ingest_docs(docs: list[dict], db: Neo4jManager) -> None:
  db.setup_constraints()  # Ensures that duplicate restrictions are active.
  logger.info(f"Processing and inserting {len(docs)} documents into Neo4j...")

  for doc in docs:
    project = extract_project_from_hal_record(doc)
    project_data = project.to_neo4j_dict()
    authors = extract_authors_from_hal_record(doc)
    authors_data = [author.to_neo4j_dict() for author in authors]
    conference = extract_conference_from_hal_record(doc)
    conference_data = conference.to_neo4j_dict() if conference else None
    domain_data = extract_research_domains_from_hal_record(doc).to_neo4j_dict()
    organization_data = extract_organizations_from_hal_record(doc).to_neo4j_dict()

    # Saves to Neo4j (MERGE automatically avoids duplicates)
    db.save_project_data(
        project=project_data,
        authors=authors_data,
        conference=conference_data,
        research_domains=domain_data["research_domains"],
        project_domain_relations=domain_data["project_domain_relations"],
        domain_hierarchy_relations=domain_data["domain_hierarchy_relations"],
        organizations=organization_data["organizations"],
        organization_relationships=organization_data[
            "organization_relationships"
        ],
    )


def run_pipeline(
    snapshot_path: str | Path | None = None,
    limit: int | None = None,
    database: str | None = None,
    db_manager: Neo4jManager | None = None,
) -> None:
  if snapshot_path is None:
    if limit is not None or database is not None:
      raise ValueError("--limit and --database require --snapshot.")
    docs = HalClient().fetch_all_publications()
  else:
    if limit is None:
      raise ValueError("--snapshot requires an explicit --limit.")
    if not database or not database.strip():
      raise ValueError(
          "--snapshot requires an explicit isolated dev --database."
      )
    docs = _load_snapshot_docs(snapshot_path, limit)

  db = db_manager or Neo4jManager(database=database)
  try:
    _ingest_docs(docs, db)
  finally:
    if db_manager is None:
      db.close()
  logger.info("Pipeline complete! The graph in Neo4j has been populated successfully.")


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
      description="Ingest HAL publications into Neo4j."
  )
  parser.add_argument(
      "--snapshot",
      type=Path,
      help="Read source records from a JSONL HAL snapshot instead of HAL.",
  )
  parser.add_argument(
      "--limit",
      type=int,
      help=(
        "Maximum snapshot records to ingest (required with --snapshot; "
        f"maximum {MAX_DEV_SUBSET_SIZE})."
      ),
  )
  parser.add_argument(
      "--database",
      help="Isolated Neo4j dev database name (required with --snapshot).",
  )
  args = parser.parse_args()
  run_pipeline(
      snapshot_path=args.snapshot,
      limit=args.limit,
      database=args.database,
  )
