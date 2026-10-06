import unittest

from validation.hal_validator import validate_hal_documents, validate_hal_payload


class HalValidatorTest(unittest.TestCase):

  def test_flags_missing_required_content_and_duplicate_ids(self):
    docs = [
        {
            "halId_s": "hal-1",
            "title_s": ["A short title"],
            "abstract_s": [""],
            "keyword_s": [],
            "doiId_s": "",
            "authFullName_s": ["Alice Example"],
            "authIdHal_s": ["alice"],
            "authIdPerson_i": ["42", "99"],
            "primaryDomain_s": "",
            "language_s": ["xx"],
            "docType_s": "",
            "publicationDate_s": "bad-date",
            "structId_i": [1, 2],
            "structName_s": ["Only one organization"],
        },
        {
            "halId_s": "hal-1",
            "title_s": ["Duplicate ID"],
            "abstract_s": ["Same doc"],
            "keyword_s": ["duplicate"],
            "doiId_s": "10.0/test",
            "authFullName_s": ["Bob"],
            "primaryDomain_s": "info.info-db",
            "docType_s": "COMM",
        },
    ]

    report = validate_hal_documents(docs, num_found=2)

    self.assertFalse(report.is_valid)
    self.assertTrue(any(issue.code == "missing_abstract" for issue in report.warnings))
    self.assertTrue(any(issue.code == "missing_keywords" for issue in report.warnings))
    self.assertTrue(any(issue.code == "missing_doi" for issue in report.warnings))
    self.assertTrue(any(issue.code == "duplicate_hal_id" for issue in report.errors))
    self.assertTrue(any(issue.code == "malformed_date" for issue in report.warnings))
    self.assertTrue(any(issue.code == "malformed_language" for issue in report.warnings))
    self.assertTrue(any(issue.code == "parallel_array_length_mismatch" for issue in report.warnings))

  def test_accepts_missing_optional_values_without_error(self):
    payload = {
        "response": {
            "numFound": 1,
            "docs": [{
                "halId_s": "hal-optional",
                "title_s": ["Valid title"],
                "abstract_s": ["A valid abstract"],
                "keyword_s": ["graph"],
                "doiId_s": "10.0/test",
                "authFullName_s": ["Ada Lovelace"],
                "authIdHal_s": ["ada"],
                "primaryDomain_s": "info.info-db",
                "docType_s": "COMM",
                "language_s": ["en"],
                "publicationDate_s": "2026-01-03",
            }],
        }
    }

    report = validate_hal_payload(payload)
    self.assertTrue(report.is_valid)

  def test_measures_missing_optional_metadata_as_warnings(self):
    report = validate_hal_documents([{
        "halId_s": "hal-optional-metadata",
        "title_s": ["Publication title"],
        "authFullName_s": ["Ada Lovelace"],
        "authIdHal_s": ["ada"],
        "docType_s": ["ART"],
    }])

    self.assertTrue(report.is_valid)
    self.assertEqual(
        {issue.code for issue in report.warnings},
        {
            "missing_abstract",
            "missing_keywords",
            "missing_doi",
            "missing_domains",
        },
    )

  def test_detects_http_and_pagination_issues(self):
    payload = {
        "response": {
            "numFound": 1,
            "docs": [
                {
                    "halId_s": "hal-paginated",
                    "title_s": ["Title"],
                    "abstract_s": ["Abstract"],
                    "keyword_s": ["keyword"],
                    "doiId_s": "10.0/test",
                    "authFullName_s": ["Author A"],
                    "primaryDomain_s": "math",
                    "docType_s": "COMM",
                }
            ],
        }
    }

    report = validate_hal_payload(payload, params={"start": 0, "rows": 1})
    self.assertTrue(report.is_valid)

    http_report = validate_hal_payload(payload, status_code=500)
    self.assertFalse(http_report.is_valid)
    self.assertTrue(any(issue.code == "http_error" for issue in http_report.errors))


if __name__ == "__main__":
  unittest.main()
