"""Unit tests for the capability module (Stage B).

All tests run without live Neo4j or LLM API keys, using FakeLLM, FakeAdapter,
and in-memory test doubles.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from capability.aggregation import (
    AuthorCapabilityAggregate,
    CapabilityAggregator,
)
from capability.extraction import (
    CapabilityExtractor,
    FakeLLM,
)
from capability.models import (
    CapabilityExtractionResult,
    CapabilityKind,
    ExtractedCapability,
)
from capability.normalization import (
    is_generic,
    normalize,
    to_capability_id,
)
from capability.repository import CapabilityRepository
from capability.resolution import (
    CapabilityRecord,
    CapabilityResolver,
    Embedder,
    NoEmbedder,
)
from graph.fake_adapter import FakeAdapter


class TestCapabilityNormalization(unittest.TestCase):
  """Tests for normalization, slug id generation, and generic term rejection."""

  def test_normalization_lowercases_and_strips_accents(self):
    self.assertEqual(normalize("Réseaux de Neurones"), "reseaux de neurones")
    self.assertEqual(normalize("  Machine  Learning  "), "machine learning")
    self.assertEqual(normalize("Éléments Finis"), "elements finis")

  def test_to_capability_id_generates_deterministic_slug(self):
    id1 = to_capability_id("Transformer Architecture")
    id2 = to_capability_id("transformer architecture")
    id3 = to_capability_id("Transformer  Architecture!")
    self.assertEqual(id1, "transformer_architecture")
    self.assertEqual(id1, id2)
    self.assertEqual(id1, id3)

  def test_generic_terms_rejection(self):
    stoplist = ["research", "data", "model", "analysis", "system", "study"]
    self.assertTrue(is_generic("research", stoplist))
    self.assertTrue(is_generic("Data Analysis", stoplist))
    self.assertTrue(is_generic("  SYSTEM  ", stoplist))
    self.assertFalse(is_generic("Graph Neural Network", stoplist))
    self.assertFalse(is_generic("Markov Decision Process", stoplist))


class TestCapabilityModels(unittest.TestCase):
  """Tests for capability dataclasses/models."""

  def test_kind_from_string_fallback(self):
    self.assertEqual(CapabilityKind.from_string("method"), CapabilityKind.METHOD)
    self.assertEqual(CapabilityKind.from_string("TECHNIQUE"), CapabilityKind.TECHNIQUE)
    self.assertEqual(CapabilityKind.from_string("non_existent"), CapabilityKind.UNKNOWN)

  def test_extracted_capability_validation(self):
    valid_raw = {
        "name": "Graph Neural Networks",
        "normalized_name": "graph neural networks",
        "kind": "METHOD",
        "evidence": "we employ graph neural networks",
        "confidence": 0.95,
    }
    cap = ExtractedCapability.from_dict(valid_raw)
    self.assertIsNotNone(cap)
    self.assertEqual(cap.name, "Graph Neural Networks")
    self.assertEqual(cap.kind, CapabilityKind.METHOD)
    self.assertEqual(cap.confidence, 0.95)

    # Missing evidence should fail
    invalid_raw = dict(valid_raw)
    invalid_raw["evidence"] = ""
    self.assertIsNone(ExtractedCapability.from_dict(invalid_raw))

    # Invalid confidence should fail
    invalid_conf = dict(valid_raw)
    invalid_conf["confidence"] = "invalid"
    self.assertIsNone(ExtractedCapability.from_dict(invalid_conf))


class TestCapabilityExtraction(unittest.TestCase):
  """Tests for extraction pipeline using FakeLLM and FakeAdapter."""

  def setUp(self):
    self.adapter = FakeAdapter()

  def test_extraction_filters_generic_and_absent_evidence(self):
    fake_responses = [[
        {
            "name": "Transformer Architecture",
            "normalized_name": "transformer architecture",
            "kind": "METHOD",
            "evidence": "transformer",
            "confidence": 0.9,
        },
        {
            "name": "Research",
            "normalized_name": "research",
            "kind": "METHOD",
            "evidence": "research",
            "confidence": 0.9,
        },
        {
            "name": "Quantum Computing",
            "normalized_name": "quantum computing",
            "kind": "METHOD",
            "evidence": "quantum superposition not in abstract",
            "confidence": 0.95,
        },
    ]]
    llm = FakeLLM(responses=fake_responses)
    extractor = CapabilityExtractor(
        adapter=self.adapter,
        llm=llm,
        dry_run=True,
    )

    result = extractor.extract_project("hal-001")
    self.assertIsNotNone(result)
    names = [c.name for c in result.capabilities]

    # "Transformer Architecture" has evidence "transformer" which is in hal-001 abstract/title
    self.assertIn("Transformer Architecture", names)
    # "Research" is in stoplist -> rejected
    self.assertNotIn("Research", names)
    # "Quantum Computing" has evidence not present in input -> rejected
    self.assertNotIn("Quantum Computing", names)


class TestCapabilityResolution(unittest.TestCase):
  """Tests for resolution pipeline: exact -> alias -> embedding -> create."""

  def test_exact_and_alias_matching(self):
    existing = [
        CapabilityRecord(
            capability_id="natural_language_processing",
            name="Natural Language Processing",
            aliases=["NLP", "Traitement Automatique du Langage Naturel"],
        )
    ]
    resolver = CapabilityResolver(existing=existing)

    # 1. Exact ID match
    record1, created1 = resolver.resolve("Natural Language Processing")
    self.assertFalse(created1)
    self.assertEqual(record1.capability_id, "natural_language_processing")

    # 2. Alias match
    record2, created2 = resolver.resolve("NLP")
    self.assertFalse(created2)
    self.assertEqual(record2.capability_id, "natural_language_processing")

    # 3. New capability
    record3, created3 = resolver.resolve("Reinforcement Learning")
    self.assertTrue(created3)
    self.assertEqual(record3.capability_id, "reinforcement_learning")

  def test_embedding_threshold_matching(self):
    existing = [
        CapabilityRecord(
            capability_id="deep_learning",
            name="Deep Learning",
            aliases=[],
        )
    ]

    class MockEmbedder(Embedder):
      def similarity(self, text_a: str, text_b: str) -> float:
        if "deep neural net" in text_a and "deep learning" in text_b:
          return 0.95
        return 0.5

    resolver = CapabilityResolver(existing=existing, embedder=MockEmbedder())
    record, created = resolver.resolve("deep neural net")
    self.assertFalse(created)
    self.assertEqual(record.capability_id, "deep_learning")


class TestCapabilityRepositoryAndCoexistence(unittest.TestCase):
  """Tests repository persistence logic and v1/v2 coexistence."""

  def test_v1_and_v2_coexistence_and_idempotency(self):
    executed_queries: list[tuple[str, dict]] = []

    mock_session = MagicMock()
    def fake_run(query, **params):
      executed_queries.append((query, params))
      return []
    mock_session.run.side_effect = fake_run

    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    repo = CapabilityRepository(driver=mock_driver)

    cap = ExtractedCapability(
        name="Graph Convolutional Network",
        normalized_name="graph convolutional network",
        kind=CapabilityKind.METHOD,
        evidence="GCN",
        confidence=0.9,
    )

    result_v1 = CapabilityExtractionResult(
        project_id="hal-001",
        extraction_version="capability-v1",
        prompt_version="prompt-v1",
        model="gpt-4o-mini",
        capabilities=[cap],
    )
    res_v1 = repo.save_extraction_result(result_v1)
    self.assertEqual(res_v1["created"] + res_v1["merged"], 1)

    result_v2 = CapabilityExtractionResult(
        project_id="hal-001",
        extraction_version="capability-v2",
        prompt_version="prompt-v2",
        model="gpt-4o",
        capabilities=[cap],
    )
    res_v2 = repo.save_extraction_result(result_v2)
    self.assertEqual(res_v2["created"] + res_v2["merged"], 1)

    # Check that both extraction versions were persisted in relationship parameters
    versions = [params.get("ev") for _, params in executed_queries if "ev" in params]
    self.assertIn("capability-v1", versions)
    self.assertIn("capability-v2", versions)


class TestCapabilityAggregation(unittest.TestCase):
  """Tests Author -> Capability evidence aggregation."""

  def test_author_capability_aggregate_metrics(self):
    agg = AuthorCapabilityAggregate(
        person_id="alice-dupont",
        capability_id="transformer_architecture",
        publication_ids=["pub-1", "pub-1", "pub-2"],
        confidences=[0.9, 0.85, 0.95],
        years=[2023, 2023, 2025],
    )
    self.assertEqual(agg.publication_count, 2)
    self.assertEqual(agg.evidence_count, 3)
    self.assertAlmostEqual(agg.avg_extraction_confidence, 0.9, places=2)
    self.assertEqual(agg.first_seen_year, 2023)
    self.assertEqual(agg.last_seen_year, 2025)

    recent = agg.recent_publication_count(reference_year=2026, half_life=3)
    self.assertEqual(recent, 2)

    score = agg.recency_weighted_score(reference_year=2026, half_life=5)
    self.assertGreater(score, 0.5)
    self.assertLessEqual(score, 1.0)


if __name__ == "__main__":
  unittest.main()
