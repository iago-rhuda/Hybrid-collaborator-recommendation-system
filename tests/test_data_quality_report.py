import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from validation.hal_validator import validate_hal_documents
from validation.report import (
    build_data_quality_report,
    render_markdown_report,
    write_data_quality_report,
)


class DataQualityReportTest(unittest.TestCase):

  def test_builds_metrics_and_concrete_risks_from_inputs(self):
    docs = [
        {
            "halId_s": "hal-1",
            "title_s": ["First"],
            "abstract_s": ["English", "French"],
            "keyword_s": ["graph"],
            "authFullName_s": ["Ada Lovelace", "Same Name"],
            "authIdHal_s": ["ada", ""],
            "authIdPerson_i": [10],
            "primaryDomain_s": "info",
            "domainAllCode_s": ["info.ai"],
            "structId_i": [22],
        },
        {
            "halId_s": "hal-1",
            "title_s": ["Second"],
            "abstract_s": [],
            "keyword_s": [],
            "authFullName_s": ["Same Name"],
            "authIdHal_s": ["other-person"],
            "primaryDomain_s": "",
            "domainAllCode_s": [],
            "doiId_s": "",
        },
    ]
    manifest = {
        "query": "*:*",
        "timestamp": "20261004T120000Z",
        "numFound": 3,
        "fetched_count": 2,
    }
    hal_validation = validate_hal_documents(docs, num_found=3)
    etl_comparison = {
        "summary": {"errors": 1},
        "entities": {
            "projects": {
                "missing_ids": ["hal-2"],
                "duplicate_ids": [{"id": "hal-1"}],
                "field_mismatches": [],
            }
        },
        "relationships": {
            "project_authors": {
                "missing": [{"source": "hal-1", "target": "author"}],
                "unexpected": [],
                "duplicates": [],
            }
        },
        "cause_hypotheses": ["Possible partial import."],
    }
    hierarchy = {
        "summary": {"finding_count": 1},
        "checks": [{"name": "cycles", "finding_count": 1, "findings": [[]]}],
    }
    integrity = {
        "summary": {"finding_count": 1},
        "checks": [{
            "name": "bare_organizations",
            "finding_count": 1,
            "findings": [{"organization_id": "22"}],
        }],
    }

    report = build_data_quality_report(
        docs,
        manifest=manifest,
        hal_validation=hal_validation,
        etl_comparison=etl_comparison,
        hierarchy=hierarchy,
        integrity=integrity,
        report_date=date(2026, 10, 4),
    )

    self.assertEqual(report["hal"]["records_retrieved"], 2)
    self.assertEqual(report["hal"]["counts"]["projects"], 1)
    self.assertEqual(report["hal"]["counts"]["authors"], 3)
    self.assertEqual(
        report["hal"]["duplicate_ids"]["duplicate_record_count"],
        1,
    )
    self.assertEqual(
        report["hal"]["author_array_alignment"]["mismatched_record_count"],
        1,
    )
    self.assertAlmostEqual(
        report["hal"]["author_identity"]["unknown_author_share"],
        1 / 3,
        places=4,
    )
    self.assertEqual(report["hal"]["pagination"]["complete"], False)
    self.assertEqual(report["etl_comparison"]["entity_mismatch_count"], 2)
    self.assertEqual(report["hierarchy"]["violation_count"], 1)
    self.assertEqual(report["neo4j_integrity"]["bare_organization_count"], 1)
    self.assertTrue(any("Stale-node behavior was not tested" in risk for risk in report["open_risks"]))
    self.assertIn("not rewrite it", report["hierarchy"]["taxonomy_policy"])

  def test_writes_date_stamped_json_and_markdown(self):
    report = build_data_quality_report(
        [],
        report_date=date(2026, 10, 4),
    )
    with tempfile.TemporaryDirectory() as temporary_directory:
      paths = write_data_quality_report(report, temporary_directory)

      self.assertEqual(paths["json"].name, "data_quality_2026-10-04.json")
      self.assertEqual(paths["markdown"].name, "data_quality_2026-10-04.md")
      decoded = json.loads(paths["json"].read_text(encoding="utf-8"))
      markdown = paths["markdown"].read_text(encoding="utf-8")

    self.assertEqual(decoded["report_date"], "2026-10-04")
    self.assertIn("## Conclusions", markdown)
    self.assertIn("## Open risks", markdown)
    self.assertIn("authoritative source facts", markdown)

  def test_rejects_invalid_documents(self):
    with self.assertRaises(TypeError):
      build_data_quality_report([{"halId_s": "ok"}, "not-a-document"])


if __name__ == "__main__":
  unittest.main()
