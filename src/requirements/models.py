"""Requirements data models.

Defines the plain-Python models for project requirements used throughout Stage B and C.
No external dependencies — all JSON-serialisable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from graph.adapter import (
  ProjectRequirements,
  ProjectSpec,
  RequiredCapability,
)


@dataclass
class RequirementExtractionResult:
  """Raw output from the LLM before domain/capability resolution."""

  project_id: str | None
  raw_requirements: list[dict[str, Any]]  # list of {name, importance, source}
  raw_goals: list[str]
  extraction_version: str
  model: str
  prompt_version: str

  def to_dict(self) -> dict[str, Any]:
    return {
        "project_id": self.project_id,
        "raw_requirements": self.raw_requirements,
        "raw_goals": self.raw_goals,
        "extraction_version": self.extraction_version,
        "model": self.model,
        "prompt_version": self.prompt_version,
    }

  @classmethod
  def from_dict(cls, data: dict[str, Any]) -> "RequirementExtractionResult":
    return cls(
        project_id=data.get("project_id"),
        raw_requirements=data.get("raw_requirements", []),
        raw_goals=data.get("raw_goals", []),
        extraction_version=data.get("extraction_version", ""),
        model=data.get("model", ""),
        prompt_version=data.get("prompt_version", ""),
    )
