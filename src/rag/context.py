"""GraphRAG explanation context builder.

Constructs bounded evidence subgraphs and validated identifier sets for
grounding LLM and template explanations.
No Cypher is exposed to the LLM or explanation layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence, Set

from graph.adapter import EvidenceItem
from recommender.gaps import CapabilityGap
from recommender.ranking import ScoredCandidate


@dataclass(frozen=True)
class ExplanationContext:
  """Bounded context providing facts and valid citation identifiers."""
  candidate_id: str
  candidate_name: str
  is_placeholder: bool
  target_project_id: str | None
  target_title: str
  features: dict[str, float]
  contributions: dict[str, float]
  evidence_items: list[EvidenceItem]
  valid_ids: set[str]
  missing_evidence: list[str] = field(default_factory=list)
  covered_gaps: list[str] = field(default_factory=list)

  def format_for_prompt(self) -> str:
    """Format context into structured markdown for the LLM prompt."""
    lines: list[str] = [
        f"### Candidate: {self.candidate_name} (ID: {self.candidate_id})",
        f"Placeholder ID: {'Yes (unreliable author identity)' if self.is_placeholder else 'No'}",
        f"Target Project: {self.target_title or self.target_project_id or 'New Project Spec'}",
        "",
        "#### Key Feature Scores & Contributions:",
    ]
    for feat, val in self.features.items():
      contrib = self.contributions.get(feat, 0.0)
      lines.append(f"- {feat}: score={val:.3f}, contribution={contrib:.3f}")

    lines.append("")
    lines.append("#### Grounded Graph Evidence (Allowed citation IDs in brackets):")
    if not self.evidence_items:
      lines.append("- No direct graph evidence items found.")
    else:
      for ev in self.evidence_items:
        lines.append(f"- [{ev.id}] ({ev.kind}): {ev.text}" + (f" (Year: {ev.year})" if ev.year else ""))

    lines.append("")
    lines.append("#### Missing Evidence / Caveats:")
    if self.missing_evidence:
      for m in self.missing_evidence:
        lines.append(f"- {m}")
    else:
      lines.append("- None noted.")

    return "\n".join(lines)


def build_explanation_context(
    candidate: ScoredCandidate,
    evidence_items: Sequence[EvidenceItem],
    target_title: str = "",
    target_project_id: str | None = None,
    gaps: Sequence[CapabilityGap] | None = None,
) -> ExplanationContext:
  """Build a strictly bounded ExplanationContext for a scored candidate.

  Args:
    candidate: Scored candidate collaborator.
    evidence_items: Supporting evidence items retrieved from graph.
    target_title: Title of the target research project.
    target_project_id: Optional HAL ID of the target project.
    gaps: Optional capability gaps for the project.

  Returns:
    ExplanationContext with all valid citation IDs and identified missing evidence.
  """
  valid_ids: set[str] = {candidate.person_id}
  if target_project_id:
    valid_ids.add(target_project_id)

  for ev in evidence_items:
    if ev.id:
      valid_ids.add(ev.id)
    if ev.project_id:
      valid_ids.add(ev.project_id)

  # Detect missing evidence
  missing: list[str] = []
  if candidate.is_placeholder:
    missing.append("Candidate identity is a fallback placeholder ('unknown_'); publication history may merge homonyms.")

  if candidate.features.get("graph", 0.0) == 0.0:
    missing.append("No prior co-authorship connection with existing project team members.")

  if candidate.features.get("gap_match", 0.0) == 0.0 and gaps:
    missing.append("No publication evidence directly matching uncovered project capability gaps.")

  if candidate.features.get("recency", 0.0) < 0.4:
    missing.append("Limited recent publication evidence within the last 3-5 years.")

  # Identify covered gaps
  covered: list[str] = []
  if gaps:
    cand_ev_ids = {ev.id for ev in evidence_items}
    for g in gaps:
      if g.capability_id and g.capability_id in cand_ev_ids:
        covered.append(g.name)
        valid_ids.add(g.capability_id)

  return ExplanationContext(
      candidate_id=candidate.person_id,
      candidate_name=candidate.full_name,
      is_placeholder=candidate.is_placeholder,
      target_project_id=target_project_id,
      target_title=target_title,
      features=dict(candidate.features),
      contributions=dict(candidate.contributions),
      evidence_items=list(evidence_items),
      valid_ids=valid_ids,
      missing_evidence=missing,
      covered_gaps=covered,
  )
