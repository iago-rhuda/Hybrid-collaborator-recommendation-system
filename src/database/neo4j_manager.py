import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


class Neo4jManager:

  def __init__(self):
    self.driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

  def close(self):
    self.driver.close()

  def setup_constraints(self):
    """It creates uniqueness constraints to prevent duplicates in the graph."""
    queries = [
        "CREATE CONSTRAINT publication_hal_id IF NOT EXISTS FOR (p:Publication) REQUIRE p.halId IS UNIQUE",
        "CREATE CONSTRAINT author_hal_id IF NOT EXISTS FOR (a:Author) REQUIRE a.authIdHal IS UNIQUE",
        "CREATE CONSTRAINT lab_name IF NOT EXISTS FOR (l:Laboratory) REQUIRE l.name IS UNIQUE",
    ]
    with self.driver.session() as session:
      for q in queries:
        session.run(q)
    print(
        "[OK] Uniqueness constraints successfully configured in Neo4j (no duplicates)."
    )

  def save_publication_data(self, doc_data, authors, labs):
    """It saves the publication, the authors, the laboratory, and creates the typed edges."""
    query = """
        MERGE (p:Publication {halId: $hal_id})
        ON CREATE SET p.title = $title, p.year = $year, p.docType = $doc_type, p.abstract = $abstract

        FOREACH (lab_name IN $labs |
            MERGE (l:Laboratory {name: lab_name})
            MERGE (p)-[:AT_LOCATION]->(l)
        )

        FOREACH (auth IN $authors |
            MERGE (a:Author {authIdHal: auth.auth_id_hal})
            ON CREATE SET a.name = auth.name, a.personId = auth.person_id
            MERGE (a)-[:WROTE]->(p)
        )
        """
    with self.driver.session() as session:
      session.run(
          query,
          hal_id=doc_data["hal_id"],
          title=doc_data["title"],
          year=doc_data["year"],
          doc_type=doc_data["doc_type"],
          abstract=doc_data["abstract"],
          labs=labs,
          authors=authors,
      )