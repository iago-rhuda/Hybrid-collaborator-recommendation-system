"""Tests for GraphRAG explanation module (Stage C).

Tests:
  - context.py (context assembly, valid ID sets, missing evidence detection)
  - explain.py:
    - template generation adheres to wording rules and cites valid IDs
    - verification passes when all cited IDs are valid
    - verification rejects invented IDs and triggers fallback to template
    - LLM failure/exception triggers fallback to template
    - missing evidence is acknowledged
    - no Cypher query is exposed to the LLM
"""

from __future__ import annotations

import unittest

from graph.adapter import EvidenceItem
from rag.context import build_explanation_context
from rag.explain import (
  FakeExplanationLLM,
  build_explanation_prompt,
  explain_candidate,
  extract_cited_ids,
  generate_template_explanation,
)
from recommender.ranking import ScoredCandidate


class TestGraphRAG(unittest.TestCase):
  """Tests for GraphRAG context building and grounded explanations."""

  def setUp(self):
    self.candidate = ScoredCandidate(
        person_id="carol-danvers",
        full_name="Carol Danvers",
        total_score=0.85,
        features={
            "gap_match": 0.8,
            "domain_relevance": 0.9,
            "complementarity": 0.7,
            "graph": 0.0,
            "recency": 0.3,
        },
        weights={"gap_match": 0.3, "domain_relevance": 0.2},
        contributions={"gap_match": 0.24, "domain_relevance": 0.18},
        evidence_ids=["hal-042", "quantum_computing"],
        is_placeholder=False,
    )
    self.evidence_items = [
        EvidenceItem(
            kind="project",
            id="hal-042",
            text="Quantum Annealing Applications",
            project_id="hal-042",
            year=2021,
        ),
        EvidenceItem(
            kind="capability",
            id="quantum_computing",
            text="Quantum Computing",
            project_id=None,
            year=2021,
        ),
        EvidenceItem(
            kind="domain",
            id="info.info-ai",
            text="Artificial Intelligence",
            project_id="hal-042",
            year=2021,
        ),
    ]

  def test_context_building_and_valid_ids(self):
    ctx = build_explanation_context(
        candidate=self.candidate,
        evidence_items=self.evidence_items,
        target_title="Hybrid Quantum ML",
        target_project_id="hal-001",
    )
    # Check valid IDs contain all supplied evidence IDs
    self.assertIn("carol-danvers", ctx.valid_ids)
    self.assertIn("hal-042", ctx.valid_ids)
    self.assertIn("quantum_computing", ctx.valid_ids)
    self.assertIn("info.info-ai", ctx.valid_ids)
    self.assertIn("hal-001", ctx.valid_ids)

    # Missing evidence detected because graph=0.0 and recency < 0.4
    self.assertTrue(any("co-authorship" in m.lower() for m in ctx.missing_evidence))
    self.assertTrue(any("recent" in m.lower() for m in ctx.missing_evidence))

  def test_template_explanation_wording_rules(self):
    ctx = build_explanation_context(
        candidate=self.candidate,
        evidence_items=self.evidence_items,
        target_title="Hybrid Quantum ML",
        target_project_id="hal-001",
    )
    template = generate_template_explanation(ctx)

    # Terminology check: must say "publication evidence related to", NEVER "expert in"
    self.assertIn("publication evidence related to", template.lower())
    self.assertNotIn("expert in", template.lower())

    # All cited IDs in template must be valid
    cited = extract_cited_ids(template)
    for cid in cited:
      self.assertIn(cid, ctx.valid_ids)

  def test_valid_llm_explanation_accepted(self):
    ctx = build_explanation_context(
        candidate=self.candidate,
        evidence_items=self.evidence_items,
        target_title="Hybrid Quantum ML",
    )
    # LLM citing valid IDs from the context
    valid_text = (
        "Researcher [carol-danvers] presents publication evidence related to "
        "[quantum_computing] in project [hal-042]. Aligned with domain [info.info-ai]."
    )
    fake_llm = FakeExplanationLLM(responses=[valid_text])
    result = explain_candidate(ctx, llm_backend=fake_llm)

    self.assertFalse(result.used_template)
    self.assertIsNone(result.fallback_reason)
    self.assertEqual(result.explanation, valid_text)
    self.assertIn("carol-danvers", result.cited_ids)
    self.assertIn("quantum_computing", result.cited_ids)

  def test_invented_id_rejected_and_falls_back_to_template(self):
    """Critical requirement: unknown IDs are rejected and trigger fallback."""
    ctx = build_explanation_context(
        candidate=self.candidate,
        evidence_items=self.evidence_items,
        target_title="Hybrid Quantum ML",
    )
    # LLM hallucinates an ungrounded project ID [hal-999-hallucinated]
    hallucinated_text = (
        "Researcher [carol-danvers] has published [hal-999-hallucinated] on quantum theory."
    )
    fake_llm = FakeExplanationLLM(responses=[hallucinated_text])
    result = explain_candidate(ctx, llm_backend=fake_llm)

    # Must reject and fall back to template!
    self.assertTrue(result.used_template)
    self.assertIsNotNone(result.fallback_reason)
    self.assertIn("hal-999-hallucinated", result.fallback_reason)
    # The resulting explanation must NOT be the hallucinated text
    self.assertNotIn("hal-999-hallucinated", result.explanation)

  def test_llm_failure_falls_back_to_template(self):
    ctx = build_explanation_context(
        candidate=self.candidate,
        evidence_items=self.evidence_items,
        target_title="Hybrid Quantum ML",
    )

    class FailingLLM:
      def generate_explanation(self, prompt: str) -> str:
        raise RuntimeError("API connection timed out")

    result = explain_candidate(ctx, llm_backend=FailingLLM())
    self.assertTrue(result.used_template)
    self.assertIsNotNone(result.fallback_reason)
    self.assertIn("timed out", result.fallback_reason)

  def test_no_cypher_exposed_in_prompt(self):
    ctx = build_explanation_context(
        candidate=self.candidate,
        evidence_items=self.evidence_items,
        target_title="Hybrid Quantum ML",
    )
    prompt = build_explanation_prompt(ctx)
    prompt_lower = prompt.lower()
    self.assertNotIn("match (", prompt_lower)
    self.assertNotIn("return ", prompt_lower)
    self.assertNotIn("cypher", prompt_lower)


if __name__ == "__main__":
  unittest.main()
