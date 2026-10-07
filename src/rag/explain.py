"""Grounded GraphRAG explanation generation with citation verification.

Implements grounded explanations adhering strictly to PROJECT_SPEC.md §11 & §2.2:
  - Wording rule: 'publication evidence related to X', NEVER 'expert in X'.
  - Uses ONLY supplied graph evidence; does not invent skills, publications, or links.
  - Every claim must cite an evidence ID in brackets: [id].
  - Post-generation verification: any citation of an ID absent from context.valid_ids
    results in rejection of the LLM output and fallback to the deterministic template.
  - Robust fallbacks: network/API failures automatically fall back to template.
  - No Cypher is ever exposed to the LLM.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from rag.context import ExplanationContext

logger = logging.getLogger(__name__)

# Regular expression to extract bracketed citation IDs e.g. [hal-001] or [domain.ai]
_CITATION_REGEX = re.compile(r"\[([a-zA-Z0-9_\.\-]+)\]")


@dataclass(frozen=True)
class ExplanationResult:
  """Result of an explanation generation with verification metadata."""
  person_id: str
  explanation: str
  cited_ids: list[str]
  used_template: bool
  fallback_reason: str | None = None


class ExplanationLLMBackend(Protocol):
  """Interface for LLM explanation generation."""

  def generate_explanation(self, prompt: str) -> str:
    """Generate grounded explanation text."""
    ...


class FakeExplanationLLM:
  """Deterministic stub used in tests."""

  def __init__(self, responses: list[str] | None = None) -> None:
    self._responses = list(responses or [])
    self._call_count = 0

  def generate_explanation(self, prompt: str) -> str:
    if not self._responses:
      return "Default stub explanation citing [hal-001]."
    idx = min(self._call_count, len(self._responses) - 1)
    self._call_count += 1
    return self._responses[idx]


def extract_cited_ids(text: str) -> list[str]:
  """Extract all unique citation IDs enclosed in square brackets from text."""
  matches = _CITATION_REGEX.findall(text)
  seen: set[str] = set()
  result: list[str] = []
  for m in matches:
    if m not in seen:
      seen.add(m)
      result.append(m)
  return result


def generate_template_explanation(context: ExplanationContext) -> str:
  """Generate a deterministic, grounded template explanation from ranking output.

  Guaranteed to cite only existing IDs and respect repository terminology rules.
  """
  parts: list[str] = []

  # Lead sentence with candidate ID
  name = context.candidate_name
  cid = context.candidate_id
  parts.append(
      f"Collaborator {name} [{cid}] is recommended based on graph evidence."
  )

  # Capabilities evidence
  cap_items = [ev for ev in context.evidence_items if ev.kind == "capability"]
  if cap_items:
    cap_cites = [f"[{c.id}] ({c.text})" for c in cap_items[:3]]
    parts.append(
        f"Shows publication evidence related to {', '.join(cap_cites)}."
    )

  # Project evidence
  proj_items = [ev for ev in context.evidence_items if ev.kind == "project"]
  if proj_items:
    p = proj_items[0]
    year_str = f" in {p.year}" if p.year else ""
    parts.append(f"Authored publication [{p.id}] ('{p.text}'){year_str}.")

  # Domain evidence
  dom_items = [ev for ev in context.evidence_items if ev.kind == "domain"]
  if dom_items:
    d = dom_items[0]
    parts.append(f"Publication history aligns with research domain [{d.id}] ({d.text}).")

  # Metrics summary
  comp_score = context.features.get("complementarity", 0.0)
  gap_score = context.features.get("gap_match", 0.0)
  parts.append(
      f"Scored {gap_score:.2f} on capability gap coverage and "
      f"{comp_score:.2f} on team complementarity."
  )

  # Acknowledge missing evidence
  if context.missing_evidence:
    missing_str = " ".join(context.missing_evidence)
    parts.append(f"Caveats: {missing_str}")

  return " ".join(parts)


def build_explanation_prompt(context: ExplanationContext) -> str:
  """Construct prompt instructing LLM according to PROJECT_SPEC §11."""
  return (
      "You are a scientific collaborator recommendation assistant. "
      "Write a concise explanation (2-4 sentences) explaining why this researcher is recommended.\n\n"
      "CRITICAL RULES:\n"
      "1. Use ONLY the supplied evidence from the context below. Do NOT invent publications, "
      "skills, affiliations, or relationships.\n"
      "2. Wording rule: say 'publication evidence related to X', NEVER 'expert in X'.\n"
      "3. Every claim MUST cite the relevant evidence identifier in square brackets, e.g. [id].\n"
      "   Only cite IDs that are explicitly listed in the Grounded Graph Evidence section or the candidate ID.\n"
      "4. Explicitly acknowledge missing evidence or caveats mentioned in the context.\n"
      "5. Do not mention database structures or query languages.\n\n"
      "CONTEXT:\n"
      f"{context.format_for_prompt()}\n\n"
      "EXPLANATION:"
  )


def explain_candidate(
    context: ExplanationContext,
    llm_backend: ExplanationLLMBackend | None = None,
) -> ExplanationResult:
  """Generate a verified explanation for a candidate.

  If an LLM backend is provided:
    1. Prompts LLM for an explanation.
    2. Extracts all cited IDs from the output.
    3. Verifies that EVERY cited ID exists within context.valid_ids.
    4. If any unknown ID is cited, rejects the response and falls back to template.
    5. If LLM raises any exception, falls back to template.
  If no LLM backend is provided:
    Returns the deterministic template explanation directly.

  Args:
    context: ExplanationContext containing facts and valid IDs.
    llm_backend: Optional LLM backend.

  Returns:
    ExplanationResult with verified explanation and citation metadata.
  """
  template_text = generate_template_explanation(context)
  template_cited_ids = extract_cited_ids(template_text)

  if llm_backend is None:
    return ExplanationResult(
        person_id=context.candidate_id,
        explanation=template_text,
        cited_ids=template_cited_ids,
        used_template=True,
        fallback_reason="No LLM backend provided",
    )

  prompt = build_explanation_prompt(context)
  try:
    generated_text = llm_backend.generate_explanation(prompt).strip()
    cited_ids = extract_cited_ids(generated_text)

    # Citation Verification: every cited ID must exist in context.valid_ids
    unknown_ids = [cid for cid in cited_ids if cid not in context.valid_ids]
    if unknown_ids:
      logger.warning(
          "LLM explanation cited unknown IDs %s not in context. Rejecting output.",
          unknown_ids,
      )
      return ExplanationResult(
          person_id=context.candidate_id,
          explanation=template_text,
          cited_ids=template_cited_ids,
          used_template=True,
          fallback_reason=f"Rejected: cited unknown IDs {unknown_ids}",
      )

    return ExplanationResult(
        person_id=context.candidate_id,
        explanation=generated_text,
        cited_ids=cited_ids,
        used_template=False,
        fallback_reason=None,
    )

  except Exception as exc:  # noqa: BLE001
    logger.warning("LLM explanation generation failed: %s. Falling back to template.", exc)
    return ExplanationResult(
        person_id=context.candidate_id,
        explanation=template_text,
        cited_ids=template_cited_ids,
        used_template=True,
        fallback_reason=f"LLM failure: {exc}",
    )
