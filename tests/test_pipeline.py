import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import (
    _load_complete_snapshot,
    _load_snapshot_docs,
    run_pipeline,
)


class FakeNeo4jManager:

  def __init__(self, database=None):
    self.database = database
    self.constraints_created = False
    self.saved_projects = []

  def setup_constraints(self):
    self.constraints_created = True

  def save_project_data(self, **project_data):
    self.saved_projects.append(project_data)

  def close(self):
    pass


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

  def _write_complete_snapshot(self, directory, docs=None, num_found=None):
    snapshot_dir = Path(directory)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    docs = docs or [{
        "halId_s": f"hal-full-{index}",
        "title_s": [f"Publication {index}"],
        "abstract_s": [f"Abstract {index}"],
        "keyword_s": [f"keyword-{index}"],
        "doiId_s": f"10.0/test-{index}",
        "authFullName_s": [f"Author {index}"],
        "authIdHal_s": [f"author-{index}"],
        "primaryDomain_s": "1.1",
        "docType_s": ["ART"],
    } for index in range(2)]
    snapshot_path = snapshot_dir / "records.jsonl"
    snapshot_path.write_text(
        "".join(json.dumps(doc) + "\n" for doc in docs),
        encoding="utf-8",
    )
    manifest = {
        "query": "*:*",
        "numFound": len(docs) if num_found is None else num_found,
        "fetched_count": len(docs),
    }
    (snapshot_dir / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return snapshot_path

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

  def test_full_import_uses_database_from_environment(self):
    environment = {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "test-password",
        "NEO4J_DATABASE": "database-from-env",
    }
    with tempfile.TemporaryDirectory() as temporary_directory:
      snapshot_path = self._write_complete_snapshot(temporary_directory)
      constructed = []

      def manager_factory(database=None):
        manager = FakeNeo4jManager(database)
        constructed.append(manager)
        return manager

      with patch("config.load_dotenv"), patch.dict(
          os.environ,
          environment,
          clear=True,
      ), patch("pipeline.Neo4jManager", side_effect=manager_factory):
        run_pipeline(
            snapshot_path=snapshot_path,
            full_import=True,
            identity_migration_reviewed=True,
        )

    self.assertEqual(constructed[0].database, "database-from-env")
    self.assertTrue(constructed[0].constraints_created)
    self.assertEqual(len(constructed[0].saved_projects), 2)

  def test_full_import_allows_explicit_database_override(self):
    environment = {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "test-password",
        "NEO4J_DATABASE": "database-from-env",
    }
    with tempfile.TemporaryDirectory() as temporary_directory:
      snapshot_path = self._write_complete_snapshot(temporary_directory)
      constructed = []

      def manager_factory(database=None):
        manager = FakeNeo4jManager(database)
        constructed.append(manager)
        return manager

      with patch("config.load_dotenv"), patch.dict(
          os.environ,
          environment,
          clear=True,
      ), patch("pipeline.Neo4jManager", side_effect=manager_factory):
        run_pipeline(
            snapshot_path=snapshot_path,
            database="explicit-database",
            full_import=True,
            identity_migration_reviewed=True,
        )

    self.assertEqual(constructed[0].database, "explicit-database")

  def test_full_import_requires_review_of_author_identity_migration(self):
    with self.assertRaisesRegex(ValueError, "identity-migration-reviewed"):
      run_pipeline(
          full_import=True,
          database="full-import-test",
          db_manager=FakeNeo4jManager(),
      )

  def test_full_import_validates_complete_snapshot_before_ingestion(self):
    with tempfile.TemporaryDirectory() as temporary_directory:
      snapshot_path = self._write_complete_snapshot(temporary_directory)
      db = FakeNeo4jManager()

      run_pipeline(
          snapshot_path=snapshot_path,
          database="full-import-test",
          full_import=True,
          identity_migration_reviewed=True,
          db_manager=db,
      )

    self.assertTrue(db.constraints_created)
    self.assertEqual(len(db.saved_projects), 2)
    self.assertEqual(
        [project["project"]["halId"] for project in db.saved_projects],
        ["hal-full-0", "hal-full-1"],
    )

  def test_full_import_rejects_incomplete_snapshot_before_database_setup(self):
    with tempfile.TemporaryDirectory() as temporary_directory:
      snapshot_path = self._write_complete_snapshot(
          temporary_directory,
          num_found=3,
      )
      db = FakeNeo4jManager()

      with self.assertRaisesRegex(ValueError, "snapshot is incomplete"):
        run_pipeline(
            snapshot_path=snapshot_path,
            database="full-import-test",
            full_import=True,
            identity_migration_reviewed=True,
            db_manager=db,
        )

    self.assertFalse(db.constraints_created)
    self.assertEqual(db.saved_projects, [])

  def test_full_import_rejects_wrong_query_and_missing_manifest(self):
    with tempfile.TemporaryDirectory() as temporary_directory:
      snapshot_path = self._write_complete_snapshot(temporary_directory)
      manifest_path = snapshot_path.parent / "manifest.json"
      manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
      manifest["query"] = "title_t:science"
      manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

      with self.assertRaisesRegex(ValueError, "requires a snapshot for"):
        _load_complete_snapshot(snapshot_path)

      manifest_path.unlink()
      with self.assertRaisesRegex(ValueError, "requires its manifest"):
        _load_complete_snapshot(snapshot_path)

  def test_full_import_rejects_duplicate_hal_ids_before_database_setup(self):
    with tempfile.TemporaryDirectory() as temporary_directory:
      docs = [{
          "halId_s": "duplicate-id",
          "title_s": ["First"],
          "abstract_s": ["First abstract"],
          "keyword_s": ["first"],
          "doiId_s": "10.0/first",
          "authFullName_s": ["Ada Lovelace"],
          "authIdHal_s": ["ada"],
          "primaryDomain_s": "1.1",
          "docType_s": ["ART"],
      }, {
          "halId_s": "duplicate-id",
          "title_s": ["Second"],
          "abstract_s": ["Second abstract"],
          "keyword_s": ["second"],
          "doiId_s": "10.0/second",
          "authFullName_s": ["Grace Hopper"],
          "authIdHal_s": ["grace"],
          "primaryDomain_s": "1.2",
          "docType_s": ["ART"],
      }]
      snapshot_path = self._write_complete_snapshot(temporary_directory, docs)
      db = FakeNeo4jManager()

      with self.assertRaisesRegex(ValueError, "duplicate_hal_id"):
        run_pipeline(
            snapshot_path=snapshot_path,
            database="full-import-test",
            full_import=True,
            identity_migration_reviewed=True,
            db_manager=db,
        )

    self.assertFalse(db.constraints_created)
    self.assertEqual(db.saved_projects, [])

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

  def test_unbounded_direct_fetch_is_rejected_to_prevent_accidental_import(self):
    with self.assertRaisesRegex(ValueError, "--full-import"):
      run_pipeline()


if __name__ == "__main__":
  unittest.main()
