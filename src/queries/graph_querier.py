import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()


class GraphQuerier:

  def __init__(self):
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    self.driver = GraphDatabase.driver(uri, auth=(user, password))

  def close(self):
    self.driver.close()

  def get_author_publications(self, author_name):
    """Retorna todas as publicações de um autor específico."""
    query = """
        MATCH (a:Author {name: $name})-[:WROTE]->(p:Publication)
        RETURN p.halId AS hal_id, p.title AS title, p.year AS year
        """
    with self.driver.session() as session:
      result = session.run(query, name=author_name)
      return [dict(record) for record in result]

  def get_collaborators_network(self, publication_title_fragment):
    """Encontra coautores que trabalharam em publicações com um termo no título."""
    query = """
        MATCH (p:Publication)<-[:WROTE]-(a:Author)
        WHERE p.title CONTAINS $fragment
        RETURN p.title AS publication, collect(a.name) AS co_authors
        """
    with self.driver.session() as session:
      result = session.run(query, fragment=publication_title_fragment)
      return [dict(record) for record in result]