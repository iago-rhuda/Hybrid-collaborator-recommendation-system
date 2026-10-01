from dataclasses import dataclass, field


@dataclass(frozen=True)
class Organization:
  """Source-independent organization schema."""

  hal_id: int
  name: str
  acronym: str | None = None
  type: str | None = None
  country: str | None = None
  address: str | None = None
  code: str | None = None
  status: str | None = None
  ror: str | None = None
  idref: str | None = None
  isni: str | None = None
  rnsr: str | None = None
  wikidata: str | None = None

  def to_neo4j_dict(self) -> dict:
    return {
        "halId": self.hal_id,
        "name": self.name,
        "acronym": self.acronym,
        "type": self.type,
        "country": self.country,
        "address": self.address,
        "code": self.code,
        "status": self.status,
        "ror": self.ror,
        "idref": self.idref,
        "isni": self.isni,
        "rnsr": self.rnsr,
        "wikidata": self.wikidata,
    }


@dataclass(frozen=True)
class OrganizationRelationship:
  """Relationship metadata between organizations."""

  source_id: int
  target_id: int
  type: str = "PART_OF"

  def to_neo4j_dict(self) -> dict:
    return {
        "sourceId": self.source_id,
        "targetId": self.target_id,
        "type": self.type,
    }


@dataclass(frozen=True)
class OrganizationExtraction:
  """Organization nodes plus relationship metadata extracted from a source."""

  organizations: list[Organization] = field(default_factory=list)
  relationships: list[OrganizationRelationship] = field(default_factory=list)

  def to_neo4j_dict(self) -> dict:
    return {
        "organizations": [
            organization.to_neo4j_dict()
            for organization in self.organizations
        ],
        "organization_relationships": [
            relationship.to_neo4j_dict()
            for relationship in self.relationships
        ],
    }
