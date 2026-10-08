import json
import unittest
from pathlib import Path

from graph.fake_adapter import FakeAdapter


class FakeAdapterTest(unittest.TestCase):

  def setUp(self):
    self.adapter = FakeAdapter()

  def test_provides_at_least_thirty_projects_with_pagination(self):
    projects = self.adapter.iter_projects(limit=30)

    self.assertEqual(len(self.adapter.iter_projects(limit=100)), 32)
    self.assertEqual(len(projects), 30)
    self.assertEqual(
        [project.project_id for project in projects],
        [
            project.project_id
            for project in self.adapter.iter_projects(limit=10, offset=0)
        ] + [
            project.project_id
            for project in self.adapter.iter_projects(limit=20, offset=10)
        ],
    )
    self.assertEqual(
        self.adapter.get_project("hal-001").title,
        "Deep Learning for Natural Language Processing",
    )
    self.assertIsNone(self.adapter.get_project("missing-project"))

  def test_models_overlapping_authors_and_placeholder_authors(self):
    first_project_members = self.adapter.get_project_members("hal-001")
    second_project_members = self.adapter.get_project_members("hal-002")
    first_ids = {person.person_id for person in first_project_members}
    second_ids = {person.person_id for person in second_project_members}

    self.assertTrue(first_ids & second_ids)

    placeholder_adapter = FakeAdapter(
        projects=[{
            "project_id": "placeholder-project",
            "members": [{
                "person_id": "unknown_Grace Hopper",
                "full_name": "Grace Hopper",
            }],
        }],
        capabilities=[],
    )
    placeholder_members = placeholder_adapter.get_project_members(
        "placeholder-project"
    )
    self.assertTrue(any(person.is_placeholder for person in placeholder_members))
    self.assertTrue(
        all(
            person.is_placeholder == person.person_id.startswith("unknown_")
            for person in placeholder_members
        )
    )
    self.assertEqual(self.adapter.get_project_members("missing-project"), [])

  def test_project_domains_include_their_full_ancestor_chain(self):
    domains = self.adapter.get_project_domains("hal-001")
    domains_by_id = {domain.domain_id: domain for domain in domains}

    self.assertEqual(
        set(domains_by_id),
        {"info", "info.info-ai"},
    )
    self.assertEqual(
        domains_by_id["info.info-ai"].parent_ids,
        ["info"],
    )
    self.assertEqual(self.adapter.get_project_domains("missing-project"), [])

  def test_dev_project_fixture_matches_fake_adapter_data(self):
    fixture_path = (
        Path(__file__).parent / "fixtures" / "dev_projects.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    self.assertEqual(len(fixture), 32)
    self.assertEqual(
        fixture[0]["project_id"],
        self.adapter.iter_projects(limit=1)[0].project_id,
    )
    first_project = fixture[0]
    self.assertTrue(first_project["members"])
    self.assertTrue(first_project["domains"])
    self.assertEqual(first_project["year"], 2022)

  def test_rejects_invalid_pagination_and_returns_empty_capabilities(self):
    with self.assertRaises(ValueError):
      self.adapter.iter_projects(limit=-1)
    with self.assertRaises(ValueError):
      self.adapter.iter_projects(limit=1, offset=-1)
    self.assertEqual(self.adapter.get_person_capabilities("author-001"), [])

  def test_finds_only_canonical_capabilities_for_terms(self):
    capabilities = self.adapter.find_capabilities_by_terms([
        "write",
        "article",
        "federated learning",
        "Differential Privacy",
    ])

    self.assertEqual(
        [cap.capability_id for cap in capabilities],
        ["differential_privacy", "federated_learning"],
    )


if __name__ == "__main__":
  unittest.main()
