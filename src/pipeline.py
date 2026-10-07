import argparse
import json
from pathlib import Path

from connectors.hal_snapshot import create_hal_snapshot
from config import load_neo4j_settings
from database.neo4j_manager import Neo4jManager
from processing.transformer import (
    extract_authors_from_hal_record,
    extract_conference_from_hal_record,
    extract_organizations_from_hal_record,
    extract_project_from_hal_record,
    extract_research_domains_from_hal_record,
)
from logger import get_logger
from validation.hal_validator import validate_hal_documents

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


def _load_complete_snapshot(snapshot_path: str | Path) -> list[dict]:
  snapshot_path = Path(snapshot_path)
  manifest_path = snapshot_path.parent / "manifest.json"
  if not manifest_path.is_file():
    raise ValueError(
        f"Complete HAL snapshot requires its manifest: {manifest_path}"
    )

  with manifest_path.open(encoding="utf-8") as manifest_file:
    manifest = json.load(manifest_file)
  if not isinstance(manifest, dict):
    raise ValueError("HAL snapshot manifest must be a JSON object.")
  if manifest.get("query") != "*:*":
    raise ValueError("Full import requires a snapshot for the '*:*' query.")

  num_found = manifest.get("numFound")
  fetched_count = manifest.get("fetched_count")
  if not isinstance(num_found, int) or not isinstance(fetched_count, int):
    raise ValueError(
        "Complete HAL snapshot manifest must contain integer numFound "
        "and fetched_count values."
    )
  if fetched_count != num_found:
    raise ValueError(
        "HAL snapshot is incomplete: manifest reports "
        f"{fetched_count} fetched records for {num_found} matching records."
    )
  if fetched_count == 0:
    raise ValueError("Full import cannot use an empty HAL snapshot.")

  docs = []
  with snapshot_path.open(encoding="utf-8") as snapshot_file:
    for line_number, line in enumerate(snapshot_file, start=1):
      if not line.strip():
        continue
      doc = json.loads(line)
      if not isinstance(doc, dict):
        raise ValueError(
            f"Snapshot record on line {line_number} must be a JSON object."
        )
      docs.append(doc)

  if len(docs) != fetched_count:
    raise ValueError(
        "HAL snapshot record count does not match its manifest: "
        f"found {len(docs)}, expected {fetched_count}."
    )
  validation = validate_hal_documents(docs, num_found=num_found)
  if not validation.is_valid:
    error_codes = ", ".join(issue.code for issue in validation.errors[:5])
    raise ValueError(
        f"Stage A HAL validation failed for full import: {error_codes}"
    )
  if validation.warnings:
    warning_codes = sorted({issue.code for issue in validation.warnings})
    logger.warning(
        "HAL validation found %s warning(s): %s",
        len(validation.warnings),
        ", ".join(warning_codes),
    )
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
    full_import: bool = False,
    identity_migration_reviewed: bool = False,
) -> None:
  if full_import:
    if limit is not None:
      raise ValueError("--limit cannot be used with --full-import.")
    settings = load_neo4j_settings(database=database)
    database = settings.database
    if not database or not database.strip():
      raise ValueError(
          "--full-import requires a database target. Pass --database or set "
          "NEO4J_DATABASE in the environment or .env file."
      )
    if not identity_migration_reviewed:
      raise ValueError(
          "--full-import requires --identity-migration-reviewed. "
          "Review the Stage A D2 identity migration plan before importing "
          "into a database containing previously ingested records."
      )
    if snapshot_path is None:
      snapshot_result = create_hal_snapshot(query="*:*")
      snapshot_path = snapshot_result["jsonl_path"]
    docs = _load_complete_snapshot(snapshot_path)
  else:
    if snapshot_path is None:
      if limit is not None or database is not None:
        raise ValueError("--limit and --database require --snapshot.")
      raise ValueError(
          "Use --snapshot with an explicit dev --limit and --database, or "
          "use --full-import with a complete '*:*' snapshot and target database."
      )
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
      help="Explicit Neo4j database target (required for all imports).",
  )
  parser.add_argument(
      "--full-import",
      action="store_true",
      help=(
          "Fetch or read a complete Stage A '*:*' snapshot, validate it, "
          "then import it. Requires --database."
      ),
  )
  parser.add_argument(
      "--identity-migration-reviewed",
      action="store_true",
      help=(
          "Confirm that the Stage A D2 author-identity migration/rebuild plan "
          "has been reviewed before a full import."
      ),
  )
  args = parser.parse_args()
  run_pipeline(
      snapshot_path=args.snapshot,
      limit=args.limit,
      database=args.database,
      full_import=args.full_import,
      identity_migration_reviewed=args.identity_migration_reviewed,
  )
