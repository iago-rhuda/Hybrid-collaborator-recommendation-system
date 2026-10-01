from dataclasses import dataclass


@dataclass(frozen=True)
class Author:
  """Common author schema used by the pipeline before persistence."""

  person_id: int | None
  hal_id: str
  first_name: str
  last_name: str
  email_domain: str
  orcid_id: str
  google_scholar_id: str
  researcher_id: str
  idref_id: str

  @property
  def full_name(self) -> str:
    return " ".join(
        part for part in [self.first_name, self.last_name] if part
    ).strip()

  def to_neo4j_dict(self) -> dict:
    return {
        "personId": self.person_id,
        "halId": self.hal_id,
        "firstName": self.first_name,
        "lastName": self.last_name,
        "fullName": self.full_name,
        "emailDomain": self.email_domain,
        "orcidId": self.orcid_id,
        "googleScholarId": self.google_scholar_id,
        "researcherId": self.researcher_id,
        "idrefId": self.idref_id,
    }
