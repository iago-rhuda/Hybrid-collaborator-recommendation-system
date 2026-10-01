from models.author import Author
from models.conference import Conference
from models.organization import (
    Organization,
    OrganizationExtraction,
    OrganizationRelationship,
)
from models.project import Project
from models.research_domain import (
    ResearchDomain,
    ResearchDomainAssociation,
    ResearchDomainExtraction,
    ResearchDomainHierarchy,
)


def _as_list(value) -> list:
  if value is None:
    return []
  return value if isinstance(value, list) else [value]


def _get_first_value(value, default=""):
  values = _as_list(value)
  return values[0] if values and values[0] else default


def _unique_values(values) -> list:
  seen = set()
  unique = []
  for value in values:
    if value is None:
      continue
    value = str(value).strip()
    if value and value not in seen:
      unique.append(value)
      seen.add(value)
  return unique


def _get_list_value(values, index: int, default=""):
  if not isinstance(values, list):
    return default
  return values[index] if index < len(values) and values[index] else default


def _get_int_list_value(values, index: int):
  value = _get_list_value(values, index, None)
  return int(value) if value is not None and str(value).isdigit() else None


def _get_parallel_value(values, index: int, expected_length: int):
  values = _as_list(values)
  if len(values) != expected_length or index >= len(values):
    return None
  value = values[index]
  if value is None or value == "":
    return None
  return str(value).strip()


def _parse_int_value(value):
  if value is None:
    return None
  value = str(value).strip()
  return int(value) if value.isdigit() else None


def _normalize_ror(value):
  if not value:
    return None
  value = str(value).strip()
  return value.rstrip("/").split("/")[-1]


def _slugify(value: str) -> str:
  clean_value = value.strip().lower()
  return "_".join(clean_value.split())


def _parse_year(value) -> int | None:
  value = str(value)
  if value.isdigit():
    return int(value)
  return int(value[:4]) if len(value) >= 4 and value[:4].isdigit() else None


def _clean_domain_label(label: str) -> str:
  label = str(label).split("/")[-1].strip()
  if label.endswith("]") and "[" in label:
    label = label.rsplit("[", 1)[0].strip()
  return label


def _parse_domain_label_map(label_values, domain_codes: list[str]) -> dict:
  label_map = {}
  labels = _as_list(label_values)
  separators = ["_FacetSep_", "###", "##", "|"]

  for index, raw_label in enumerate(labels):
    raw_label = str(raw_label).strip()
    if not raw_label:
      continue

    code = ""
    label = raw_label
    for separator in separators:
      if separator in raw_label:
        code, label = raw_label.split(separator, 1)
        break

    if not code and ":" in raw_label:
      possible_code, possible_label = raw_label.split(":", 1)
      if possible_code in domain_codes:
        code = possible_code
        label = possible_label

    if not code and index < len(domain_codes):
      code = domain_codes[index]

    code = code.strip()
    if code:
      label_map[code] = _clean_domain_label(label)

  return label_map


def _extract_domain_level_codes(doc: dict) -> dict[int, list[str]]:
  return {
      0: _unique_values(_as_list(doc.get("level0_domain_s"))),
      1: _unique_values(_as_list(doc.get("level1_domain_s"))),
      2: _unique_values(_as_list(doc.get("level2_domain_s"))),
  }


def _find_parent_domain(child_code: str, parent_candidates: list[str]) -> str | None:
  matching_parents = [
      parent
      for parent in parent_candidates
      if child_code != parent and child_code.startswith(f"{parent}.")
  ]
  if not matching_parents:
    return None
  return max(matching_parents, key=len)


def _extract_domain_hierarchy(level_codes: dict[int, list[str]]):
  hierarchy = []
  seen = set()

  for level in sorted(level_codes):
    if level == 0:
      continue

    parent_candidates = []
    for parent_level in range(level - 1, -1, -1):
      parent_candidates.extend(level_codes.get(parent_level, []))

    for child_code in level_codes.get(level, []):
      parent_code = _find_parent_domain(child_code, parent_candidates)
      if parent_code and (child_code, parent_code) not in seen:
        hierarchy.append(
            ResearchDomainHierarchy(
                child_id=child_code,
                parent_id=parent_code,
            )
        )
        seen.add((child_code, parent_code))

  return hierarchy


