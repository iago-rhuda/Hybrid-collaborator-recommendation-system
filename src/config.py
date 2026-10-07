"""Central configuration loader.

Loads environment variables (via python-dotenv) and YAML config files.
Usage:
  from config import get_config, get_graph_mapping, get_capability_config, get_ranking_config
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
try:
  from dotenv import load_dotenv
  load_dotenv()
except ImportError:
  pass


# Resolve config directory relative to the project root (parent of src/)
_SRC_DIR = Path(__file__).parent
_PROJECT_ROOT = _SRC_DIR.parent
_CONFIG_DIR = _PROJECT_ROOT / "config"
DEFAULT_GRAPH_MAPPING_PATH = _CONFIG_DIR / "graph_mapping.yaml"


@dataclass(frozen=True)
class Neo4jSettings:
  uri: str
  user: str
  password: str = field(repr=False)
  database: str | None = None


def load_neo4j_settings(database: str | None = None) -> Neo4jSettings:
  """Load required Neo4j connection settings from the environment."""
  load_dotenv()
  values = {
      "NEO4J_URI": os.getenv("NEO4J_URI"),
      "NEO4J_USER": os.getenv("NEO4J_USER"),
      "NEO4J_PASSWORD": os.getenv("NEO4J_PASSWORD"),
  }
  missing = [name for name, value in values.items() if not value]
  if missing:
    raise ValueError(
        "Neo4j configuration is missing: " + ", ".join(missing)
    )
  return Neo4jSettings(
      uri=values["NEO4J_URI"],
      user=values["NEO4J_USER"],
      password=values["NEO4J_PASSWORD"],
      database=database if database is not None else os.getenv("NEO4J_DATABASE"),
  )


def load_graph_mapping(
    path: str | Path = DEFAULT_GRAPH_MAPPING_PATH,
) -> dict:
  """Load the graph mapping and expose the logical node mapping aliases."""
  with Path(path).open(encoding="utf-8") as mapping_file:
    mapping = yaml.safe_load(mapping_file)
  if not isinstance(mapping, dict):
    raise ValueError("Graph mapping must contain a top-level mapping")

  labels = mapping.get("labels", {})
  properties = mapping.get("properties", {})
  nodes = mapping.setdefault("nodes", {})
  for logical_name, label in labels.items():
    node = nodes.setdefault(logical_name, {})
    node.setdefault("label", label)
    node.setdefault("key", properties.get(logical_name, {}).get("id"))
    if logical_name in properties:
      node.setdefault("properties", {
          name: value
          for name, value in properties[logical_name].items()
          if name != "id"
      })
  relationships = mapping.get("relationships", {})
  if "wrote" in relationships:
    relationships.setdefault("authorship", relationships["wrote"])
  return mapping


def _load_yaml(filename: str) -> dict:
  """Load a YAML file from the config directory."""
  path = _CONFIG_DIR / filename
  if not path.exists():
    return {}
  with open(path, encoding="utf-8") as fh:
    return yaml.safe_load(fh) or {}


def get_neo4j_config() -> dict:
  """Return Neo4j connection parameters from environment variables."""
  return {
      "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
      "user": os.getenv("NEO4J_USER", "neo4j"),
      "password": os.getenv("NEO4J_PASSWORD", "password"),
      "database": os.getenv("NEO4J_DATABASE", ""),
  }


def get_graph_mapping() -> dict:
  """Return graph mapping configuration (labels, relationships, properties)."""
  return load_graph_mapping()


def get_capability_config() -> dict:
  """Return capability extraction configuration."""
  return _load_yaml("capability.yaml")


def get_ranking_config() -> dict:
  """Return ranking configuration (weights, limits)."""
  return _load_yaml("ranking.yaml")


def get_llm_config() -> dict:
  """Return LLM provider configuration from environment variables."""
  google_key = os.getenv("GOOGLE_AI_STUDIO") or os.getenv("GEMINI_API_KEY", "")
  openai_key = os.getenv("OPENAI_API_KEY", "")
  
  # Auto-detect provider if google key is present
  default_provider = "gemini" if google_key and not openai_key else "openai"
  provider = os.getenv("LLM_PROVIDER", default_provider).lower()

  if provider in ("gemini", "google"):
    default_model = "gemini-2.5-flash"
    api_key = google_key
  else:
    default_model = "gpt-4o-mini"
    api_key = openai_key

  return {
      "provider": provider,
      "model": os.getenv("LLM_MODEL", default_model),
      "api_key": api_key,
      "cache_dir": os.getenv(
          "LLM_CACHE_DIR",
          str(_PROJECT_ROOT / "data" / "llm_cache"),
      ),
  }
