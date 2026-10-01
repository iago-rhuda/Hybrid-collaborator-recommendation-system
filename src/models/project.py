from dataclasses import dataclass, field


@dataclass(frozen=True)
class Project:
  """Common project schema used by the pipeline before persistence."""

  hal_id: str
  title: str
  abstract: str
  keywords: list[str] = field(default_factory=list)
  document_type: str = ""
  language: list[str] = field(default_factory=list)
  publication_date: str = ""
  publication_year: int | None = None
  doi: str = ""
  uri: str = ""

  def to_neo4j_dict(self) -> dict:
    return {
        "halId": self.hal_id,
        "title": self.title,
        "abstract": self.abstract,
        "keywords": self.keywords,
        "documentType": self.document_type,
        "language": self.language,
        "publicationDate": self.publication_date,
        "publicationYear": self.publication_year,
        "doi": self.doi,
        "uri": self.uri,
    }