def _merge_organization(existing: Organization, incoming: Organization):
  return Organization(
      hal_id=existing.hal_id,
      name=existing.name or incoming.name,
      acronym=existing.acronym or incoming.acronym,
      type=existing.type or incoming.type,
      country=existing.country or incoming.country,
      address=existing.address or incoming.address,
      code=existing.code or incoming.code,
      status=existing.status or incoming.status,
      ror=existing.ror or incoming.ror,
      idref=existing.idref or incoming.idref,
      isni=existing.isni or incoming.isni,
      rnsr=existing.rnsr or incoming.rnsr,
      wikidata=existing.wikidata or incoming.wikidata,
  )


def _parse_organization_relationship(value):
  value = str(value)
  if "_JoinSep_" not in value:
    return None

  source_part, target_part = value.split("_JoinSep_", 1)
  source_id = _parse_int_value(source_part.split("_", 1)[0])
  target_id = _parse_int_value(target_part.split("_FacetSep_", 1)[0])

  if source_id is None or target_id is None:
    return None
  return OrganizationRelationship(source_id=source_id, target_id=target_id)


def extract_authors_from_hal_record(doc: dict) -> list[Author]:
  """Maps HAL author fields to the common Author schema."""
  names = doc.get("authFullName_s", [])
  authors = []

  for index, full_name in enumerate(names):
    first_name = _get_list_value(doc.get("authFirstName_s", []), index)
    last_name = _get_list_value(doc.get("authLastName_s", []), index)

    if not first_name and not last_name and full_name:
      name_parts = full_name.split(maxsplit=1)
      first_name = name_parts[0]
      last_name = name_parts[1] if len(name_parts) > 1 else ""

    hal_id = _get_list_value(doc.get("authIdHal_s", []), index)
    if not hal_id:
      hal_id = f"unknown_{full_name or index}"

    authors.append(
        Author(
            person_id=_get_int_list_value(doc.get("authIdPerson_i", []), index),
            hal_id=str(hal_id),
            first_name=str(first_name),
            last_name=str(last_name),
            email_domain=str(
                _get_list_value(doc.get("authEmailDomain_s", []), index)
            ),
            orcid_id=str(_get_list_value(doc.get("authORCIDIdExt_s", []), index)),
            google_scholar_id=str(
                _get_list_value(doc.get("authGoogleScholarIdExt_s", []), index)
            ),
            researcher_id=str(
                _get_list_value(doc.get("authResearcherIdIdExt_s", []), index)
            ),
            idref_id=str(_get_list_value(doc.get("authIdRefIdExt_s", []), index)),
        )
    )

  return authors


def extract_organizations_from_hal_record(doc: dict) -> OrganizationExtraction:
  """Maps HAL struct fields to source-independent organization data."""
  struct_ids = _as_list(doc.get("structId_i"))
  total_structures = len(struct_ids)
  organizations = {}
  organization_order = []

  for index, raw_hal_id in enumerate(struct_ids):
    hal_id = _parse_int_value(raw_hal_id)
    if hal_id is None:
      continue

    organization = Organization(
        hal_id=hal_id,
        name=_get_parallel_value(
            doc.get("structName_s"), index, total_structures
        ) or "",
        acronym=_get_parallel_value(
            doc.get("structAcronym_s"), index, total_structures
        ),
        type=_get_parallel_value(
            doc.get("structType_s"), index, total_structures
        ),
        country=_get_parallel_value(
            doc.get("structCountry_s"), index, total_structures
        ),
        address=_get_parallel_value(
            doc.get("structAddress_s"), index, total_structures
        ),
        code=_get_parallel_value(
            doc.get("structCode_s"), index, total_structures
        ),
        status=_get_parallel_value(
            doc.get("structValid_s"), index, total_structures
        ),
        ror=_normalize_ror(
            _get_parallel_value(
                doc.get("structRorIdExt_s"), index, total_structures
            )
        ),
        idref=_get_parallel_value(
            doc.get("structIdrefIdExt_s"), index, total_structures
        ),
        isni=_get_parallel_value(
            doc.get("structIsniIdExt_s"), index, total_structures
        ),
        rnsr=_get_parallel_value(
            doc.get("structRnsrIdExt_s"), index, total_structures
        ),
        wikidata=_get_parallel_value(
            doc.get("structWikidataIdExt_s"), index, total_structures
        ),
    )

    if hal_id not in organizations:
      organizations[hal_id] = organization
      organization_order.append(hal_id)
    else:
      organizations[hal_id] = _merge_organization(
          organizations[hal_id], organization
      )

  relationships = []
  seen_relationships = set()
  for value in _as_list(doc.get("structIsChildOf_fs")):
    relationship = _parse_organization_relationship(value)
    if not relationship:
      continue
    key = (
        relationship.source_id,
        relationship.target_id,
        relationship.type,
    )
    if key not in seen_relationships:
      relationships.append(relationship)
      seen_relationships.add(key)

  return OrganizationExtraction(
      organizations=[
          organizations[hal_id]
          for hal_id in organization_order
      ],
      relationships=relationships,
  )


