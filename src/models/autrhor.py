from dataclasses import dataclass


@dataclass
class Author:
  name: str
  auth_id_hal: str
  person_id: int
  first_name: str
  last_name: str
  email_domain: str

  @classmethod
  def from_hal_record(cls, doc, index: int):
    """Extracts and cleans author data directly from a raw HAL document."""
    names = doc.get("authFullName_s", [])
    hal_ids = doc.get("authIdHal_s", [])
    person_ids = doc.get("authIdPerson_i", [])
    first_names = doc.get("authFirstName_s", [])
    last_names = doc.get("authLastName_s", [])
    email_domains = doc.get("authEmailDomain_s", [])

    name = names[index] if index < len(names) else "Unknown"
    h_id = (
        str(hal_ids[index])
        if index < len(hal_ids) and hal_ids[index]
        else f"unknown_{name}"
    )
    p_id = (
        int(person_ids[index])
        if index < len(person_ids) and str(person_ids[index]).isdigit()
        else 0
    )
    f_name = first_names[index] if index < len(first_names) else ""
    l_name = last_names[index] if index < len(last_names) else ""
    e_dom = email_domains[index] if index < len(email_domains) else ""

    return cls(
        name=name,
        auth_id_hal=h_id,
        person_id=p_id,
        first_name=f_name,
        last_name=l_name,
        email_domain=e_dom,
    )

  def to_dict(self):
    """Converts the object into a dictionary ready for Neo4j.."""
    return {
        "name": self.name,
        "authIdHal": self.auth_id_hal,
        "personId": self.person_id,
        "firstName": self.first_name,
        "lastName": self.last_name,
        "emailDomain": self.email_domain,
    }