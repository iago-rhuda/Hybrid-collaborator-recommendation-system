import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv


DEFAULT_GRAPH_MAPPING_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "graph_mapping.yaml"
)


@dataclass(frozen=True)
class Neo4jSettings:
  uri: str
  user: str
  password: str
  database: str | None = None


def load_neo4j_settings(database: str | None = None) -> Neo4jSettings:
  """Load Neo4j connection settings from the environment and optional .env."""
  load_dotenv()
  uri = os.getenv("NEO4J_URI")
  user = os.getenv("NEO4J_USER")
  password = os.getenv("NEO4J_PASSWORD")
  missing = [
      name
      for name, value in (
          ("NEO4J_URI", uri),
          ("NEO4J_USER", user),
          ("NEO4J_PASSWORD", password),
      )
      if not value
  ]
  if missing:
    raise ValueError(
        "Neo4j configuration is missing: " + ", ".join(missing)
    )
  return Neo4jSettings(
      uri=uri,
      user=user,
      password=password,
      database=database or os.getenv("NEO4J_DATABASE"),
  )


def load_graph_mapping(
    path: str | Path = DEFAULT_GRAPH_MAPPING_PATH,
) -> dict:
  """Load the physical graph schema mapping from a YAML file."""
  with Path(path).open("r", encoding="utf-8") as mapping_file:
    mapping = yaml.safe_load(mapping_file)
  if not isinstance(mapping, dict):
    raise ValueError("Graph mapping must contain a top-level mapping")
  return mapping