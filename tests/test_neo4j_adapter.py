import unittest

from graph.adapter import DomainView, PersonView, ProjectView
from graph.neo4j_adapter import Neo4jAdapter


class FakeResult:
  def __init__(self, records):
    self.records = records

  def single(self):
    return self.records[0] if self.records else None

  def __iter__(self):
    return iter(self.records)


class FakeSession:
  def __init__(self, driver, database):
    self.driver = driver
    self.database = database

  def __enter__(self):
    self.driver.databases.append(self.database)
    return self

  def __exit__(self, exc_type, exc_value, traceback):
    return False

  def run(self, query, **parameters):
    self.driver.calls.append((query, parameters))
    for marker, records in self.driver.responses:
      if marker in query:
        return FakeResult(records)
    return FakeResult([])


class FakeDriver:
  def __init__(self, responses):
    self.responses = responses
    self.calls = []
    self.databases = []
    self.closed = False

  def session(self, database=None):
    return FakeSession(self, database)

  def close(self):
    self.closed = True


class Neo4jAdapterTest(unittest.TestCase):

  def test_reads_project_properties_using_parameterized_project_id(self):
    driver = FakeDriver([
        ("MATCH (p:Project {halId:", [{
            "project_id": "hal-123",
            "title": "A publication",
            "abstract": "An abstract",
            "keywords": ["systems", "graphs"],
            "year": 2024,
            "doc_type": "ART",
        }]),
    ])
    adapter = Neo4jAdapter(driver=driver, database="dev")

    project = adapter.get_project("hal-123")

    self.assertEqual(
        project,
        ProjectView(
            project_id="hal-123",
            title="A publication",
            abstract="An abstract",
            keywords=["systems", "graphs"],
            year=2024,
            doc_type="ART",
        ),
    )
    query, parameters = driver.calls[0]
    self.assertIn("$project_id", query)
    self.assertNotIn("hal-123", query)
    self.assertEqual(parameters, {"project_id": "hal-123"})
    self.assertEqual(driver.databases, ["dev"])

  def test_returns_none_for_missing_project_and_normalizes_missing_values(self):
    driver = FakeDriver([
        ("MATCH (p:Project {halId:", []),
    ])
    adapter = Neo4jAdapter(driver=driver)

    self.assertIsNone(adapter.get_project("not-found"))

    driver.responses = [("MATCH (p:Project {halId:", [{
        "project_id": "hal-empty",
        "title": None,
        "abstract": None,
        "keywords": None,
        "year": None,
        "doc_type": None,
    }])]
    project = adapter.get_project("hal-empty")
    self.assertEqual(project.title, "")
    self.assertEqual(project.abstract, "")
    self.assertEqual(project.keywords, [])
    self.assertIsNone(project.year)
    self.assertEqual(project.doc_type, "")

  def test_iter_projects_is_ordered_and_parameterizes_pagination(self):
    driver = FakeDriver([
        ("MATCH (p:Project)", [{
            "project_id": "hal-2",
            "title": "Second",
            "abstract": "",
            "keywords": "single-keyword",
            "year": "2023",
            "doc_type": "ART",
        }]),
    ])
    adapter = Neo4jAdapter(driver=driver)

    projects = adapter.iter_projects(limit=5, offset=10)

    self.assertEqual(len(projects), 1)
    self.assertEqual(projects[0].keywords, ["single-keyword"])
    self.assertEqual(projects[0].year, 2023)
    query, parameters = driver.calls[0]
    self.assertIn("ORDER BY p.halId", query)
    self.assertIn("SKIP $offset", query)
    self.assertIn("LIMIT $limit", query)
    self.assertEqual(parameters, {"offset": 10, "limit": 5})

  def test_reads_authors_and_flags_unknown_ids_as_placeholders(self):
    driver = FakeDriver([
        ("MATCH (a:Author)-[:WROTE]->(p:Project", [
            {
                "person_id": "author-1",
                "full_name": "Ada Martin",
                "first_name": "",
                "last_name": "",
            },
            {
                "person_id": "unknown_Grace Hopper",
                "full_name": None,
                "first_name": "Grace",
                "last_name": "Hopper",
            },
        ]),
    ])
    adapter = Neo4jAdapter(driver=driver)

    members = adapter.get_project_members("hal-123")

    self.assertEqual(
        members,
        [
            PersonView("author-1", "Ada Martin", False),
            PersonView("unknown_Grace Hopper", "Grace Hopper", True),
        ],
    )
    query, parameters = driver.calls[0]
    self.assertIn("[:WROTE]", query)
    self.assertEqual(parameters, {"project_id": "hal-123"})

  def test_reads_project_domains_and_transitive_ancestors(self):
    driver = FakeDriver([
        ("MATCH (assigned)-[:SUBDOMAIN_OF*0..]->(d:ResearchDomain)", [
            {
                "domain_id": "1.1.1",
                "name": "Distributed systems",
                "parent_ids": ["1", "1.1"],
            },
            {"domain_id": "1.1", "name": "Computer science", "parent_ids": ["1"]},
            {"domain_id": "1", "name": "Engineering", "parent_ids": []},
        ]),
    ])
    adapter = Neo4jAdapter(driver=driver)

    domains = adapter.get_project_domains("hal-123")

    self.assertEqual(
        domains,
        [
            DomainView("1.1.1", "Distributed systems", ["1", "1.1"]),
            DomainView("1.1", "Computer science", ["1"]),
            DomainView("1", "Engineering", []),
        ],
    )
    self.assertEqual(driver.calls[0][1], {"project_id": "hal-123"})
    self.assertIn("HAS_RESEARCH_DOMAIN", driver.calls[0][0])

  def test_validates_pagination_and_returns_empty_capabilities(self):
    adapter = Neo4jAdapter(driver=FakeDriver([]))

    with self.assertRaises(ValueError):
      adapter.iter_projects(limit=-1)
    with self.assertRaises(ValueError):
      adapter.iter_projects(limit=1, offset=-1)
    self.assertEqual(adapter.iter_projects(limit=0), [])
    self.assertEqual(adapter.get_person_capabilities("author-1"), [])


if __name__ == "__main__":
  unittest.main()
