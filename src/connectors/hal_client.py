import requests


class HalClient:

  def __init__(self):
    self.base_url = "https://api.archives-ouvertes.fr/search/utc/"
    self.query = '("data science" OR "science de données")'
    self.rows_per_page = 100

    self.fields = (
        "halId_s,docid,title_s,subTitle_s,"
        "authFullName_s,authIdPerson_i,authIdHal_s,"
        "structName_s,labStructName_s,"
        "abstract_s,keyword_s,domain_s,docType_s,"
        "language_s,producedDate_s,publicationDateY_i,"
        "journalTitle_s,doiId_s,uri_s,openAccess_bool"
    )

  def fetch_data_science_publications(self):
    """Gera um iterador/lista com todas as publicações de Data Science da UTC."""
    start = 0
    all_docs = []

    print("Consultando a API do HAL para publicações de Data Science...")

    while True:
      params = {
          "q": self.query,
          "fl": self.fields,
          "rows": self.rows_per_page,
          "start": start,
          "wt": "json",
      }

      response = requests.get(self.base_url, params=params, timeout=30)
      response.raise_for_status()

      data = response.json()["response"]
      num_found = data["numFound"]
      docs = data["docs"]

      if start == 0:
        print(f"Total de publicações encontradas no HAL: {num_found}")

      if not docs:
        break

      all_docs.extend(docs)
      start += self.rows_per_page

      if start >= num_found:
        break

    return all_docs