"""FakeAdapter — in-memory adapter backed by static fixtures.

Used in all tests that must run without Neo4j or an LLM key.
Fixtures are loaded from tests/fixtures/dev_projects.json and
tests/fixtures/capabilities.json on first use.

Stage-C methods (find_candidates, get_candidate_evidence, get_coauthor_distance)
raise NotImplementedError — they will be implemented in Stage C.
"""

from __future__ import annotations

import json
from pathlib import Path

from graph.adapter import (
  CandidateRef,
  DomainView,
  EvidenceItem,
  GraphAdapter,
  PersonCapability,
  PersonView,
  ProjectView,
)

# Resolve fixture paths relative to this file
_SRC_DIR = Path(__file__).parent.parent
_PROJECT_ROOT = _SRC_DIR.parent
_FIXTURES_DIR = _PROJECT_ROOT / "tests" / "fixtures"


def _load_json(filename: str) -> list | dict:
  path = _FIXTURES_DIR / filename
  if not path.exists():
    return []
  with open(path, encoding="utf-8") as fh:
    return json.load(fh)


class FakeAdapter:
  """In-memory adapter loaded from fixture JSON files."""

  def __init__(
      self,
      projects: list[dict] | None = None,
      capabilities: list[dict] | None = None,
  ) -> None:
    """Optionally inject fixtures directly (useful in unit tests).

    When *projects* or *capabilities* are None the adapter reads the
    corresponding JSON fixture files from tests/fixtures/.
    """
    raw_projects: list[dict] = (
        projects if projects is not None else _load_json("dev_projects.json")
    )
    raw_caps: list[dict] = (
        capabilities if capabilities is not None
        else _load_json("capabilities.json")
    )

    self._projects: dict[str, ProjectView] = {}
    self._members: dict[str, list[PersonView]] = {}
    self._domains: dict[str, list[DomainView]] = {}
    self._person_projects: dict[str, list[str]] = {}
    self._persons: dict[str, PersonView] = {}

    for raw in raw_projects:
      pid = raw["project_id"]
      self._projects[pid] = ProjectView(
          project_id=pid,
          title=raw.get("title", ""),
          abstract=raw.get("abstract", ""),
          keywords=raw.get("keywords", []),
          year=raw.get("year"),
          doc_type=raw.get("doc_type", ""),
      )
      self._members[pid] = [
          PersonView(
              person_id=m["person_id"],
              full_name=m.get("full_name", ""),
              is_placeholder=m["person_id"].startswith("unknown_"),
          )
          for m in raw.get("members", [])
      ]
      self._domains[pid] = [
          DomainView(
              domain_id=d["domain_id"],
              name=d.get("name", ""),
              parent_ids=d.get("parent_ids", []),
          )
          for d in raw.get("domains", [])
      ]

      # Index person to projects and persons dictionary
      for m in self._members[pid]:
        self._person_projects.setdefault(m.person_id, []).append(pid)
        self._persons[m.person_id] = m

    # person_id -> list[PersonCapability]
    self._capabilities: dict[str, list[PersonCapability]] = {}
    for raw in raw_caps:
      pid = raw["person_id"]
      cap = PersonCapability(
          person_id=pid,
          capability_id=raw["capability_id"],
          name=raw.get("name", ""),
          kind=raw.get("kind", "UNKNOWN"),
          publication_count=raw.get("publication_count", 1),
          evidence_count=raw.get("evidence_count", 1),
          avg_confidence=raw.get("avg_confidence", 0.7),
          last_seen_year=raw.get("last_seen_year"),
          extraction_version=raw.get("extraction_version", "capability-v1"),
      )
      self._capabilities.setdefault(pid, []).append(cap)
      if pid not in self._persons:
        self._persons[pid] = PersonView(
            person_id=pid,
            full_name=raw.get("name", pid),
            is_placeholder=pid.startswith("unknown_"),
        )

  # ------------------------------------------------------------------
  # Fact methods (Stage A / Stage B)
  # ------------------------------------------------------------------

  def get_project(self, project_id: str) -> ProjectView | None:
    return self._projects.get(project_id)

  def iter_projects(
      self,
      limit: int = 100,
      offset: int = 0,
  ) -> list[ProjectView]:
    if limit < 0 or offset < 0:
      raise ValueError("limit and offset must be non-negative")
    items = sorted(self._projects.values(), key=lambda p: p.project_id)
    return items[offset: offset + limit]

  def get_project_members(self, project_id: str) -> list[PersonView]:
    return list(self._members.get(project_id, []))

  def get_project_domains(self, project_id: str) -> list[DomainView]:
    return list(self._domains.get(project_id, []))

  def find_domains_by_keywords(self, keywords: list[str]) -> list[DomainView]:
    """Find domains whose name or ID contains any of the given keywords."""
    kw_lower = [k.strip().lower() for k in keywords if len(k.strip()) >= 2]
    if not kw_lower:
      return []
    matched: dict[str, DomainView] = {}
    for dom_list in self._domains.values():
      for d in dom_list:
        d_name_low = d.name.lower()
        d_id_low = d.domain_id.lower()
        if any(k in d_name_low or k in d_id_low for k in kw_lower):
          matched[d.domain_id] = d
    return list(matched.values())

  def get_person_capabilities(self, person_id: str) -> list[PersonCapability]:
    return list(self._capabilities.get(person_id, []))

  # ------------------------------------------------------------------
  # Stage-C methods
  # ------------------------------------------------------------------

  def find_candidates(
      self,
      domain_ids: list[str],
      capability_ids: list[str],
      exclude_person_ids: list[str],
      limit: int = 200,
  ) -> list[CandidateRef]:
    domain_set = set(domain_ids)
    cap_set = set(capability_ids)
    exclude_set = set(exclude_person_ids)

    all_person_ids = set(self._persons.keys()) | set(self._capabilities.keys())
    candidates: list[CandidateRef] = []

    for pid in sorted(all_person_ids):
      if pid in exclude_set:
        continue

      matched_domains: set[str] = set()
      for proj_id in self._person_projects.get(pid, []):
        for d in self._domains.get(proj_id, []):
          if d.domain_id in domain_set:
            matched_domains.add(d.domain_id)
          for parent in d.parent_ids:
            if parent in domain_set:
              matched_domains.add(parent)

      matched_caps: set[str] = set()
      for c in self._capabilities.get(pid, []):
        if c.capability_id in cap_set:
          matched_caps.add(c.capability_id)

      if matched_domains or matched_caps:
        candidates.append(CandidateRef(
            person_id=pid,
            matched_domain_ids=sorted(matched_domains),
            matched_capability_ids=sorted(matched_caps),
        ))
        if len(candidates) >= limit:
          break

    return candidates

  def get_candidate_evidence(
      self,
      person_id: str,
      domain_ids: list[str],
      capability_ids: list[str],
  ) -> list[EvidenceItem]:
    domain_set = set(domain_ids)
    cap_set = set(capability_ids)
    evidence: list[EvidenceItem] = []
    seen: set[tuple[str, str]] = set()

    for proj_id in self._person_projects.get(person_id, []):
      proj = self._projects.get(proj_id)
      if not proj:
        continue
      proj_domains = self._domains.get(proj_id, [])
      matches_domain = False
      for d in proj_domains:
        d_ids = {d.domain_id} | set(d.parent_ids)
        if (d_ids & domain_set) or not domain_set:
          matches_domain = True
          key = ("domain", d.domain_id)
          if key not in seen:
            seen.add(key)
            evidence.append(EvidenceItem(
                kind="domain",
                id=d.domain_id,
                text=d.name or d.domain_id,
                project_id=proj_id,
                year=proj.year,
            ))

      if matches_domain or not domain_set:
        key = ("project", proj.project_id)
        if key not in seen:
          seen.add(key)
          evidence.append(EvidenceItem(
              kind="project",
              id=proj.project_id,
              text=proj.title,
              project_id=proj.project_id,
              year=proj.year,
          ))

    for c in self._capabilities.get(person_id, []):
      if (c.capability_id in cap_set) or not cap_set:
        key = ("capability", c.capability_id)
        if key not in seen:
          seen.add(key)
          evidence.append(EvidenceItem(
              kind="capability",
              id=c.capability_id,
              text=c.name or c.capability_id,
              project_id=None,
              year=c.last_seen_year,
          ))

    return evidence

  def get_coauthor_distance(
      self,
      person_id: str,
      team_person_ids: list[str],
  ) -> int | None:
    if not team_person_ids:
      return None
    target_set = set(team_person_ids)
    if person_id in target_set:
      return 0

    queue: list[tuple[str, int]] = [(person_id, 0)]
    visited: set[str] = {person_id}

    while queue:
      curr, dist = queue.pop(0)
      if dist >= 3:
        continue

      coauthors: set[str] = set()
      for proj_id in self._person_projects.get(curr, []):
        for m in self._members.get(proj_id, []):
          coauthors.add(m.person_id)

      for nxt in sorted(coauthors):
        if nxt not in visited:
          visited.add(nxt)
          if nxt in target_set:
            return dist + 1
          queue.append((nxt, dist + 1))

    return None


# Verify that FakeAdapter satisfies the GraphAdapter Protocol (runtime check)
def _check_protocol() -> None:
  adapter: GraphAdapter = FakeAdapter(projects=[], capabilities=[])  # type: ignore[assignment]
  _ = adapter  # suppress unused-variable warning


_check_protocol()
