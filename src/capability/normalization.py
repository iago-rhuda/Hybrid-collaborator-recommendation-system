"""Capability name normalization utilities.

Provides:
- normalize(name) -> str            # lowercase, accent-stripped, whitespace-collapsed English canonical form
- to_capability_id(name) -> str     # deterministic slug from the normalized name
- is_generic(name, stoplist) -> bool  # True if the name matches a stoplist entry

All functions are pure with no external dependencies.
"""

from __future__ import annotations

import re
import unicodedata


def _strip_accents(text: str) -> str:
  """Remove diacritical marks (accents) from *text* using Unicode NFC decomposition."""
  nfd = unicodedata.normalize("NFD", text)
  return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def normalize(name: str) -> str:
  """Return the normalized English canonical form of a capability name.

  Normalisation steps (order matters):
  1. Strip leading/trailing whitespace.
  2. Lowercase.
  3. Strip diacritical marks (accents).
  4. Replace hyphens and underscores with spaces.
  5. Remove characters that are not alphanumeric or whitespace.
  6. Collapse internal whitespace to single spaces.
  7. Strip again.

  Examples:
    "Graph Neural Network"   -> "graph neural network"
    "Réseaux de Neurones"   -> "reseaux de neurones"
    "NLP (core)"            -> "nlp core"
    "deep--learning"        -> "deep  learning" -> "deep learning"
  """
  text = name.strip().lower()
  text = _strip_accents(text)
  text = text.replace("-", " ").replace("_", " ")
  text = re.sub(r"[^\w\s]", "", text)  # remove punctuation except _ (already removed)
  text = re.sub(r"\s+", " ", text).strip()
  return text


def to_capability_id(name: str) -> str:
  """Return a deterministic slug identifier from a capability name.

  The slug is derived from the normalized form:
  - Spaces replaced by underscores.
  - Result is safe for use as a Neo4j property value and YAML key.

  Examples:
    "Graph Neural Network"  -> "graph_neural_network"
    "Réseaux de Neurones"  -> "reseaux_de_neurones"
    "NLP"                  -> "nlp"
  """
  return normalize(name).replace(" ", "_")


def is_generic(name: str, stoplist: list[str]) -> bool:
  """Return True if *name* normalizes to a term in *stoplist*.

  The stoplist entries are compared after normalization of both sides,
  so case and accents are ignored. Also flags combinations where all words
  are stoplist entries (e.g. 'Data Analysis').

  Args:
    name:      Raw or normalized capability name to test.
    stoplist:  List of generic terms to reject (from config/capability.yaml).

  Returns:
    True when *name* (normalized) matches stoplist entries.
  """
  normalized = normalize(name)
  normalized_stoplist = {normalize(s) for s in stoplist}
  if normalized in normalized_stoplist:
    return True
  words = normalized.split()
  return bool(words) and all(w in normalized_stoplist for w in words)

