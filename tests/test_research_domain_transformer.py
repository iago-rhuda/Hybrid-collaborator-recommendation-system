import unittest

from processing.transformer import extract_research_domains_from_hal_record


class ResearchDomainTransformerTest(unittest.TestCase):

  def test_extracts_domains_with_labels_primary_and_hierarchy(self):
    doc = {
        "primaryDomain_s": "spi.meca",
        "domainAllCode_s": ["spi.meca", "info.info-db", "spi.meca"],
        "en_domainAllCodeLabel_fs": [
            "spi.meca_FacetSep_Engineering Sciences/Mechanics",
            "info.info-db_FacetSep_Computer Science [cs]/Databases [cs.DB]",
        ],
        "fr_domainAllCodeLabel_fs": [
            "spi.meca_FacetSep_Sciences de l'ingénieur/Mécanique",
            "info.info-db_FacetSep_Informatique [cs]/Base de données [cs.DB]",
        ],
        "level0_domain_s": ["spi", "info"],
        "level1_domain_s": ["spi.meca", "info.info-db"],
        "level2_domain_s": [],
    }

    result = extract_research_domains_from_hal_record(doc)
    domains = {domain.id: domain for domain in result.domains}
    associations = {
        association.domain_id: association for association in result.associations
    }
    hierarchy = {
        (relation.child_id, relation.parent_id) for relation in result.hierarchy
    }

    self.assertEqual(domains["spi.meca"].name, "Mechanics")
    self.assertEqual(domains["spi.meca"].name_fr, "Mécanique")
    self.assertEqual(domains["spi.meca"].source, "HAL")
    self.assertNotIn("level", domains["spi.meca"].to_neo4j_dict())
    self.assertEqual(domains["info.info-db"].name, "Databases")
    self.assertEqual(domains["info.info-db"].name_fr, "Base de données")
    self.assertEqual(len(result.associations), 2)
    self.assertTrue(associations["spi.meca"].primary)
    self.assertFalse(associations["info.info-db"].primary)
    self.assertIn(("spi.meca", "spi"), hierarchy)
    self.assertIn(("info.info-db", "info"), hierarchy)

  def test_handles_missing_fields_gracefully(self):
    result = extract_research_domains_from_hal_record({})

    self.assertEqual(result.domains, [])
    self.assertEqual(result.associations, [])
    self.assertEqual(result.hierarchy, [])

  def test_supports_primary_domain_when_all_codes_are_missing(self):
    doc = {
        "primaryDomain_s": "info.info-ai",
        "en_domainAllCodeLabel_fs": [
            "info.info-ai_FacetSep_Computer Science/Artificial Intelligence"
        ],
    }

    result = extract_research_domains_from_hal_record(doc)

    self.assertEqual(len(result.domains), 1)
    self.assertEqual(result.domains[0].id, "info.info-ai")
    self.assertEqual(result.domains[0].name, "Artificial Intelligence")
    self.assertEqual(len(result.associations), 1)
    self.assertTrue(result.associations[0].primary)


if __name__ == "__main__":
  unittest.main()
