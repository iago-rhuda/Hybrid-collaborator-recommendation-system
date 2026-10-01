import unittest

from processing.transformer import extract_organizations_from_hal_record


class OrganizationTransformerTest(unittest.TestCase):

  def test_extracts_institution_and_laboratory_as_organizations(self):
    doc = {
        "structId_i": [2175, 93027],
        "structName_s": [
            "Roberval",
            "Université de Technologie de Compiègne",
        ],
        "structAcronym_s": ["Roberval", "UTC"],
        "structType_s": ["laboratory", "institution"],
        "structCountry_s": ["fr", "fr"],
        "structAddress_s": [
            "Centre de Recherche de Royallieu",
            "rue du Docteur Schweitzer",
        ],
        "structCode_s": ["UMR7337", "UTC"],
        "structValid_s": ["VALID", "VALID"],
        "structRorIdExt_s": [
            "https://ror.org/023ffhx15",
            "https://ror.org/04y5kwa70",
        ],
        "structIdrefIdExt_s": ["123456789", "029644631"],
        "structIsChildOf_fs": [
            "2175_laboratory_JoinSep_93027_FacetSep_Université de Technologie de Compiègne",
            "2175_Roberval_JoinSep_93027_FacetSep_Université de Technologie de Compiègne",
        ],
    }

    result = extract_organizations_from_hal_record(doc)
    organizations = {org.hal_id: org for org in result.organizations}

    self.assertEqual(organizations[2175].name, "Roberval")
    self.assertEqual(organizations[2175].type, "laboratory")
    self.assertEqual(organizations[2175].ror, "023ffhx15")
    self.assertEqual(
        organizations[93027].name,
        "Université de Technologie de Compiègne",
    )
    self.assertEqual(organizations[93027].acronym, "UTC")
    self.assertEqual(organizations[93027].type, "institution")
    self.assertEqual(organizations[93027].idref, "029644631")
    self.assertEqual(len(result.relationships), 1)
    self.assertEqual(result.relationships[0].source_id, 2175)
    self.assertEqual(result.relationships[0].target_id, 93027)
    self.assertEqual(result.relationships[0].type, "PART_OF")

  def test_extracts_multiple_organizations_with_parallel_alignment(self):
    doc = {
        "structId_i": [1, 2, 3],
        "structName_s": ["Team A", "Lab B", "Institution C"],
        "structAcronym_s": ["TA", "LB", "IC"],
        "structType_s": ["researchteam", "laboratory", "institution"],
        "structCountry_s": ["fr", "mx", "us"],
        "structValid_s": ["OLD", "VALID", "INCOMING"],
    }

    result = extract_organizations_from_hal_record(doc)

    self.assertEqual([org.hal_id for org in result.organizations], [1, 2, 3])
    self.assertEqual(result.organizations[0].name, "Team A")
    self.assertEqual(result.organizations[0].type, "researchteam")
    self.assertEqual(result.organizations[1].name, "Lab B")
    self.assertEqual(result.organizations[1].country, "mx")
    self.assertEqual(result.organizations[2].acronym, "IC")
    self.assertEqual(result.organizations[2].status, "INCOMING")

  def test_handles_missing_optional_fields(self):
    doc = {
        "structId_i": [93027],
        "structName_s": ["Université de Technologie de Compiègne"],
        "structType_s": ["institution"],
    }

    result = extract_organizations_from_hal_record(doc)
    organization = result.organizations[0]

    self.assertEqual(organization.hal_id, 93027)
    self.assertEqual(organization.name, "Université de Technologie de Compiègne")
    self.assertEqual(organization.type, "institution")
    self.assertIsNone(organization.acronym)
    self.assertIsNone(organization.ror)

  def test_deduplicates_by_hal_id_without_deduplicating_by_name(self):
    doc = {
        "structId_i": [2175, 2175, 93027],
        "structName_s": ["Roberval", "Roberval", "Roberval"],
        "structAcronym_s": ["Roberval", "ROB", "UTC"],
        "structType_s": ["laboratory", "laboratory", "institution"],
        "structCountry_s": ["fr", "fr", "fr"],
        "structValid_s": ["VALID", "VALID", "VALID"],
    }

    result = extract_organizations_from_hal_record(doc)

    self.assertEqual([org.hal_id for org in result.organizations], [2175, 93027])
    self.assertEqual(result.organizations[0].name, "Roberval")
    self.assertEqual(result.organizations[1].name, "Roberval")
    self.assertEqual(result.organizations[1].type, "institution")

  def test_does_not_guess_sparse_external_identifier_alignment(self):
    doc = {
        "structId_i": [2175, 93027, 412526],
        "structName_s": ["Roberval", "UTC", "DeltaCAD"],
        "structType_s": ["laboratory", "institution", "institution"],
        "structRorIdExt_s": [
            "https://ror.org/023ffhx15",
            "https://ror.org/04y5kwa70",
        ],
    }

    result = extract_organizations_from_hal_record(doc)

    self.assertIsNone(result.organizations[0].ror)
    self.assertIsNone(result.organizations[1].ror)
    self.assertIsNone(result.organizations[2].ror)


if __name__ == "__main__":
  unittest.main()
