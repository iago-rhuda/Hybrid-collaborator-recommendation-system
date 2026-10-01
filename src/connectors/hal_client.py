import json
from urllib.parse import urlencode
from urllib.request import urlopen

try:
  import requests
except ModuleNotFoundError:
  requests = None


class HalClient:

  def __init__(self):
    self.base_url = "https://api.archives-ouvertes.fr/search/utc/"
    self.query = '("data science" OR "science de données")'
    self.rows_per_page = 100

    self.fields = (
        "halId_s,docid,title_s,subTitle_s,"
        "authFullName_s,authIdPerson_i,authIdHal_s,"
        "authFirstName_s,authLastName_s,authEmailDomain_s,"
        "authORCIDIdExt_s,authGoogleScholarIdExt_s,"
        "authResearcherIdIdExt_s,authIdRefIdExt_s,"
        "structId_i,structName_s,structAcronym_s,structType_s,"
        "structCountry_s,structAddress_s,structCode_s,structValid_s,"
        "structRorIdExt_s,structIdrefIdExt_s,structIsniIdExt_s,"
        "structRnsrIdExt_s,structWikidataIdExt_s,structIsChildOf_fs,"
        "conferenceTitle_s,conferenceStartDate_s,conferenceEndDate_s,"
        "city_s,country_s,"
        "abstract_s,keyword_s,domain_s,primaryDomain_s,domainAllCode_s,"
        "en_domainAllCodeLabel_fs,fr_domainAllCodeLabel_fs,"
        "level0_domain_s,level1_domain_s,level2_domain_s,"
        "docType_s,"
        "language_s,publicationDate_s,producedDate_s,publicationDateY_i,"
        "journalTitle_s,doiId_s,uri_s,openAccess_bool"
    )

  def _get_json(self, params):
    if requests:
      response = requests.get(self.base_url, params=params, timeout=30)
      response.raise_for_status()
      return response.json()

    url = f"{self.base_url}?{urlencode(params)}"
    with urlopen(url, timeout=30) as response:
      return json.loads(response.read().decode("utf-8"))

  def fetch_publications(self, query=None, max_rows=None, rows_per_page=None):
    """Fetches HAL publications using the configured field list."""
    start = 0
    all_docs = []
    query = query or self.query
    rows_per_page = rows_per_page or self.rows_per_page

    print("Consulting the HAL's API for publications...")

    while True:
      rows = rows_per_page
      if max_rows is not None:
        remaining_rows = max_rows - len(all_docs)
        if remaining_rows <= 0:
          break
        rows = min(rows, remaining_rows)

      params = {
          "q": query,
          "fl": self.fields,
          "rows": rows,
          "start": start,
          "wt": "json",
      }

      data = self._get_json(params)["response"]
      num_found = data["numFound"]
      docs = data["docs"]

      if start == 0:
        print(f"Total of publications found in HAL: {num_found}")

      if not docs:
        break

      all_docs.extend(docs)
      start += rows

      if start >= num_found or (max_rows is not None and len(all_docs) >= max_rows):
        break

    return all_docs

  def fetch_data_science_publications(self):
    """Creates an iterator/list with all publications of Data Science from the UTC."""
    return self.fetch_publications()
