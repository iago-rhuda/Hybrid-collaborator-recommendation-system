from dataclasses import dataclass, field


@dataclass(frozen=True)
class ResearchDomain:
  """Source-independent research domain schema."""

  id: str
  name: str
  name_fr: str = ""
  source: str = "HAL"

  def to_neo4j_dict(self) -> dict:
    return {
        "id": self.id,
        "name": self.name,
        "nameFr": self.name_fr,
        "source": self.source,
    }


@dataclass(frozen=True)
class ResearchDomainAssociation:
  """Association metadata between a project and a research domain."""

  domain_id: str
  primary: bool = False

  def to_neo4j_dict(self) -> dict:
    return {
        "domainId": self.domain_id,
        "primary": self.primary,
    }


@dataclass(frozen=True)
class ResearchDomainHierarchy:
  """Hierarchy metadata between research domains."""

  child_id: str
  parent_id: str

  def to_neo4j_dict(self) -> dict:
    return {
        "childId": self.child_id,
        "parentId": self.parent_id,
    }


@dataclass(frozen=True)
class ResearchDomainExtraction:
  """Research domain nodes plus relationship metadata extracted from a source."""

  domains: list[ResearchDomain] = field(default_factory=list)
  associations: list[ResearchDomainAssociation] = field(default_factory=list)
  hierarchy: list[ResearchDomainHierarchy] = field(default_factory=list)

  def to_neo4j_dict(self) -> dict:
    return {
        "research_domains": [
            domain.to_neo4j_dict() for domain in self.domains
        ],
        "project_domain_relations": [
            association.to_neo4j_dict() for association in self.associations
        ],
        "domain_hierarchy_relations": [
            relation.to_neo4j_dict() for relation in self.hierarchy
        ],
    }
