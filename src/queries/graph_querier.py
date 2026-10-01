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

  def get_author_projects(self, author_name):
    """Returns all projects by a specific author."""
    query = """
        MATCH (a:Author {fullName: $name})-[:WROTE]->(p:Project)
        RETURN p.halId AS hal_id, p.title AS title, p.publicationYear AS year
        """
    with self.driver.session() as session:
      result = session.run(query, name=author_name)
      return [dict(record) for record in result]

  def get_author_publications(self, author_name):
    """Backward-compatible alias for older callers."""
    return self.get_author_projects(author_name)

  def get_collaborators_network(self, project_title_fragment):
    """Find collaborators who have worked on projects with a term in the title."""
    query = """
        MATCH (p:Project)<-[:WROTE]-(a:Author)
        WHERE p.title CONTAINS $fragment
        RETURN p.title AS publication, collect(a.fullName) AS co_authors
        """
    with self.driver.session() as session:
      result = session.run(query, fragment=project_title_fragment)
      return [dict(record) for record in result]
