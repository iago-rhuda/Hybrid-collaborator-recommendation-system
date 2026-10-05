"""Central configuration loader.

Loads environment variables (via python-dotenv) and YAML config files.
Usage:
  from config import get_config, get_graph_mapping, get_capability_config, get_ranking_config
"""

import os
import yaml
from pathlib import Path
try:
  from dotenv import load_dotenv
  load_dotenv()
except ImportError:
  pass


# Resolve config directory relative to the project root (parent of src/)
_SRC_DIR = Path(__file__).parent
_PROJECT_ROOT = _SRC_DIR.parent
_CONFIG_DIR = _PROJECT_ROOT / "config"


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
      "database": os.getenv("NEO4J_DATABASE", "neo4j"),
  }


def get_graph_mapping() -> dict:
  """Return graph mapping configuration (labels, relationships, properties)."""
  return _load_yaml("graph_mapping.yaml")


def get_capability_config() -> dict:
  """Return capability extraction configuration."""
  return _load_yaml("capability.yaml")


def get_ranking_config() -> dict:
  """Return ranking configuration (weights, limits)."""
  return _load_yaml("ranking.yaml")


def get_llm_config() -> dict:
  """Return LLM provider configuration from environment variables."""
  return {
      "provider": os.getenv("LLM_PROVIDER", "openai"),
      "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
      "api_key": os.getenv("OPENAI_API_KEY", ""),
      "cache_dir": os.getenv(
          "LLM_CACHE_DIR",
          str(_PROJECT_ROOT / "data" / "llm_cache"),
      ),
  }
