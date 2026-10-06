"""Tests for recommender module (Stage C).

Tests coverage for:
  - gaps.py (gap computation, importance weighting, empty gaps)
  - candidates.py (member exclusion, placeholder detection)
  - features.py (all 7 features in [0, 1], missing data, most-similar != best-complement)
  - ranking.py (determinism, stable tie-breaks, weight change effects, contributions)
  - evidence.py (evidence retrieval and grouping)
  - evaluation.py (leave-one-author-out hit@k)
"""

from __future__ import annotations

import unittest

from graph.adapter import (
  DomainView,
  EvidenceItem,
  PersonCapability,
  ProjectRequirements,
  ProjectSpec,
  RequiredCapability,
)
from graph.fake_adapter import FakeAdapter
from recommender.candidates import find_recommendation_candidates
from recommender.engine import recommend_collaborators
from recommender.evaluation import evaluate_leave_one_author_out
from recommender.evidence import extract_evidence_ids, retrieve_candidate_evidence
from recommender.features import (
  compute_complementarity,
  compute_domain_relevance,
  compute_gap_match,
  compute_graph_proximity,
  compute_project_similarity,
  compute_recency,
  compute_semantic_similarity,
)
from recommender.gaps import (
  CapabilityGap,
  compute_capability_gaps,
  get_total_gap_importance,
  get_uncovered_gaps,
)
from recommender.ranking import (
  LinearScorer,
  rank_candidates,
)


class TestGaps(unittest.TestCase):
  """Tests for capability gap analysis."""

  def test_compute_gaps_all_covered(self):
    reqs = ProjectRequirements(
        project_id="p1",
        domain_ids=["info.info-ai"],
        required_capabilities=[
            RequiredCapability(name="NLP", importance=0.9, source="extracted", capability_id="nlp"),
        ],
        goals=["Goal 1"],
        extraction_version="v1",
    )
    team_caps = [
        PersonCapability(
            person_id="alice",
            capability_id="nlp",
            name="NLP",
            kind="DOMAIN",
            publication_count=3,
            evidence_count=4,
            avg_confidence=0.9,
            last_seen_year=2023,
            extraction_version="v1",
        )
    ]
    gaps = compute_capability_gaps(reqs, team_caps)
    self.assertEqual(len(gaps), 1)
    self.assertTrue(gaps[0].is_covered)
    self.assertEqual(gaps[0].covered_by, ["alice"])
    self.assertEqual(len(get_uncovered_gaps(gaps)), 0)

  def test_compute_gaps_uncovered(self):
    reqs = ProjectRequirements(
        project_id="p1",
        domain_ids=["info.info-ai"],
        required_capabilities=[
            RequiredCapability(name="NLP", importance=0.9, source="extracted", capability_id="nlp"),
            RequiredCapability(name="Privacy", importance=0.7, source="extracted", capability_id="diff_privacy"),
        ],
        goals=[],
        extraction_version="v1",
    )
    team_caps = [
        PersonCapability(
            person_id="alice",
            capability_id="nlp",
            name="NLP",
            kind="DOMAIN",
            publication_count=3,
            evidence_count=4,
            avg_confidence=0.9,
            last_seen_year=2023,
            extraction_version="v1",
        )
    ]
    gaps = compute_capability_gaps(reqs, team_caps)
    self.assertEqual(len(gaps), 2)
    uncovered = get_uncovered_gaps(gaps)
    self.assertEqual(len(uncovered), 1)
    self.assertEqual(uncovered[0].capability_id, "diff_privacy")
    self.assertAlmostEqual(get_total_gap_importance(gaps, uncovered_only=True), 0.7)

  def test_empty_requirements(self):
    reqs = ProjectRequirements(
        project_id="p1",
        domain_ids=[],
        required_capabilities=[],
        goals=[],
        extraction_version="v1",
    )
    gaps = compute_capability_gaps(reqs, [])
    self.assertEqual(gaps, [])
    self.assertEqual(get_uncovered_gaps(gaps), [])


