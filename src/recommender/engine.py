"""End-to-end recommendation engine.

Coordinates the recommendation pipeline:
  1. Target project & requirements resolution
  2. Team members & team capabilities retrieval
  3. Gap analysis (required - covered)
  4. Candidate generation via GraphAdapter
  5. Feature computation (all 7 features)
  6. Deterministic ranking & evidence linking
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from graph.adapter import (
  DomainView,
  GraphAdapter,
  PersonCapability,
  ProjectRequirements,
  ProjectSpec,
  ProjectView,
  RequiredCapability,
)
from recommender.candidates import find_recommendation_candidates
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
from recommender.gaps import CapabilityGap, compute_capability_gaps, get_uncovered_gaps
from recommender.ranking import ScoredCandidate, rank_candidates


@dataclass(frozen=True)
class RecommendationResult:
  """Complete recommendation pipeline output."""
  target_project_id: str | None
  target_title: str
  requirements: ProjectRequirements
  gaps: list[CapabilityGap]
  uncovered_gaps: list[CapabilityGap]
  team_member_ids: list[str]
  candidates: list[ScoredCandidate]


def recommend_collaborators(
    adapter: GraphAdapter,
    project_id: str | None = None,
    spec: ProjectSpec | None = None,
    requirements: ProjectRequirements | None = None,
    team_member_ids: Sequence[str] | None = None,
    weights: dict[str, float] | None = None,
    top_k: int = 10,
    candidate_limit: int = 50,
) -> RecommendationResult:
  """Run the end-to-end collaborator recommendation pipeline.

  Args:
    adapter: GraphAdapter implementation (live Neo4j or FakeAdapter).
    project_id: Optional HAL ID of an existing publication.
    spec: Optional free-text ProjectSpec.
    requirements: Optional pre-extracted requirements.
    team_member_ids: Optional override of current team members (e.g. for leave-one-out evaluation).
    weights: Optional custom ranking weights.
    top_k: Number of candidates to return.
    candidate_limit: Max candidates to retrieve before ranking.

  Returns:
    RecommendationResult with ranked candidates, features, weights, contributions,
    evidence IDs, and gap analysis.
  """
  project_view: ProjectView | None = None
  target_title = ""
  effective_team_ids: list[str] = []
  target_domains: list[DomainView] = []

  if project_id:
    project_view = adapter.get_project(project_id)
    if project_view:
      target_title = project_view.title
    if team_member_ids is not None:
      effective_team_ids = list(team_member_ids)
    else:
      members = adapter.get_project_members(project_id)
      effective_team_ids = [m.person_id for m in members]
    target_domains = adapter.get_project_domains(project_id)
  else:
    effective_team_ids = list(team_member_ids or [])
    if spec:
      target_title = spec.title
      if spec.keywords and hasattr(adapter, "find_domains_by_keywords"):
        target_domains = adapter.find_domains_by_keywords(spec.keywords)

  # Build or use requirements
  if requirements is None:
    domain_ids: list[str] = []
    for d in target_domains:
      domain_ids.append(d.domain_id)
      domain_ids.extend(d.parent_ids)
    domain_ids = sorted(list(set(domain_ids)))

    # Derive requirements from spec or project domains
    req_caps: list[RequiredCapability] = []
    if spec and spec.keywords:
      from capability.normalization import to_capability_id
      for kw in spec.keywords:
        cid = to_capability_id(kw)
        req_caps.append(RequiredCapability(
            name=kw,
            importance=0.8,
            source="spec",
            capability_id=cid,
        ))

    requirements = ProjectRequirements(
        project_id=project_id,
        domain_ids=domain_ids,
        required_capabilities=req_caps,
        goals=[],
        extraction_version="fallback-v1",
    )

  # Collect all target domain IDs with ancestors
  all_target_domain_ids: set[str] = set(requirements.domain_ids)
  for d in target_domains:
    all_target_domain_ids.add(d.domain_id)
    all_target_domain_ids.update(d.parent_ids)

  # Retrieve team capabilities
  team_capabilities: list[PersonCapability] = []
  team_cap_ids: set[str] = set()
  for mid in effective_team_ids:
    m_caps = adapter.get_person_capabilities(mid)
    team_capabilities.extend(m_caps)
    for c in m_caps:
      team_cap_ids.add(c.capability_id)

  # Compute capability gaps
  gaps = compute_capability_gaps(requirements, team_capabilities)
  uncovered_gaps = get_uncovered_gaps(gaps)

  # Generate candidates (excludes team members)
  raw_candidates = find_recommendation_candidates(
      adapter=adapter,
      requirements=requirements,
      team_person_ids=effective_team_ids,
      limit=candidate_limit,
  )

  required_cap_ids = {
      c.capability_id
      for c in requirements.required_capabilities
      if c.capability_id is not None
  }

  target_features: set[str] = set(all_target_domain_ids) | set(required_cap_ids)
  if project_view:
    target_features.update(project_view.keywords)

  # Compute features for each candidate
  candidates_data: list[dict] = []
  for cand in raw_candidates:
    pid = cand.person_id
    cand_caps = adapter.get_person_capabilities(pid)
    cand_cap_ids = {c.capability_id for c in cand_caps}

    # Retrieve candidate evidence
    ev_items = retrieve_candidate_evidence(
        adapter,
        pid,
        domain_ids=list(all_target_domain_ids),
        capability_ids=list(required_cap_ids),
    )
    ev_ids = extract_evidence_ids(ev_items)

    # Coauthor distance to team
    coauthor_dist = (
        adapter.get_coauthor_distance(pid, effective_team_ids)
        if effective_team_ids
        else None
    )

    # Recency from latest evidence or capability
    years = [item.year for item in ev_items if item.year is not None]
    cap_years = [c.last_seen_year for c in cand_caps if c.last_seen_year is not None]
    all_years = years + cap_years
    last_year = max(all_years) if all_years else None

    # Candidate profile features for project similarity
    cand_features: set[str] = set(cand.matched_domain_ids) | set(cand_cap_ids)
    for ev in ev_items:
      if ev.kind == "domain":
        cand_features.add(ev.id)
      elif ev.kind == "capability":
        cand_features.add(ev.id)

    # Compute the 7 pure features
    f_gap_match = compute_gap_match(cand_cap_ids, gaps)
    f_domain_relevance = compute_domain_relevance(cand.matched_domain_ids, all_target_domain_ids)
    f_semantic = compute_semantic_similarity(cand_cap_ids, required_cap_ids)
    f_complementarity = compute_complementarity(
        cand_cap_ids,
        team_cap_ids,
        relevant_capability_ids=required_cap_ids if required_cap_ids else None,
    )
    f_project_sim = compute_project_similarity(target_features, cand_features)
    f_graph = compute_graph_proximity(coauthor_dist)
    f_recency = compute_recency(last_year)

    feature_dict = {
        "gap_match": f_gap_match,
        "domain_relevance": f_domain_relevance,
        "semantic": f_semantic,
        "complementarity": f_complementarity,
        "project_similarity": f_project_sim,
        "graph": f_graph,
        "recency": f_recency,
    }

    candidates_data.append({
        "person_id": pid,
        "full_name": cand.full_name,
        "is_placeholder": cand.is_placeholder,
        "features": feature_dict,
        "evidence_ids": ev_ids,
    })

  # Rank candidates deterministically
  ranked = rank_candidates(
      candidates_data=candidates_data,
      weights=weights,
      top_k=top_k,
  )

  return RecommendationResult(
      target_project_id=project_id,
      target_title=target_title,
      requirements=requirements,
      gaps=gaps,
      uncovered_gaps=uncovered_gaps,
      team_member_ids=effective_team_ids,
      candidates=ranked,
  )
