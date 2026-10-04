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


if __name__ == "__main__":
  unittest.main()
