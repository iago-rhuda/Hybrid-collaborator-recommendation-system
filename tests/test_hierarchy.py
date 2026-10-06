import unittest

from validation.hierarchy import validate_domain_hierarchy


class DomainHierarchyValidationTest(unittest.TestCase):

  def test_reports_cycle_orphans_and_bad_parent_rules(self):
    domains = [
        {"id": "science", "name": "Science"},
        {"id": "science.math", "name": "Mathematics"},
        {"id": "standalone", "name": "Standalone"},
    ]
    hierarchy = [
        {"child_id": "science.math", "parent_id": "science"},
        {"child_id": "science", "parent_id": "science.math"},
    ]

    report = validate_domain_hierarchy(domains, hierarchy)
    checks = {check["name"]: check for check in report["checks"]}

    self.assertEqual(checks["cycles"]["finding_count"], 1)
    self.assertEqual(checks["orphan_domains"]["finding_count"], 1)
    self.assertEqual(checks["dotted_prefix_parent_rules"]["finding_count"], 1)

  def test_checks_maximum_depth_dotted_codes_and_domain_names(self):
    domains = [
        {"id": "a", "name": "A"},
        {"id": "a.b", "name": "B"},
        {"id": "a.b.c", "name": "C"},
        {"id": "a.b.c.d", "name": "D"},
        {"id": "a..e", "name": ""},
    ]
    hierarchy = [
        {"childId": "a.b", "parentId": "a"},
        {"childId": "a.b.c", "parentId": "a.b"},
        {"childId": "a.b.c.d", "parentId": "a.b.c"},
    ]

    report = validate_domain_hierarchy(
        domains,
        hierarchy,
        project_domain_relations=[{"domainId": "a..e"}],
        max_levels=3,
    )
    checks = {check["name"]: check for check in report["checks"]}

    self.assertEqual(checks["maximum_depth"]["findings"][0]["levels"], 4)
    self.assertEqual(checks["malformed_domain_ids"]["finding_count"], 1)
    self.assertEqual(checks["malformed_domain_names"]["finding_count"], 1)
    self.assertFalse(report["summary"]["is_valid"])
    self.assertIn("authoritative HAL source facts", report["taxonomy_policy"])

  def test_accepts_transformer_style_objects_and_valid_root_associations(self):
    class Domain:

      def __init__(self, domain_id, name):
        self.id = domain_id
        self.name = name
        self.name_fr = ""

    class Relation:

      def __init__(self, child_id, parent_id):
        self.child_id = child_id
        self.parent_id = parent_id

    report = validate_domain_hierarchy(
        [Domain("info", "Informatics"), Domain("info.ai", "Artificial Intelligence")],
        [Relation("info.ai", "info")],
        [{"domain_id": "info"}],
    )

    self.assertTrue(report["summary"]["is_valid"])
    self.assertEqual(report["checks"][1]["finding_count"], 0)

  def test_allows_missing_optional_french_label_and_flags_duplicate_ids(self):
    report = validate_domain_hierarchy(
        [
            {"id": "info", "name": "Informatics", "nameFr": ""},
            {"id": "info", "name": "Informatics", "nameFr": ""},
        ],
        [],
        [{"domainId": "missing-domain"}],
    )
    checks = {check["name"]: check for check in report["checks"]}

    self.assertEqual(checks["malformed_domain_names"]["finding_count"], 0)
    self.assertEqual(checks["duplicate_domain_ids"]["finding_count"], 1)
    self.assertEqual(
        checks["unknown_project_domain_associations"]["finding_count"],
        1,
    )

  def test_rejects_non_positive_maximum_depth(self):
    with self.assertRaises(ValueError):
      validate_domain_hierarchy([], [], max_levels=0)


if __name__ == "__main__":
  unittest.main()
