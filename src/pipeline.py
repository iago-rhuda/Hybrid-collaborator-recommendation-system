from connectors.hal_client import HalClient
from database.neo4j_manager import Neo4jManager
from processing.transformer import (
    extract_authors_from_hal_record,
    extract_conference_from_hal_record,
    extract_organizations_from_hal_record,
    extract_project_from_hal_record,
    extract_research_domains_from_hal_record,
)


def run_pipeline():
  db = Neo4jManager()
  db.setup_constraints()  # Ensures that duplicate restrictions are active.

  client = HalClient()
  docs = client.fetch_data_science_publications()

  print(f"\nProcessing and inserting {len(docs)} documents into Neo4j...")

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

  db.close()
  print("\n[SUCCESS] Pipeline complete! The graph in Neo4j has been populated.")


if __name__ == "__main__":
  run_pipeline()
