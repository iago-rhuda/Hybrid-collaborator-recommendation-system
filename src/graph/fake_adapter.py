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
from typing import Iterator

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

  # ------------------------------------------------------------------
  # Fact methods (Stage A / Stage B)
  # ------------------------------------------------------------------

  def get_project(self, project_id: str) -> ProjectView | None:
    return self._projects.get(project_id)

  def iter_projects(
      self,
      limit: int = 100,
      offset: int = 0,
  ) -> Iterator[ProjectView]:
    items = sorted(self._projects.values(), key=lambda p: p.project_id)
    yield from items[offset: offset + limit]

  def get_project_members(self, project_id: str) -> list[PersonView]:
    return list(self._members.get(project_id, []))

  def get_project_domains(self, project_id: str) -> list[DomainView]:
    return list(self._domains.get(project_id, []))

  def get_person_capabilities(self, person_id: str) -> list[PersonCapability]:
    return list(self._capabilities.get(person_id, []))

  # ------------------------------------------------------------------
  # Stage-C methods — not yet implemented
  # ------------------------------------------------------------------

  def find_candidates(
      self,
      domain_ids: list[str],
      capability_ids: list[str],
      exclude_person_ids: list[str],
      limit: int = 200,
  ) -> list[CandidateRef]:
    raise NotImplementedError(
        "find_candidates is implemented in Stage C (src/graph/neo4j_adapter.py)"
    )

  def get_candidate_evidence(
      self,
      person_id: str,
      domain_ids: list[str],
      capability_ids: list[str],
  ) -> list[EvidenceItem]:
    raise NotImplementedError(
        "get_candidate_evidence is implemented in Stage C"
    )

  def get_coauthor_distance(
      self,
      person_id: str,
      team_person_ids: list[str],
  ) -> int | None:
    raise NotImplementedError(
        "get_coauthor_distance is implemented in Stage C"
    )


# Verify that FakeAdapter satisfies the GraphAdapter Protocol (runtime check)
def _check_protocol() -> None:
  adapter: GraphAdapter = FakeAdapter(projects=[], capabilities=[])  # type: ignore[assignment]
  _ = adapter  # suppress unused-variable warning


_check_protocol()
