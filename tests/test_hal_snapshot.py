import json
import tempfile
import unittest
from pathlib import Path

from connectors.hal_snapshot import create_hal_snapshot


class FakeHalClient:

  def __init__(self):
    self.query = "*:*"
    self.rows_per_page = 2
    self.fields = "halId_s,title_s,keyword_s"
    self.last_params = None
    self.sort = None
    self._response = {
        "response": {
            "numFound": 3,
            "docs": [{
                "halId_s": "hal-1",
                "title_s": ["Alpha"],
                "keyword_s": ["AI"],
            }, {
                "halId_s": "hal-2",
                "title_s": ["Beta"],
                "keyword_s": ["Data"],
            }],
        }
    }

  def _get_json(self, params):
    self.last_params = params
    return self._response

  def fetch_publications(
      self,
      query=None,
      max_rows=None,
      rows_per_page=None,
      sort=None,
  ):
    self.sort = sort
    docs = self._response["response"]["docs"]
    if max_rows is not None:
      return docs[:max_rows]
    return docs


class HalSnapshotTest(unittest.TestCase):

  def test_creates_jsonl_snapshot_and_manifest(self):
    client = FakeHalClient()

    with tempfile.TemporaryDirectory() as temp_dir:
      result = create_hal_snapshot(
          query="*:*",
          max_rows=2,
          output_dir=Path(temp_dir),
          rows_per_page=2,
          client=client,
      )

      self.assertTrue(result["jsonl_path"].exists())
      self.assertTrue(result["manifest_path"].exists())

      records = []
      with result["jsonl_path"].open("r", encoding="utf-8") as jsonl_file:
        for line in jsonl_file:
          records.append(json.loads(line))

      self.assertEqual(len(records), 2)
      self.assertEqual(records[0]["halId_s"], "hal-1")
      self.assertEqual(result["manifest"]["numFound"], 3)
      self.assertEqual(result["manifest"]["fetched_count"], 2)
      self.assertEqual(result["manifest"]["query"], "*:*")
      self.assertEqual(result["manifest"]["sort"], "halId_s asc")
      self.assertIn("halId_s", result["manifest"]["requested_fields"])
      self.assertEqual(client.last_params["sort"], "halId_s asc")
      self.assertEqual(client.sort, "halId_s asc")

  def test_pads_author_fields_to_match_author_count(self):
    client = FakeHalClient()
    client.fields = (
        "authFullName_s,authIdHal_s,authIdPerson_i,"
        "authFirstName_s,authLastName_s,authORCIDIdExt_s"
    )
    doc = {
        "halId_s": "hal-authors",
        "authFullName_s": ["Ada Lovelace", "Grace Hopper", "Katherine Johnson"],
        "authIdHal_s": ["ada", "grace"],
        "authIdPerson_i": [42],
        "authFirstName_s": ["Ada", "Grace", "Katherine"],
        "authLastName_s": ["Lovelace"],
    }
    client._response["response"]["docs"] = [doc]

    with tempfile.TemporaryDirectory() as temp_dir:
      result = create_hal_snapshot(
          output_dir=Path(temp_dir),
          client=client,
      )

      with result["jsonl_path"].open("r", encoding="utf-8") as jsonl_file:
        record = json.loads(jsonl_file.readline())

    expected_author_fields = [
        "authFullName_s",
        "authIdHal_s",
        "authIdPerson_i",
        "authFirstName_s",
        "authLastName_s",
        "authORCIDIdExt_s",
    ]
    self.assertTrue(
        all(len(record[field]) == 3 for field in expected_author_fields)
    )
    self.assertEqual(record["authIdHal_s"], ["ada", "grace", 0])
    self.assertEqual(record["authIdPerson_i"], [42, 0, 0])
    self.assertEqual(record["authLastName_s"], ["Lovelace", 0, 0])
    self.assertEqual(record["authORCIDIdExt_s"], [0, 0, 0])
    self.assertEqual(doc["authIdHal_s"], ["ada", "grace"])


if __name__ == "__main__":
  unittest.main()