def extract_conference_from_hal_record(doc: dict) -> Conference | None:
  """Maps HAL conference fields to the common Conference schema."""
  title = doc.get("conferenceTitle_s", "")
  if isinstance(title, list):
    title = title[0] if title else ""

  if not title:
    return None

  start_date = doc.get("conferenceStartDate_s", "")
  end_date = doc.get("conferenceEndDate_s", "")
  city = doc.get("city_s", "")
  country = doc.get("country_s", "")

  conference_id = "_".join(
      part
      for part in [
          _slugify(str(title)),
          _slugify(str(start_date)),
          _slugify(str(city)),
          _slugify(str(country)),
      ]
      if part
  )

  return Conference(
      conference_id=conference_id,
      title=str(title),
      start_date=str(start_date),
      end_date=str(end_date),
      city=str(city),
      country=str(country),
  )


def extract_project_from_hal_record(doc: dict) -> Project:
  """Maps HAL document fields to the common Project schema."""
  publication_year = doc.get("publicationDateY_i")
  if publication_year is None:
    publication_year = doc.get("producedDate_s", "")
  publication_year = _parse_year(publication_year)

  return Project(
      hal_id=str(doc.get("halId_s", doc.get("docid", "Unknown"))),
      title=str(_get_first_value(doc.get("title_s"), "Untitled")),
      abstract=str(_get_first_value(doc.get("abstract_s"), "")),
      keywords=[str(keyword) for keyword in _as_list(doc.get("keyword_s"))],
      document_type=str(doc.get("docType_s", "")),
      language=[str(language) for language in _as_list(doc.get("language_s"))],
      publication_date=str(doc.get("publicationDate_s", "")),
      publication_year=publication_year,
      doi=str(doc.get("doiId_s", "")),
      uri=str(doc.get("uri_s", "")),
  )


def extract_research_domains_from_hal_record(doc: dict) -> ResearchDomainExtraction:
  """Maps HAL domain fields to source-independent research domain data."""
  primary_domain = str(doc.get("primaryDomain_s", "")).strip()
  domain_codes = _unique_values(
      _as_list(doc.get("domainAllCode_s")) or _as_list(doc.get("domain_s"))
  )
  if primary_domain and primary_domain not in domain_codes:
    domain_codes.insert(0, primary_domain)

  level_codes = _extract_domain_level_codes(doc)
  hierarchy = _extract_domain_hierarchy(level_codes)
  hierarchy_codes = [
      code
      for relation in hierarchy
      for code in [relation.child_id, relation.parent_id]
  ]
  all_domain_codes = _unique_values(domain_codes + hierarchy_codes)

  english_labels = _parse_domain_label_map(
      doc.get("en_domainAllCodeLabel_fs"), all_domain_codes
  )
  french_labels = _parse_domain_label_map(
      doc.get("fr_domainAllCodeLabel_fs"), all_domain_codes
  )

  domains = [
      ResearchDomain(
          id=code,
          name=english_labels.get(code) or french_labels.get(code) or code,
          name_fr=french_labels.get(code, ""),
          source="HAL",
      )
      for code in all_domain_codes
  ]
  associations = [
      ResearchDomainAssociation(
          domain_id=code,
          primary=bool(primary_domain and code == primary_domain),
      )
      for code in domain_codes
  ]

  return ResearchDomainExtraction(
      domains=domains,
      associations=associations,
      hierarchy=hierarchy,
  )
