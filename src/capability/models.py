"""Capability Pydantic models and kind enumeration.

These are used for structured LLM output validation and data transfer.
All LLM-extracted data passes through these models before any persistence.
"""

from __future__ import annotations

import re
import unicodedata
from enum import Enum
from typing import Any


class CapabilityKind(str, Enum):
  """Classification of the kind of capability extracted from a publication."""
  DOMAIN = "DOMAIN"
  METHOD = "METHOD"
  TECHNIQUE = "TECHNIQUE"
  TECHNOLOGY = "TECHNOLOGY"
  TOOL = "TOOL"
  TOPIC = "TOPIC"
  METHODOLOGY = "METHODOLOGY"
  UNKNOWN = "UNKNOWN"

  @classmethod
  def from_string(cls, value: str) -> "CapabilityKind":
    """Parse a string to CapabilityKind, defaulting to UNKNOWN."""
    try:
      return cls(value.upper())
    except (ValueError, AttributeError):
      return cls.UNKNOWN


class ExtractedCapability:
  """A single capability extracted from a publication's text.

  This class is intentionally a plain Python class (not a Pydantic model or
  dataclass) so that the module has no external dependencies.  Validation is
  performed by the extraction layer using ``from_dict``.
  """

  __slots__ = ("name", "normalized_name", "kind", "evidence", "confidence")

  def __init__(
      self,
      name: str,
      normalized_name: str,
      kind: CapabilityKind,
      evidence: str,
      confidence: float,
  ) -> None:
    self.name = name
    self.normalized_name = normalized_name
    self.kind = kind
    self.evidence = evidence
    self.confidence = confidence

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "ExtractedCapability | None":
    """Construct from a raw LLM-output dictionary.

    Returns None if required fields are missing or confidence is not a float.
    """
    name = data.get("name", "").strip()
    if not name:
      return None
    evidence = data.get("evidence", "").strip()
    if not evidence:
      return None
    try:
      confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
      return None
    kind = CapabilityKind.from_string(data.get("kind", "UNKNOWN"))
    normalized_name = data.get("normalized_name", "").strip() or name
    return cls(
        name=name,
        normalized_name=normalized_name,
        kind=kind,
        evidence=evidence,
        confidence=confidence,
    )

  def to_dict(self) -> dict[str, Any]:
    return {
        "name": self.name,
        "normalized_name": self.normalized_name,
        "kind": self.kind.value,
        "evidence": self.evidence,
        "confidence": self.confidence,
    }

  def __repr__(self) -> str:  # pragma: no cover
    return (
        f"ExtractedCapability(name={self.name!r}, kind={self.kind.value}, "
        f"confidence={self.confidence:.2f})"
    )


class CapabilityExtractionResult:
  """Container for all capabilities extracted from a single publication.

  Also holds metadata for caching and provenance tracking.
  """

  __slots__ = (
      "project_id",
      "extraction_version",
      "prompt_version",
      "model",
      "capabilities",
  )

  def __init__(
      self,
      project_id: str,
      extraction_version: str,
      prompt_version: str,
      model: str,
      capabilities: list[ExtractedCapability],
  ) -> None:
    self.project_id = project_id
    self.extraction_version = extraction_version
    self.prompt_version = prompt_version
    self.model = model
    self.capabilities = capabilities

  def to_dict(self) -> dict[str, Any]:
    return {
        "project_id": self.project_id,
        "extraction_version": self.extraction_version,
        "prompt_version": self.prompt_version,
        "model": self.model,
        "capabilities": [c.to_dict() for c in self.capabilities],
    }

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "CapabilityExtractionResult":
    caps = [
        cap
        for raw in data.get("capabilities", [])
        if (cap := ExtractedCapability.from_dict(raw)) is not None
    ]
    return cls(
        project_id=data.get("project_id", ""),
        extraction_version=data.get("extraction_version", ""),
        prompt_version=data.get("prompt_version", ""),
        model=data.get("model", ""),
        capabilities=caps,
    )

  def __repr__(self) -> str:  # pragma: no cover
    return (
        f"CapabilityExtractionResult(project_id={self.project_id!r}, "
        f"n_capabilities={len(self.capabilities)})"
    )