class TestCandidates(unittest.TestCase):
  """Tests for candidate generation through adapter."""

  def setUp(self):
    self.adapter = FakeAdapter()

  def test_candidate_generation_excludes_team(self):
    reqs = ProjectRequirements(
        project_id="hal-001",
        domain_ids=["info.info-ai", "info"],
        required_capabilities=[
            RequiredCapability(name="NLP", importance=0.8, source="spec", capability_id="natural_language_processing")
        ],
        goals=[],
        extraction_version="v1",
    )
    team = ["alice-dupont", "bob-martin"]
    candidates = find_recommendation_candidates(self.adapter, reqs, team_person_ids=team)

    cand_ids = [c.person_id for c in candidates]
    self.assertNotIn("alice-dupont", cand_ids)
    self.assertNotIn("bob-martin", cand_ids)
    self.assertGreater(len(candidates), 0)

  def test_placeholder_flagging(self):
    # Inject a fixture containing an unknown_ author
    custom_adapter = FakeAdapter(
        projects=[{
            "project_id": "hal-ph",
            "title": "Placeholder Study",
            "members": [{"person_id": "unknown_john_doe", "full_name": "John Doe"}],
            "domains": [{"domain_id": "info.info-ai", "name": "AI", "parent_ids": []}],
        }],
        capabilities=[],
    )
    reqs = ProjectRequirements(
        project_id="target",
        domain_ids=["info.info-ai"],
        required_capabilities=[],
        goals=[],
        extraction_version="v1",
    )
    candidates = find_recommendation_candidates(custom_adapter, reqs, team_person_ids=[])
    self.assertEqual(len(candidates), 1)
    self.assertTrue(candidates[0].is_placeholder)


class TestFeatures(unittest.TestCase):
  """Tests for the 7 pure recommendation features in [0.0, 1.0]."""

  def test_all_features_within_bounds(self):
    gap = CapabilityGap(capability_id="cap1", name="Cap 1", importance=0.8, source="ext", is_covered=False)
    self.assertTrue(0.0 <= compute_gap_match(["cap1"], [gap]) <= 1.0)
    self.assertTrue(0.0 <= compute_domain_relevance(["d1", "d2"], ["d2", "d3"]) <= 1.0)
    self.assertTrue(0.0 <= compute_semantic_similarity(["cap1"], ["cap1", "cap2"]) <= 1.0)
    self.assertTrue(0.0 <= compute_complementarity(["cap1", "cap2"], ["cap1"]) <= 1.0)
    self.assertTrue(0.0 <= compute_project_similarity(["a", "b"], ["b", "c"]) <= 1.0)
    self.assertTrue(0.0 <= compute_graph_proximity(2, max_hops=3) <= 1.0)
    self.assertTrue(0.0 <= compute_recency(2022, current_year=2024, half_life=3.0) <= 1.0)

  def test_missing_data_handling(self):
    # Gap match with empty gaps
    self.assertEqual(compute_gap_match(["cap1"], []), 0.0)
    # Domain relevance with empty sets
    self.assertEqual(compute_domain_relevance([], []), 0.0)
    # Semantic with empty requirements
    self.assertEqual(compute_semantic_similarity(["cap1"], []), 0.0)
    # Complementarity with empty candidate
    self.assertEqual(compute_complementarity([], ["team_cap"]), 0.0)
    # Project similarity with empty features
    self.assertEqual(compute_project_similarity([], []), 0.0)
    # Graph proximity with None or unreachable
    self.assertEqual(compute_graph_proximity(None), 0.0)
    self.assertEqual(compute_graph_proximity(5, max_hops=3), 0.0)
    # Recency with None year
    self.assertEqual(compute_recency(None), 0.0)

  def test_most_similar_not_best_complement(self):
    """Critical requirement: one case where the most similar person is not the best complement."""
    # Team currently has: ['python', 'ml', 'nlp']
    team_caps = {"python", "ml", "nlp"}
    target_domains = {"info.info-ai"}

    # Person A is almost identical to team: has python, ml, nlp
    person_a_caps = {"python", "ml", "nlp"}
    # Person B complements the team: has python, but also robotics, control_systems
    person_b_caps = {"python", "robotics", "control_systems"}

    # Similarity to team profile
    sim_a = compute_project_similarity(team_caps, person_a_caps)
    sim_b = compute_project_similarity(team_caps, person_b_caps)

    # Person A is much more similar to current team than Person B
    self.assertGreater(sim_a, sim_b)

    # But complementarity penalises redundancy!
    comp_a = compute_complementarity(person_a_caps, team_caps)
    comp_b = compute_complementarity(person_b_caps, team_caps)

    # Person A has 0 complementarity (redundant), while Person B has high complementarity!
    self.assertEqual(comp_a, 0.0)
    self.assertAlmostEqual(comp_b, 2.0 / 3.0)
    self.assertGreater(comp_b, comp_a)


