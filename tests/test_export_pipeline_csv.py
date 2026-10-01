import csv
import tempfile
import unittest
from pathlib import Path

from export_pipeline_csv import (
    build_csv_tables_from_hal_docs,
    write_csv_tables,
)


class ExportPipelineCsvTest(unittest.TestCase):

  def test_builds_csv_tables_for_all_current_models(self):
    docs = [{
        "halId_s": "hal-01699728",
        "title_s": ["A test article"],
        "abstract_s": ["A test abstract"],
        "keyword_s": ["pipeline", "neo4j"],
        "docType_s": "COMM",
        "language_s": ["en"],
        "publicationDate_s": "2026-01-03",
        "producedDate_s": "2026-01-02",
        "publicationDateY_i": 2026,
        "doiId_s": "10.0000/test",
        "uri_s": "https://hal.science/hal-01699728",
        "authFullName_s": ["Ada Lovelace"],
        "authIdHal_s": ["ada-lovelace"],
        "authIdPerson_i": [42],
        "authFirstName_s": ["Ada"],
        "authLastName_s": ["Lovelace"],
        "conferenceTitle_s": "TestConf",
        "conferenceStartDate_s": "2026-02-01",
        "conferenceEndDate_s": "2026-02-02",
        "city_s": "Compiègne",
        "country_s": "fr",
        "structId_i": [2175, 93027],
        "structName_s": [
            "Roberval",
            "Université de Technologie de Compiègne",
        ],
        "structAcronym_s": ["Roberval", "UTC"],
        "structType_s": ["laboratory", "institution"],
        "structCountry_s": ["fr", "fr"],
        "structValid_s": ["VALID", "VALID"],
        "structRorIdExt_s": [
            "https://ror.org/023ffhx15",
            "https://ror.org/04y5kwa70",
        ],
        "structIsChildOf_fs": [
            "2175_laboratory_JoinSep_93027_FacetSep_Université de Technologie de Compiègne",
        ],
        "primaryDomain_s": "spi.meca",
        "domainAllCode_s": ["spi.meca"],
        "en_domainAllCodeLabel_fs": [
            "spi.meca_FacetSep_Engineering Sciences/Mechanics",
        ],
        "fr_domainAllCodeLabel_fs": [
            "spi.meca_FacetSep_Sciences de l'ingénieur/Mécanique",
        ],
        "level0_domain_s": ["spi"],
        "level1_domain_s": ["spi.meca"],
    }]

    tables = build_csv_tables_from_hal_docs(docs)

    self.assertEqual(len(tables["projects"]), 1)
    self.assertEqual(len(tables["authors"]), 1)
    self.assertEqual(len(tables["conferences"]), 1)
    self.assertEqual(len(tables["organizations"]), 2)
    self.assertEqual(len(tables["research_domains"]), 2)
    self.assertEqual(len(tables["project_authors"]), 1)
    self.assertEqual(len(tables["project_conferences"]), 1)
    self.assertEqual(len(tables["project_organizations"]), 2)
    self.assertEqual(len(tables["organization_relationships"]), 1)
    self.assertEqual(len(tables["project_research_domains"]), 1)
    self.assertEqual(len(tables["research_domain_hierarchy"]), 1)
    project = tables["projects"]["hal-01699728"]
    self.assertEqual(project["publicationDate"], "2026-01-03")

  def test_writes_csv_files_with_headers(self):
    tables = build_csv_tables_from_hal_docs([{
        "halId_s": "hal-test",
        "title_s": ["CSV smoke test"],
    }])

    with tempfile.TemporaryDirectory() as temp_dir:
      files = write_csv_tables(tables, Path(temp_dir))
      projects_path = files["projects"]

      with projects_path.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))

    self.assertEqual(rows[0]["halId"], "hal-test")
    self.assertEqual(rows[0]["title"], "CSV smoke test")


if __name__ == "__main__":
  unittest.main()
