import unittest

from export_pipeline_csv import build_csv_tables_from_hal_docs
from validation.etl_compare import (
    ENTITY_CONFIG,
    compare_expected_to_neo4j,
)


def _doc():
  return {
      "halId_s": "hal-compare-1",
      "title_s": ["A comparison fixture"],
      "abstract_s": ["Abstract text"],
      "keyword_s": ["graphs", "validation"],
      "docType_s": "COMM",
      "language_s": ["en"],
      "publicationDate_s": "2026-02-03",
      "publicationDateY_i": 2026,
      "authFullName_s": ["Ada Lovelace"],
      "authIdHal_s": ["ada-lovelace"],
      "authIdPerson_i": [42],
      "authFirstName_s": ["Ada"],
      "authLastName_s": ["Lovelace"],
      "conferenceTitle_s": "CompareConf",
      "conferenceStartDate_s": "2026-05-01",
      "conferenceEndDate_s": "2026-05-02",
      "city_s": "Compiègne",
      "country_s": "fr",
      "structId_i": [93027],
      "structName_s": ["Université de Technologie de Compiègne"],
      "structType_s": ["institution"],
      "structCountry_s": ["fr"],
      "structValid_s": ["VALID"],
      "structIsChildOf_fs": [],
      "primaryDomain_s": "info.info-db",
      "domainAllCode_s": ["info.info-db"],
      "en_domainAllCodeLabel_fs": [
          "info.info-db_FacetSep_Computer Science/Databases"
      ],
      "fr_domainAllCodeLabel_fs": [
          "info.info-db_FacetSep_Informatique/Base de données"
      ],
      "level0_domain_s": ["info"],
      "level1_domain_s": ["info.info-db"],
  }


def _matching_state(tables):
  entities = {}
  for table_name, (_label, _key_property) in ENTITY_CONFIG.items():
    entities[table_name] = {
        str(key): {"count": 1, "records": [dict(row)]}
        for key, row in tables[table_name].items()
    }

  relationship_specs = {
      "project_authors": ("projectHalId", "authorHalId"),
      "project_conferences": ("projectHalId", "conferenceId"),
      "project_organizations": ("projectHalId", "organizationHalId"),
      "project_research_domains": ("projectHalId", "domainId"),
      "organization_relationships": ("sourceId", "targetId"),
      "research_domain_hierarchy": ("childId", "parentId"),
  }
  relationships = {}
  for table_name, (source_field, target_field) in relationship_specs.items():
    relationships[table_name] = {
        (str(row[source_field]), str(row[target_field])): 1
        for row in tables[table_name].values()
    }
  return {"entities": entities, "relationships": relationships}


class EtlCompareTest(unittest.TestCase):

  def test_reports_property_and_relationship_losses(self):
    docs = [_doc()]
    tables = build_csv_tables_from_hal_docs(docs)
    state = _matching_state(tables)
    project = state["entities"]["projects"]["hal-compare-1"]["records"][0]
    project["publicationDate"] = "2026-03-04"
    state["relationships"]["project_authors"] = {}

    report = compare_expected_to_neo4j(tables, state, docs)

    self.assertEqual(
        report["entities"]["projects"]["field_mismatches"][0]["fields"][
            "publicationDate"
        ]["actual"],
        "2026-03-04",
    )
    self.assertEqual(
        len(report["relationships"]["project_authors"]["missing"]),
        1,
    )
    self.assertGreater(report["summary"]["errors"], 0)

  def test_reports_duplicate_input_records_and_database_nodes(self):
    docs = [_doc(), _doc()]
    tables = build_csv_tables_from_hal_docs(docs)
    state = _matching_state(tables)
    state["entities"]["projects"]["hal-compare-1"]["count"] = 2

    report = compare_expected_to_neo4j(tables, state, docs)

    self.assertEqual(
        report["source_duplicates"]["duplicate_project_record_count"],
        1,
    )
    self.assertEqual(
        report["entities"]["projects"]["duplicate_ids"],
        [{"id": "hal-compare-1", "count": 2}],
    )
    self.assertEqual(report["summary"]["warnings"], 1)

  def test_matching_state_has_no_mismatches(self):
    docs = [_doc()]
    tables = build_csv_tables_from_hal_docs(docs)

    report = compare_expected_to_neo4j(tables, _matching_state(tables), docs)

    self.assertEqual(report["summary"]["errors"], 0)
    self.assertEqual(report["summary"]["warnings"], 0)


if __name__ == "__main__":
  unittest.main()