class TestRanking(unittest.TestCase):
  """Tests for ranking determinism and tie-breaking."""

  def test_determinism_and_tie_breaking(self):
    candidates_data = [
        {"person_id": "zack", "features": {"gap_match": 0.5}, "evidence_ids": ["e1"]},
        {"person_id": "adam", "features": {"gap_match": 0.5}, "evidence_ids": ["e2"]},
        {"person_id": "charlie", "features": {"gap_match": 0.8}, "evidence_ids": ["e3"]},
    ]
    weights = {"gap_match": 1.0}
    ranked = rank_candidates(candidates_data, weights=weights)

    # Highest score first
    self.assertEqual(ranked[0].person_id, "charlie")
    # Equal scores tie-broken alphabetically: adam before zack
    self.assertEqual(ranked[1].person_id, "adam")
    self.assertEqual(ranked[2].person_id, "zack")

  def test_weight_change_effect(self):
    candidates_data = [
        {"person_id": "cand_a", "features": {"gap_match": 1.0, "graph": 0.0}},
        {"person_id": "cand_b", "features": {"gap_match": 0.0, "graph": 1.0}},
    ]
    # Weight gap_match higher
    r1 = rank_candidates(candidates_data, weights={"gap_match": 0.9, "graph": 0.1})
    self.assertEqual(r1[0].person_id, "cand_a")

    # Weight graph higher
    r2 = rank_candidates(candidates_data, weights={"gap_match": 0.1, "graph": 0.9})
    self.assertEqual(r2[0].person_id, "cand_b")

  def test_linear_scorer_contributions_sum_to_total(self):
    feats = {"gap_match": 0.8, "domain_relevance": 0.6, "graph": 0.5}
    weights = {"gap_match": 0.5, "domain_relevance": 0.3, "graph": 0.2}
    total, contribs = LinearScorer().score(feats, weights)

    expected = (0.8 * 0.5) + (0.6 * 0.3) + (0.5 * 0.2)
    self.assertAlmostEqual(total, expected)
    self.assertAlmostEqual(sum(contribs.values()), total)


class TestEvidence(unittest.TestCase):
  """Tests for evidence retrieval."""

  def setUp(self):
    self.adapter = FakeAdapter()

  def test_retrieve_and_deduplicate(self):
    ev = retrieve_candidate_evidence(
        self.adapter,
        person_id="carlos-silva",
        domain_ids=["info.info-ai"],
        capability_ids=["graph_neural_network"],
    )
    self.assertGreater(len(ev), 0)
    ids = extract_evidence_ids(ev)
    self.assertEqual(len(ids), len(set(ids)))
    self.assertIn("graph_neural_network", ids)


class TestEvaluation(unittest.TestCase):
  """Tests for leave-one-author-out evaluation."""

  def setUp(self):
    # Create fake adapter with at least one project with 3 authors
    self.adapter = FakeAdapter(
        projects=[
            {
                "project_id": "proj-triad",
                "title": "Three Author Project",
                "members": [
                    {"person_id": "auth1", "full_name": "Author 1"},
                    {"person_id": "auth2", "full_name": "Author 2"},
                    {"person_id": "auth3", "full_name": "Author 3"},
                ],
                "domains": [
                    {"domain_id": "info.info-ai", "name": "AI", "parent_ids": ["info"]},
                ],
            }
        ],
        capabilities=[
            {"person_id": "auth1", "capability_id": "cap1", "name": "Cap 1"},
            {"person_id": "auth2", "capability_id": "cap2", "name": "Cap 2"},
            {"person_id": "auth3", "capability_id": "cap3", "name": "Cap 3"},
        ],
    )

  def test_leave_one_out_executes(self):
    result = evaluate_leave_one_author_out(self.adapter, min_authors=3, top_k=5)
    self.assertEqual(result.total_evaluated, 1)
    self.assertIsInstance(result.hit_at_1, float)
    self.assertIsInstance(result.hit_at_5, float)
    self.assertIsInstance(result.mrr, float)


if __name__ == "__main__":
  unittest.main()
