"""Stage C Demonstration Script.

Runs an end-to-end demonstration of the collaboration recommendation system:
1. Target project recommendation with capability gap analysis, feature breakdown,
   and grounded explanations.
2. Free-text research project specification recommendation.
3. Leave-one-author-out hit@k evaluation summary.

Usage:
  python demo.py
  python demo.py --live
"""

from __future__ import annotations

import argparse
import sys

from graph.adapter import GraphAdapter, ProjectSpec
from graph.fake_adapter import FakeAdapter
from rag.context import build_explanation_context
from rag.explain import explain_candidate
from recommender.engine import recommend_collaborators
from recommender.evaluation import evaluate_leave_one_author_out


def run_demo(use_live: bool = False) -> None:
  print("=" * 75)
  print(" HYBRID COLLABORATOR RECOMMENDATION SYSTEM — STAGE C DEMO")
  print("=" * 75)

  adapter: GraphAdapter
  project_id: str
  if use_live:
    try:
      from graph.neo4j_adapter import Neo4jAdapter
      adapter = Neo4jAdapter.from_config()
      p = next(adapter.iter_projects(limit=1))
      project_id = p.project_id
      print(f"[*] Connected to live Neo4j database. Using real project: {project_id}")
    except Exception as exc:
      print(f"[!] Could not connect to live Neo4j ({exc}). Using FakeAdapter fixtures.")
      adapter = FakeAdapter()
      project_id = "hal-001"
  else:
    print("[*] Running in reproducible fixture mode with FakeAdapter.")
    adapter = FakeAdapter()
    project_id = "hal-001"

  # -------------------------------------------------------------------------
  # Demo Part 1: Recommend for an existing publication
  # -------------------------------------------------------------------------
  print("\n" + "-" * 75)
  print(f"PART 1: Recommendation for Existing Publication [{project_id}]")
  print("-" * 75)

  res1 = recommend_collaborators(adapter=adapter, project_id=project_id, top_k=3)
  print(f"Title:        {res1.target_title}")
  print(f"Current Team: {', '.join(res1.team_member_ids)}")
  print(f"Gaps identified: {len(res1.uncovered_gaps)} uncovered / {len(res1.gaps)} total")
  for g in res1.gaps:
    cov_str = f"Covered by {', '.join(g.covered_by)}" if g.is_covered else "UNCOVERED GAP"
    print(f"  - {g.name} (importance: {g.importance:.2f}) -> {cov_str}")

  print(f"\nTop {len(res1.candidates)} Recommended Collaborators:")
  for idx, cand in enumerate(res1.candidates, start=1):
    ev_items = adapter.get_candidate_evidence(
        person_id=cand.person_id,
        domain_ids=res1.requirements.domain_ids,
        capability_ids=[
            c.capability_id for c in res1.requirements.required_capabilities if c.capability_id
        ],
    )
    ctx = build_explanation_context(
        candidate=cand,
        evidence_items=ev_items,
        target_title=res1.target_title,
        target_project_id=res1.target_project_id,
        gaps=res1.gaps,
    )
    exp = explain_candidate(ctx)

    print(f"\n  #{idx} {cand.full_name} [{cand.person_id}] (Score: {cand.total_score:.4f})")
    print("     Feature Contributions:")
    for feat, contrib in cand.contributions.items():
      val = cand.features.get(feat, 0.0)
      print(f"       * {feat:20s}: raw={val:.3f} | contrib={contrib:.4f}")
    print(f"     Grounded Explanation: {exp.explanation}")
    print(f"     Verified Cited IDs:   {', '.join(exp.cited_ids)}")

  # -------------------------------------------------------------------------
  # Demo Part 2: Recommend for a new Project Specification
  # -------------------------------------------------------------------------
  print("\n" + "-" * 75)
  print("PART 2: Recommendation for Free-Text Research Specification")
  print("-" * 75)

  spec = ProjectSpec(
      title="Privacy-Preserving Federated Learning for Distributed Healthcare",
      abstract="We design differential privacy protocols for federated deep learning across hospitals.",
      keywords=["federated learning", "differential privacy", "transformer architecture"],
  )
  print(f"Spec Title:    {spec.title}")
  print(f"Spec Keywords: {', '.join(spec.keywords)}")

  # Use FakeAdapter for consistent benchmark demo
  demo_adapter = FakeAdapter() if use_live else adapter
  res2 = recommend_collaborators(adapter=demo_adapter, spec=spec, top_k=2)

  print(f"\nTop {len(res2.candidates)} Collaborators for Spec:")
  for idx, cand in enumerate(res2.candidates, start=1):
    ev_items = demo_adapter.get_candidate_evidence(
        person_id=cand.person_id,
        domain_ids=res2.requirements.domain_ids,
        capability_ids=[
            c.capability_id for c in res2.requirements.required_capabilities if c.capability_id
        ],
    )
    ctx = build_explanation_context(
        candidate=cand,
        evidence_items=ev_items,
        target_title=res2.target_title,
        gaps=res2.gaps,
    )
    exp = explain_candidate(ctx)
    print(f"\n  #{idx} {cand.full_name} [{cand.person_id}] (Score: {cand.total_score:.4f})")
    print(f"     Grounded Explanation: {exp.explanation}")
    print(f"     Evidence IDs:         {', '.join(cand.evidence_ids[:5])}...")

  # -------------------------------------------------------------------------
  # Demo Part 3: Leave-One-Author-Out Evaluation
  # -------------------------------------------------------------------------
  print("\n" + "-" * 75)
  print("PART 3: Leave-One-Author-Out Evaluation Benchmark (FakeAdapter)")
  print("-" * 75)

  eval_res = evaluate_leave_one_author_out(FakeAdapter(), min_authors=2, top_k=5, limit_projects=10)
  print(f"Evaluated Projects: {eval_res.total_evaluated}")
  print(f"Hit@1:  {eval_res.hit_at_1 * 100:.1f}%")
  print(f"Hit@3:  {eval_res.hit_at_3 * 100:.1f}%")
  print(f"Hit@5:  {eval_res.hit_at_5 * 100:.1f}%")
  print(f"MRR:    {eval_res.mrr:.3f}")

  print("\n" + "=" * 75)
  print(" DEMO COMPLETED SUCCESSFULLY")
  print("=" * 75)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description="Stage C Demo")
  parser.add_argument("--live", action="store_true", help="Connect to live Neo4j database")
  args = parser.parse_args()
  run_demo(use_live=args.live)
