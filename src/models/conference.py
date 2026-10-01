from dataclasses import dataclass


@dataclass(frozen=True)
class Conference:
  """Common conference schema used by the pipeline before persistence."""

  conference_id: str
  title: str
  start_date: str
  end_date: str
  city: str
  country: str

  def to_neo4j_dict(self) -> dict:
    return {
        "conferenceId": self.conference_id,
        "title": self.title,
        "startDate": self.start_date,
        "endDate": self.end_date,
        "city": self.city,
        "country": self.country,
    }
