import json
import unittest
from pathlib import Path

from graph.fake_adapter import FakeAdapter


class FakeAdapterTest(unittest.TestCase):

  def setUp(self):
    self.adapter = FakeAdapter()

  def test_provides_at_least_thirty_synthetic_projects_with_pagination(self):
    projects = self.adapter.iter_projects(limit=30)

    self.assertEqual(len(self.adapter.iter_projects(limit=100)), 36)
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
        self.adapter.get_project("fixture-hal-0001").title,
        "Synthetic research publication 01",
    )
    self.assertIsNone(self.adapter.get_project("missing-project"))

  def test_models_overlapping_authors_and_placeholder_authors(self):
    first_project_members = self.adapter.get_project_members("fixture-hal-0001")
    second_project_members = self.adapter.get_project_members("fixture-hal-0002")
    first_ids = {person.person_id for person in first_project_members}
    second_ids = {person.person_id for person in second_project_members}

    self.assertTrue(first_ids & second_ids)

    placeholder_members = self.adapter.get_project_members("fixture-hal-0006")
    self.assertTrue(any(person.is_placeholder for person in placeholder_members))
    self.assertTrue(
        all(
            person.is_placeholder == person.person_id.startswith("unknown_")
            for person in placeholder_members
        )
    )
    self.assertEqual(self.adapter.get_project_members("missing-project"), [])

  def test_project_domains_include_their_full_ancestor_chain(self):
    domains = self.adapter.get_project_domains("fixture-hal-0001")
    domains_by_id = {domain.domain_id: domain for domain in domains}

    self.assertEqual(
        set(domains_by_id),
        {"fixture.1", "fixture.1.1", "fixture.1.1.1"},
    )
    self.assertEqual(
        domains_by_id["fixture.1.1.1"].parent_ids,
        ["fixture.1", "fixture.1.1"],
    )
    self.assertEqual(self.adapter.get_project_domains("missing-project"), [])

  def test_dev_project_fixture_is_labeled_and_matches_fake_adapter_data(self):
    fixture_path = (
        Path(__file__).parent / "fixtures" / "dev_projects.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    self.assertIn("Synthetic", fixture["source"])
    self.assertEqual(fixture["project_count"], 36)
    self.assertEqual(len(fixture["projects"]), 36)
    self.assertEqual(
        fixture["projects"][0]["project_id"],
        self.adapter.iter_projects(limit=1)[0].project_id,
    )
    first_project = fixture["projects"][0]
    self.assertTrue(first_project["authors"])
    self.assertTrue(first_project["domains"])
    self.assertEqual(first_project["year"], 2010)
    self.assertTrue(
        any(
            author["is_placeholder"]
            for project in fixture["projects"]
            for author in project["authors"]
        )
    )

  def test_rejects_invalid_pagination_and_marks_later_methods_unimplemented(self):
    with self.assertRaises(ValueError):
      self.adapter.iter_projects(limit=-1)
    with self.assertRaises(ValueError):
      self.adapter.iter_projects(limit=1, offset=-1)
    with self.assertRaisesRegex(NotImplementedError, "Stage A"):
      self.adapter.get_person_capabilities("author-001")


if __name__ == "__main__":
  unittest.main()
