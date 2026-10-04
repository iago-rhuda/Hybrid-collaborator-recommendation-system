import unittest

from connectors.hal_client import HalClient


class HalClientTest(unittest.TestCase):

  def test_adds_sort_parameter_when_requested(self):
    client = HalClient()
    requested_params = []

    def fake_get_json(params):
      requested_params.append(params)
      return {
          "response": {
              "numFound": 1,
              "docs": [{"halId_s": "hal-1"}],
          }
      }

    client._get_json = fake_get_json
    docs = client.fetch_publications(
        query="*:*",
        max_rows=1,
        rows_per_page=1,
        sort="halId_s asc",
    )

    self.assertEqual(docs, [{"halId_s": "hal-1"}])
    self.assertEqual(requested_params[0]["sort"], "halId_s asc")

  def test_preserves_unsorted_default_for_existing_callers(self):
    client = HalClient()
    requested_params = []

    def fake_get_json(params):
      requested_params.append(params)
      return {
          "response": {
              "numFound": 1,
              "docs": [{"halId_s": "hal-1"}],
          }
      }

    client._get_json = fake_get_json
    client.fetch_publications(
        query="*:*",
        max_rows=1,
        rows_per_page=1,
    )

    self.assertNotIn("sort", requested_params[0])


if __name__ == "__main__":
  unittest.main()
