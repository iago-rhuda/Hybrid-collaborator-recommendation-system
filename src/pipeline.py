from connectors.hal_client import HalClient
from database.neo4j_manager import Neo4jManager


def run_pipeline():
  db = Neo4jManager()
  db.setup_constraints()  # Ensures that duplicate restrictions are active.

  client = HalClient()
  docs = client.fetch_data_science_publications()

  print(f"\nProcessing and inserting {len(docs)} documents into Neo4j...")

  for doc in docs:
    hal_id = doc.get("halId_s", doc.get("docid", "Unknown"))
    title = doc.get("title_s", ["Untitled"])[0]
    year = doc.get("publicationDateY_i", doc.get("producedDate_s", 0))
    doc_type = doc.get("docType_s", "Unknown")
    abstract = doc.get("abstract_s", [""])[0]

    # Lists extractions
    auth_names = doc.get("authFullName_s", [])
    auth_ids_hal = doc.get("authIdHal_s", [])
    auth_ids_person = doc.get("authIdPerson_i", [])
    labs = doc.get("labStructName_s", [])
    if not labs:
      labs = doc.get("structName_s", [])

    # Formatting authors for Cypher
    authors_list = []
    for i, name in enumerate(auth_names):
      h_id = (
          str(auth_ids_hal[i])
          if i < len(auth_ids_hal) and auth_ids_hal[i]
          else f"unknown_{name}"
      )
      p_id = (
          str(auth_ids_person[i]) if i < len(auth_ids_person) else "unknown"
      )
      authors_list.append(
          {"name": name, "auth_id_hal": h_id, "person_id": p_id}
      )

    doc_data = {
        "hal_id": hal_id,
        "title": title,
        "year": int(year) if str(year).isdigit() else 0,
        "doc_type": doc_type,
        "abstract": abstract,
    }

    # Saves to Neo4j (MERGE automatically avoids duplicates)
    db.save_publication_data(doc_data, authors_list, labs)

  db.close()
  print("\n[SUCCESS] Pipeline complete! The graph in Neo4j has been populated.")


if __name__ == "__main__":
  run_pipeline()