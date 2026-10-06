import unittest

from validation.neo4j_integrity import (
    DIAGNOSTIC_QUERIES,
    REQUIRED_UNIQUE_KEYS,
    run_integrity_checks,
)


class _FakeSession:

  def __init__(self, responses):
    self.responses = iter(responses)
    self.calls = []

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_value, traceback):
    return False

  def run(self, query, **parameters):
    self.calls.append((query, parameters))
    return next(self.responses)


class _FakeDriver:

  def __init__(self, responses):
    self.fake_session = _FakeSession(responses)

  def session(self):
    return self.fake_session


class Neo4jIntegrityTest(unittest.TestCase):

  def test_reports_preventive_constraints_and_diagnostic_findings(self):
    constraints = [
        {
            "type": "UNIQUENESS",
            "entityType": "NODE",
            "labelsOrTypes": [label],
            "properties": [property_name],
        }
        for label, property_name in REQUIRED_UNIQUE_KEYS
    ]
    responses = [
        constraints,
        [{"entity": "Project", "id": "duplicate", "duplicates": 2}],
        [],
        [{"project_id": "orphan-project"}],
        [],
        [{"organization_id": "bare-organization"}],
        [],
        [{"relationship": "WROTE", "multiplicity": 2}],
        [{"author_id": "unknown_Ada", "full_name": "Ada"}],
    ]
    driver = _FakeDriver(responses)

    report = run_integrity_checks(driver)

    self.assertEqual(report["summary"]["check_count"], 9)
    self.assertEqual(report["summary"]["preventive_check_count"], 1)
    self.assertEqual(report["summary"]["diagnostic_check_count"], 8)
    self.assertEqual(report["summary"]["checks_with_findings"], 5)
    checks = {check["name"]: check for check in report["checks"]}
    self.assertEqual(
        checks["unique_id_constraints"]["classification"],
        "preventive",
    )
    self.assertEqual(checks["duplicate_ids"]["classification"], "diagnostic")
    self.assertEqual(checks["duplicate_ids"]["finding_count"], 1)
    self.assertEqual(
        checks["unknown_authors"]["findings"][0]["author_id"],
        "unknown_Ada",
    )

    query_parameters = {
        name: parameters
        for (query, parameters), name in zip(
            driver.fake_session.calls,
            ["constraints", *DIAGNOSTIC_QUERIES],
        )
    }
    self.assertEqual(
        query_parameters["unknown_authors"],
        {"prefix": "unknown_"},
    )
    self.assertTrue(
        all(isinstance(query, str) for query, _parameters in driver.fake_session.calls)
    )

  def test_reports_missing_preventive_constraints(self):
    driver = _FakeDriver([[]] + [[] for _ in DIAGNOSTIC_QUERIES])

    report = run_integrity_checks(driver)

    preventive = report["checks"][0]
    self.assertEqual(preventive["status"], "findings")
    self.assertEqual(preventive["finding_count"], len(REQUIRED_UNIQUE_KEYS))


if __name__ == "__main__":
  unittest.main()
