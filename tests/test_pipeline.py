import json
import tempfile
import unittest
from pathlib import Path

from pipeline import _load_snapshot_docs, run_pipeline


class FakeNeo4jManager:

  def __init__(self):
    self.constraints_created = False
    self.saved_projects = []

  def setup_constraints(self):
    self.constraints_created = True

  def save_project_data(self, **project_data):
    self.saved_projects.append(project_data)


class PipelineTest(unittest.TestCase):

  def _write_snapshot(self, directory, count=3):
    path = Path(directory) / "records.jsonl"
    with path.open("w", encoding="utf-8") as snapshot_file:
      for index in range(count):
        snapshot_file.write(json.dumps({
            "halId_s": f"hal-{index}",
            "authFullName_s": ["Ada Lovelace", "Grace Hopper"],
            "authIdHal_s": ["grace-hopper", 0],
            "authIdPerson_i": [42, 43],
        }) + "\n")
    return path

  def test_snapshot_reader_obeys_explicit_dev_limit(self):
    with tempfile.TemporaryDirectory() as temporary_directory:
      snapshot_path = self._write_snapshot(temporary_directory)

      docs = _load_snapshot_docs(snapshot_path, limit=2)

    self.assertEqual([doc["halId_s"] for doc in docs], ["hal-0", "hal-1"])

  def test_snapshot_ingest_uses_dev_database_and_fixed_author_ids(self):
    with tempfile.TemporaryDirectory() as temporary_directory:
      snapshot_path = self._write_snapshot(temporary_directory)
      db = FakeNeo4jManager()

      run_pipeline(
          snapshot_path=snapshot_path,
          limit=2,
          database="isolated-dev",
          db_manager=db,
      )

    self.assertTrue(db.constraints_created)
    self.assertEqual(len(db.saved_projects), 2)
    self.assertEqual(
        [project["project"]["halId"] for project in db.saved_projects],
        ["hal-0", "hal-1"],
    )
    self.assertEqual(
        [author["halId"] for author in db.saved_projects[0]["authors"]],
        ["person_42", "grace-hopper"],
    )

  def test_snapshot_ingest_requires_an_explicit_dev_database(self):
    with tempfile.TemporaryDirectory() as temporary_directory:
      snapshot_path = self._write_snapshot(temporary_directory)

      with self.assertRaisesRegex(ValueError, "isolated dev"):
        run_pipeline(
            snapshot_path=snapshot_path,
            limit=1,
            db_manager=FakeNeo4jManager(),
        )

  def test_snapshot_limit_is_bounded_to_dev_subset_size(self):
    with tempfile.TemporaryDirectory() as temporary_directory:
      snapshot_path = self._write_snapshot(temporary_directory)

      with self.assertRaisesRegex(ValueError, "between 1 and 2000"):
        _load_snapshot_docs(snapshot_path, limit=2001)


if __name__ == "__main__":
  unittest.main()
