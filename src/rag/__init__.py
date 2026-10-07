"""GraphRAG package — grounded explanations with evidence citation verification."""

from rag.context import ExplanationContext, build_explanation_context
from rag.explain import (
  ExplanationLLMBackend,
  ExplanationResult,
  FakeExplanationLLM,
  build_explanation_prompt,
  explain_candidate,
  extract_cited_ids,
  generate_template_explanation,
)

__all__ = [
    "ExplanationContext",
    "build_explanation_context",
    "ExplanationResult",
    "ExplanationLLMBackend",
    "FakeExplanationLLM",
    "build_explanation_prompt",
    "generate_template_explanation",
    "extract_cited_ids",
    "explain_candidate",
]
