"""Capability resolution — maps extracted capability names to canonical Capability nodes.

Resolution order (spec §9.3):
  1. Normalize name.
  2. Exact match against existing capability ids.
  3. Alias match against existing capability aliases.
  4. Embedding similarity (optional, via Embedder interface) above a high,
     configurable threshold.
  5. Create a new canonical Capability node.

Abbreviation merging is conservative: the embedding threshold for abbreviations
(short normalized names) is higher than the general threshold.

This module is stateless between calls — it reads the existing capability index
from the repository interface and returns resolution decisions without writing.
Writing is done by repository.py.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from capability.normalization import normalize, to_capability_id
from config import get_capability_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Embedder interface (optional; resolution works without it)
# ---------------------------------------------------------------------------

class Embedder(ABC):
  """Interface for computing embedding similarity between two texts."""

  @abstractmethod
  def similarity(self, text_a: str, text_b: str) -> float:
    """Return cosine similarity in [0, 1] between *text_a* and *text_b*."""
    ...


class NoEmbedder(Embedder):
  """Stub embedder that always returns 0.0 (no embedding similarity)."""

  def similarity(self, text_a: str, text_b: str) -> float:  # noqa: ARG002
    return 0.0


# ---------------------------------------------------------------------------
# In-memory capability index (passed in by the caller / repository)
# ---------------------------------------------------------------------------

@dataclass
class CapabilityRecord:
  """Represents a resolved or to-be-created Capability node."""
  capability_id: str     # deterministic slug
  name: str              # canonical English name
  aliases: list[str]     # surface forms (may include non-English originals)


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

class CapabilityResolver:
  """Resolves capability names to canonical CapabilityRecord instances.

  The resolver is initialised with an in-memory index of existing capabilities.
  It is not thread-safe; create one per extraction batch.

  Args:
    existing:  List of capabilities already in the graph (or empty for first run).
    embedder:  Optional Embedder implementation.  Pass ``NoEmbedder()`` to skip
               embedding-based merging.
  """

  def __init__(
      self,
      existing: list[CapabilityRecord] | None = None,
      embedder: Embedder | None = None,
  ) -> None:
    cfg = get_capability_config()
    res_cfg = cfg.get("resolution", {})
    self._threshold: float = float(
        res_cfg.get("embedding_similarity_threshold", 0.92)
    )
    self._abbr_threshold: float = float(
        res_cfg.get("abbreviation_similarity_threshold", 0.97)
    )

    self._embedder: Embedder = embedder or NoEmbedder()

    # Internal indexes
    self._by_id: dict[str, CapabilityRecord] = {}
    self._alias_index: dict[str, str] = {}  # normalized alias -> capability_id

    for record in (existing or []):
      self._add_to_index(record)

  def _add_to_index(self, record: CapabilityRecord) -> None:
    self._by_id[record.capability_id] = record
    # Index the canonical name and all aliases
    self._alias_index[normalize(record.name)] = record.capability_id
    for alias in record.aliases:
      self._alias_index[normalize(alias)] = record.capability_id

  def _is_abbreviation(self, normalized_name: str) -> bool:
    """Heuristic: an all-uppercase token without spaces is treated as an abbreviation."""
    stripped = normalized_name.strip()
    return len(stripped) <= 6 and " " not in stripped

  def resolve(
      self,
      name: str,
      alias: str | None = None,
  ) -> tuple[CapabilityRecord, bool]:
    """Resolve *name* to a capability record.

    Args:
      name:   Normalized English name from the extracted capability.
      alias:  Original surface form (may be French or non-canonical English).
              Added to the resolved record's aliases if not already present.

    Returns:
      A tuple (record, created) where *created* is True if a new Capability
      node needs to be created in the graph.
    """
    norm = normalize(name)
    cap_id = to_capability_id(name)

    # 1. Exact id match
    if cap_id in self._by_id:
      record = self._by_id[cap_id]
      self._maybe_add_alias(record, alias)
      logger.debug("Exact id match: %r -> %r", name, cap_id)
      return record, False

    # 2. Alias match
    if norm in self._alias_index:
      existing_id = self._alias_index[norm]
      record = self._by_id[existing_id]
      self._maybe_add_alias(record, alias)
      logger.debug("Alias match: %r -> %r", name, existing_id)
      return record, False

    # 3. Embedding similarity (optional)
    if not isinstance(self._embedder, NoEmbedder):
      threshold = self._abbr_threshold if self._is_abbreviation(norm) else self._threshold
      best_record, best_sim = self._best_embedding_match(norm)
      if best_record is not None and best_sim >= threshold:
        self._maybe_add_alias(best_record, alias)
        logger.debug(
            "Embedding match: %r -> %r (sim=%.3f)", name, best_record.capability_id, best_sim
        )
        return best_record, False

    # 4. Create new record
    new_aliases: list[str] = []
    if alias and normalize(alias) != norm:
      new_aliases.append(alias)
    record = CapabilityRecord(
        capability_id=cap_id,
        name=name,
        aliases=new_aliases,
    )
    self._add_to_index(record)
    logger.debug("New capability: %r (id=%r)", name, cap_id)
    return record, True

  def _best_embedding_match(
      self,
      normalized_name: str,
  ) -> tuple[CapabilityRecord | None, float]:
    best_record: CapabilityRecord | None = None
    best_sim = 0.0
    for record in self._by_id.values():
      sim = self._embedder.similarity(normalized_name, normalize(record.name))
      if sim > best_sim:
        best_sim = sim
        best_record = record
    return best_record, best_sim

  def _maybe_add_alias(self, record: CapabilityRecord, alias: str | None) -> None:
    if not alias:
      return
    norm_alias = normalize(alias)
    if norm_alias not in self._alias_index:
      record.aliases.append(alias)
      self._alias_index[norm_alias] = record.capability_id

  @property
  def all_records(self) -> list[CapabilityRecord]:
    """Return all currently known capability records (existing + newly created)."""
    return list(self._by_id.values())
