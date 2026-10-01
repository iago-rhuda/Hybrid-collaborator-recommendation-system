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
        "CREATE CONSTRAINT project_hal_id IF NOT EXISTS FOR (p:Project) REQUIRE p.halId IS UNIQUE",
        "CREATE CONSTRAINT author_hal_id IF NOT EXISTS FOR (a:Author) REQUIRE a.halId IS UNIQUE",
        "CREATE CONSTRAINT conference_id IF NOT EXISTS FOR (c:Conference) REQUIRE c.conferenceId IS UNIQUE",
        "CREATE CONSTRAINT research_domain_id IF NOT EXISTS FOR (d:ResearchDomain) REQUIRE d.id IS UNIQUE",
        "CREATE CONSTRAINT organization_hal_id IF NOT EXISTS FOR (o:Organization) REQUIRE o.halId IS UNIQUE",
    ]
    with self.driver.session() as session:
      for q in queries:
        session.run(q)
    print(
        "[OK] Uniqueness constraints successfully configured in Neo4j (no duplicates)."
    )

  def save_project_data(
      self,
      project,
      authors,
      labs=None,
      conference=None,
      research_domains=None,
      project_domain_relations=None,
      domain_hierarchy_relations=None,
      organizations=None,
      organization_relationships=None,
  ):
    """It saves the project and related graph nodes."""
    labs = labs or []
    research_domains = research_domains or []
    project_domain_relations = project_domain_relations or []
    domain_hierarchy_relations = domain_hierarchy_relations or []
    organizations = organizations or []
    organization_relationships = organization_relationships or []

    query = """
        MERGE (p:Project {halId: $project_hal_id})
        ON CREATE SET p += $project

        FOREACH (auth IN $authors |
            MERGE (a:Author {halId: auth.halId})
            ON CREATE SET
                a.personId = auth.personId,
                a.firstName = auth.firstName,
                a.lastName = auth.lastName,
                a.fullName = auth.fullName,
                a.emailDomain = auth.emailDomain,
                a.orcidId = auth.orcidId,
                a.googleScholarId = auth.googleScholarId,
                a.researcherId = auth.researcherId,
                a.idrefId = auth.idrefId
            MERGE (a)-[:WROTE]->(p)
        )

        FOREACH (conf IN CASE WHEN $conference IS NULL THEN [] ELSE [$conference] END |
            MERGE (c:Conference {conferenceId: conf.conferenceId})
            ON CREATE SET
                c.title = conf.title,
                c.startDate = conf.startDate,
                c.endDate = conf.endDate,
                c.city = conf.city,
                c.country = conf.country
            MERGE (p)-[:PRESENTED_AT]->(c)
        )

        FOREACH (domain IN $research_domains |
            MERGE (d:ResearchDomain {id: domain.id})
            ON CREATE SET d += domain
        )

        FOREACH (domain_relation IN $project_domain_relations |
            MERGE (d:ResearchDomain {id: domain_relation.domainId})
            MERGE (p)-[r:HAS_RESEARCH_DOMAIN]->(d)
            SET r.primary = domain_relation.primary
        )

        FOREACH (hierarchy_relation IN $domain_hierarchy_relations |
            MERGE (child:ResearchDomain {id: hierarchy_relation.childId})
            MERGE (parent:ResearchDomain {id: hierarchy_relation.parentId})
            MERGE (child)-[:SUBDOMAIN_OF]->(parent)
        )

        FOREACH (organization IN $organizations |
            MERGE (o:Organization {halId: organization.halId})
            ON CREATE SET o += organization
            MERGE (p)-[:HAS_ORGANIZATION]->(o)
        )

        FOREACH (organization_relation IN $organization_relationships |
            MERGE (source:Organization {halId: organization_relation.sourceId})
            MERGE (target:Organization {halId: organization_relation.targetId})
            MERGE (source)-[:PART_OF]->(target)
        )
        """
    with self.driver.session() as session:
      session.run(
          query,
          project_hal_id=project["halId"],
          project=project,
          authors=authors,
          conference=conference,
          research_domains=research_domains,
          project_domain_relations=project_domain_relations,
          domain_hierarchy_relations=domain_hierarchy_relations,
          organizations=organizations,
          organization_relationships=organization_relationships,
      )

  def save_publication_data(self, doc_data, authors, labs, conference):
    """Backward-compatible wrapper for older pipeline calls."""
    project = {
        "halId": doc_data["hal_id"],
        "title": doc_data["title"],
        "abstract": doc_data["abstract"],
        "keywords": [],
        "documentType": doc_data["doc_type"],
        "language": [],
        "publicationDate": "",
        "publicationYear": doc_data["year"],
        "doi": "",
        "uri": "",
    }
    self.save_project_data(project, authors, labs, conference)
