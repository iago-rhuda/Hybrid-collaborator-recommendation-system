"""Unit tests for the requirements module (Stage B5).

All tests run without live Neo4j or LLM API keys using FakeRequirementLLM,
FakeAdapter, and temporary directory caches.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from capability.resolution import CapabilityRecord, CapabilityResolver
from graph.adapter import ProjectSpec
from graph.fake_adapter import FakeAdapter
from requirements.extraction import (
    FakeRequirementLLM,
    RequirementsExtractor,
)


class TestRequirementsExtraction(unittest.TestCase):
  """Tests for requirements extraction, caching, and fallback."""

  def setUp(self):
    self.adapter = FakeAdapter()
    self.temp_dir = tempfile.TemporaryDirectory()
    self.cache_dir = Path(self.temp_dir.name)

  def tearDown(self):
    self.temp_dir.cleanup()

  def test_extract_from_spec_success_and_caching(self):
    fake_response = {
        "requirements": [
            {"name": "Graph Neural Networks", "importance": 0.9, "source": "extracted"},
            {"name": "Python", "importance": 0.8, "source": "extracted"},
        ],
        "goals": ["Develop graph-based recommender", "Evaluate ranking metrics"],
    }
    llm = FakeRequirementLLM(responses=[fake_response])
    extractor = RequirementsExtractor(
        adapter=self.adapter,
        llm=llm,
        cache_dir=self.cache_dir,
    )

    spec = ProjectSpec(
        title="Graph-based Collaborative Filtering",
        abstract="We explore graph neural networks for team recommendation.",
        keywords=["graph neural networks", "collaborative filtering"],
    )

    reqs = extractor.extract_from_spec(spec)
    self.assertIsNotNone(reqs)
    self.assertEqual(len(reqs.required_capabilities), 2)
    self.assertEqual(len(reqs.goals), 2)
    self.assertEqual(reqs.goals[0], "Develop graph-based recommender")

    # Second extraction should hit the disk cache
    cached_reqs = extractor.extract_from_spec(spec)
    self.assertEqual(len(cached_reqs.required_capabilities), 2)
    self.assertEqual(cached_reqs.required_capabilities[0].name, "Graph Neural Networks")

  def test_extract_with_resolver_mapping(self):
    fake_response = {
        "requirements": [
            {"name": "Transformer Architecture", "importance": 0.9, "source": "extracted"},
            {"name": "Unknown Exotic Technique", "importance": 0.8, "source": "extracted"},
        ],
        "goals": ["Test resolution"],
    }
    resolver = CapabilityResolver(
        existing=[
            CapabilityRecord(
                capability_id="transformer_architecture",
                name="Transformer Architecture",
                aliases=[],
            )
        ]
    )
    llm = FakeRequirementLLM(responses=[fake_response])
    extractor = RequirementsExtractor(
        adapter=self.adapter,
        llm=llm,
        resolver=resolver,
        cache_dir=self.cache_dir,
    )

    reqs = extractor.extract_from_project("hal-001")
    caps = {r.name: r for r in reqs.required_capabilities}

    # Resolved capability gets capability_id
    self.assertEqual(caps["Transformer Architecture"].capability_id, "transformer_architecture")
    self.assertEqual(caps["Transformer Architecture"].importance, 0.9)

    # Unresolved gets None and discounted importance (0.8 * 0.7 = 0.56)
    self.assertIsNone(caps["Unknown Exotic Technique"].capability_id)
    self.assertAlmostEqual(caps["Unknown Exotic Technique"].importance, 0.56, places=2)

  def test_fallback_on_llm_failure(self):
    class FailingLLM(FakeRequirementLLM):
      def extract_requirements(self, prompt: str):
        raise RuntimeError("API timeout or network failure")

    extractor = RequirementsExtractor(
        adapter=self.adapter,
        llm=FailingLLM(),
        cache_dir=self.cache_dir,
    )

    reqs = extractor.extract_from_project("hal-001")
    self.assertIsNotNone(reqs)
    # hal-001 has domains: info.info-ai, info.info-cl, info
    self.assertGreater(len(reqs.domain_ids), 0)
    self.assertIn("info.info-ai", reqs.domain_ids)
    # Falls back to domain-based required capabilities
    self.assertGreater(len(reqs.required_capabilities), 0)


if __name__ == "__main__":
  unittest.main()
