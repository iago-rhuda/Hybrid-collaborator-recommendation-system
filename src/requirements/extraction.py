"""Requirements extraction.

Extracts structured project requirements from a ProjectSpec or an existing project
via the graph adapter.

Pipeline:
  1. Build context text from spec (or fetch project from adapter).
  2. Call LLM to extract raw requirements (capability names + importance + source).
  3. Map each raw requirement to ResearchDomain ids and Capability ids using the
     B3 resolver (unresolved requirements are kept by name with lower importance).
  4. Cache the ProjectRequirements as JSON in data/requirements/.
  5. On LLM failure: fall back to domain-only requirements derived from the
     project's existing research domains.

D5 decision: requirements are cached as JSON, not written to Neo4j this week.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from capability.resolution import CapabilityRecord, CapabilityResolver
from config import get_llm_config
from graph.adapter import (
  GraphAdapter,
  ProjectRequirements,
  ProjectSpec,
  RequiredCapability,
)
from requirements.models import RequirementExtractionResult

logger = logging.getLogger(__name__)

# Prompt version for requirements extraction
_PROMPT_VERSION = "req-prompt-v1"
_EXTRACTION_VERSION = "req-v1"


# ---------------------------------------------------------------------------
# LLM backend interface (same pattern as capability extraction)
# ---------------------------------------------------------------------------

class RequirementLLMBackend:
  """Abstract-ish LLM backend for requirements extraction.

  Subclass and override ``extract_requirements`` or inject a stub in tests.
  """

  def extract_requirements(self, prompt: str) -> dict[str, Any]:
    """Return a dict with keys 'requirements' (list) and 'goals' (list of str).

    Each requirement dict should have: name (str), importance (float 0-1),
    source ('extracted').
    """
    raise NotImplementedError


class FakeRequirementLLM(RequirementLLMBackend):
  """Deterministic stub used in tests."""

  def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
    self._responses = list(responses or [])
    self._call_count = 0

  def extract_requirements(self, prompt: str) -> dict[str, Any]:  # noqa: ARG002
    if not self._responses:
      return {"requirements": [], "goals": []}
    idx = min(self._call_count, len(self._responses) - 1)
    self._call_count += 1
    return self._responses[idx]


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_requirements_prompt(
    title: str,
    abstract: str,
    keywords: list[str],
    domain_names: list[str],
) -> str:
  kw_str = ", ".join(keywords) if keywords else "none"
  dom_str = ", ".join(domain_names) if domain_names else "none"
  return (
      "You are a research requirements analyst. "
      "Given the following research project description, identify the specific "
      "capabilities and skills required to carry out or extend this project. "
      "Focus on concrete methods, techniques, tools or technologies — not generic terms. "
      "Do NOT repeat the research domains as requirements unless they represent "
      "a specific skill. "
      "For each requirement, provide: "
      "{'name': str, 'importance': float (0-1), 'source': 'extracted'}. "
      "Also identify 2-4 high-level research goals (plain strings). "
      "Return JSON: {\"requirements\": [...], \"goals\": [...]}.\n\n"
      f"Title: {title}\n"
      f"Abstract: {abstract}\n"
      f"Keywords: {kw_str}\n"
      f"Research domains: {dom_str}"
  )


# ---------------------------------------------------------------------------
# JSON cache helpers
# ---------------------------------------------------------------------------

def _cache_key(project_id: str | None, title: str, prompt_version: str) -> str:
  raw = f"{project_id or ''}|{title}|{prompt_version}"
  return hashlib.sha256(raw.encode()).hexdigest()


def _requirements_cache_path(cache_dir: Path, key: str) -> Path:
  return cache_dir / f"req_{key}.json"


def _load_requirements_from_cache(
    cache_dir: Path,
    key: str,
) -> ProjectRequirements | None:
  path = _requirements_cache_path(cache_dir, key)
  if not path.exists():
    return None
  with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
  req_caps = [
      RequiredCapability(
          name=r["name"],
          importance=r["importance"],
          source=r["source"],
          capability_id=r.get("capability_id"),
      )
      for r in data.get("required_capabilities", [])
  ]
  return ProjectRequirements(
      project_id=data.get("project_id"),
      domain_ids=data.get("domain_ids", []),
      required_capabilities=req_caps,
      goals=data.get("goals", []),
      extraction_version=data.get("extraction_version", ""),
  )


def _save_requirements_to_cache(
    cache_dir: Path,
    key: str,
    requirements: ProjectRequirements,
) -> None:
  cache_dir.mkdir(parents=True, exist_ok=True)
  path = _requirements_cache_path(cache_dir, key)
  data = {
      "project_id": requirements.project_id,
      "domain_ids": requirements.domain_ids,
      "required_capabilities": [
          {
              "name": r.name,
              "importance": r.importance,
              "source": r.source,
              "capability_id": r.capability_id,
          }
          for r in requirements.required_capabilities
      ],
      "goals": requirements.goals,
      "extraction_version": requirements.extraction_version,
  }
  with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Domain-only fallback
# ---------------------------------------------------------------------------

def _domain_fallback(
    project_id: str | None,
    domain_ids: list[str],
    domain_names: dict[str, str],
) -> ProjectRequirements:
  """Build minimal requirements from domain names when LLM fails."""
  logger.warning("LLM failure — falling back to domain-only requirements")
  req_caps = [
      RequiredCapability(
          name=domain_names.get(did, did),
          importance=0.5,
          source="extracted",
          capability_id=None,
      )
      for did in domain_ids
  ]
  return ProjectRequirements(
      project_id=project_id,
      domain_ids=domain_ids,
      required_capabilities=req_caps,
      goals=[],
      extraction_version=_EXTRACTION_VERSION,
  )


# ---------------------------------------------------------------------------
# Resolution helper
# ---------------------------------------------------------------------------

def _resolve_requirements(
    raw_reqs: list[dict[str, Any]],
    resolver: CapabilityResolver | None,
) -> list[RequiredCapability]:
  """Map raw requirements to capability ids via the resolver.

  Unresolved requirements (no resolver or no match) keep capability_id=None
  and receive a reduced importance (×0.7) to signal lower confidence.
  """
  resolved: list[RequiredCapability] = []
  for raw in raw_reqs:
    name = str(raw.get("name", "")).strip()
    if not name:
      continue
    try:
      importance = float(raw.get("importance", 0.5))
    except (TypeError, ValueError):
      importance = 0.5
    source = str(raw.get("source", "extracted"))

    cap_id: str | None = None
    if resolver is not None:
      try:
        record, created = resolver.resolve(name=name)
        if not created:
          cap_id = record.capability_id
      except Exception:  # noqa: BLE001
        cap_id = None

    if cap_id is None:
      importance = max(0.0, importance * 0.7)

    resolved.append(RequiredCapability(
        name=name,
        importance=importance,
        source=source,
        capability_id=cap_id,
    ))
  return resolved


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

class RequirementsExtractor:
  """Extracts and caches project requirements.

  Args:
    adapter:   Graph adapter for fetching existing project data.
    llm:       LLM backend (use FakeRequirementLLM in tests).
    resolver:  Optional capability resolver from Stage B3.
    cache_dir: Override the default cache directory.
  """

  def __init__(
      self,
      adapter: GraphAdapter,
      llm: RequirementLLMBackend,
      resolver: CapabilityResolver | None = None,
      cache_dir: Path | None = None,
  ) -> None:
    self._adapter = adapter
    self._llm = llm
    self._resolver = resolver

    llm_cfg = get_llm_config()
    self._model = llm_cfg.get("model", "unknown")

    if cache_dir is not None:
      self._cache_dir = cache_dir
    else:
      _src_dir = Path(__file__).parent.parent
      _project_root = _src_dir.parent
      self._cache_dir = _project_root / "data" / "requirements"

  def _get_project_context(
      self,
      project_id: str,
  ) -> tuple[str, str, list[str], list[str], dict[str, str]]:
    """Fetch title, abstract, keywords, domain_ids, domain_names for an existing project."""
    project = self._adapter.get_project(project_id)
    if project is None:
      return "", "", [], [], {}
    domains = self._adapter.get_project_domains(project_id)
    domain_ids = [d.domain_id for d in domains]
    domain_names = {d.domain_id: d.name for d in domains}
    return (
        project.title,
        project.abstract,
        project.keywords,
        domain_ids,
        domain_names,
    )

  def _spec_context(
      self,
      spec: ProjectSpec,
  ) -> tuple[str, str, list[str], list[str], dict[str, str]]:
    """Derive context from a free-text ProjectSpec (no adapter call needed)."""
    return spec.title, spec.abstract, spec.keywords, [], {}

  def extract_from_spec(self, spec: ProjectSpec) -> ProjectRequirements:
    """Extract requirements from a free-text project specification."""
    return self._extract(
        project_id=None,
        title=spec.title,
        abstract=spec.abstract,
        keywords=spec.keywords,
        domain_ids=[],
        domain_names={},
    )

  def extract_from_project(self, project_id: str) -> ProjectRequirements:
    """Extract requirements for an existing project by its halId."""
    title, abstract, keywords, domain_ids, domain_names = (
        self._get_project_context(project_id)
    )
    return self._extract(
        project_id=project_id,
        title=title,
        abstract=abstract,
        keywords=keywords,
        domain_ids=domain_ids,
        domain_names=domain_names,
    )

  def _extract(
      self,
      project_id: str | None,
      title: str,
      abstract: str,
      keywords: list[str],
      domain_ids: list[str],
      domain_names: dict[str, str],
  ) -> ProjectRequirements:
    # Check cache
    cache_key = _cache_key(project_id, title, _PROMPT_VERSION)
    cached = _load_requirements_from_cache(self._cache_dir, cache_key)
    if cached is not None:
      logger.info("Requirements cache hit for project %r", project_id)
      return cached

    # Build prompt and call LLM
    domain_name_list = list(domain_names.values())
    prompt = _build_requirements_prompt(title, abstract, keywords, domain_name_list)

    try:
      llm_output = self._llm.extract_requirements(prompt)
      raw_reqs: list[dict[str, Any]] = llm_output.get("requirements", [])
      raw_goals: list[str] = [str(g) for g in llm_output.get("goals", [])]
      _validate_structured_output(raw_reqs, raw_goals)
    except Exception as exc:  # noqa: BLE001
      logger.warning("LLM requirements extraction failed: %s", exc)
      result = _domain_fallback(project_id, domain_ids, domain_names)
      _save_requirements_to_cache(self._cache_dir, cache_key, result)
      return result

    resolved = _resolve_requirements(raw_reqs, self._resolver)

    # Filter generic/unsupported (zero importance or empty name)
    resolved = [r for r in resolved if r.name and r.importance > 0]

    result = ProjectRequirements(
        project_id=project_id,
        domain_ids=domain_ids,
        required_capabilities=resolved,
        goals=raw_goals,
        extraction_version=_EXTRACTION_VERSION,
    )
    _save_requirements_to_cache(self._cache_dir, cache_key, result)
    return result


def _validate_structured_output(
    raw_reqs: list[dict[str, Any]],
    raw_goals: list[str],
) -> None:
  """Raise ValueError if the LLM output doesn't meet basic structural requirements."""
  if not isinstance(raw_reqs, list):
    raise ValueError("'requirements' must be a list")
  if not isinstance(raw_goals, list):
    raise ValueError("'goals' must be a list")
  for req in raw_reqs:
    if not isinstance(req, dict):
      raise ValueError(f"Each requirement must be a dict, got {type(req)}")
    name = req.get("name", "")
    if not name or not isinstance(name, str):
      raise ValueError(f"Requirement missing 'name': {req}")
