import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import load_graph_mapping, load_neo4j_settings


class ConfigTest(unittest.TestCase):

  def test_loads_the_checked_in_graph_mapping(self):
    mapping = load_graph_mapping()

    self.assertEqual(mapping["nodes"]["project"]["label"], "Project")
    self.assertEqual(mapping["relationships"]["authorship"], "WROTE")

  def test_loads_mapping_from_a_yaml_path(self):
    with tempfile.TemporaryDirectory() as directory:
      mapping_path = Path(directory) / "mapping.yaml"
      mapping_path.write_text(
          "nodes:\n  project:\n    label: Project\n",
          encoding="utf-8",
      )

      self.assertEqual(
          load_graph_mapping(mapping_path),
          {"nodes": {"project": {"label": "Project"}}},
      )

  def test_loads_neo4j_settings_without_exposing_credentials(self):
    environment = {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "test-password",
        "NEO4J_DATABASE": "database-from-env",
    }
    with patch("config.load_dotenv"), patch.dict(os.environ, environment, clear=True):
      settings = load_neo4j_settings()

    self.assertEqual(settings.uri, "bolt://localhost:7687")
    self.assertEqual(settings.user, "neo4j")
    self.assertEqual(settings.password, "test-password")
    self.assertEqual(settings.database, "database-from-env")

  def test_explicit_database_overrides_environment_database(self):
    environment = {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "test-password",
        "NEO4J_DATABASE": "database-from-env",
    }
    with patch("config.load_dotenv"), patch.dict(os.environ, environment, clear=True):
      settings = load_neo4j_settings(database="explicit-database")

    self.assertEqual(settings.database, "explicit-database")

  def test_reports_missing_neo4j_environment_variables(self):
    with patch("config.load_dotenv"), patch.dict(os.environ, {}, clear=True):
      with self.assertRaisesRegex(
          ValueError,
          "NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD",
      ):
        load_neo4j_settings()


if __name__ == "__main__":
  unittest.main()
