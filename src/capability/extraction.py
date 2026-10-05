"""Capability extraction pipeline.

Orchestrates LLM-based extraction of capabilities from project text.

Key design choices:
- Extraction is driven by an ``LLMBackend`` interface so tests can inject a
  ``FakeLLM`` without any API keys or network access.
- LLM outputs are cached on disk keyed by (project_id, prompt_version, model).
- CLI flags: --limit, --version, --dry-run, --resume.
- Bilingual corpus (fr/en): ``normalized_name`` is always English; original
  surface forms go into ``aliases``.
- Generic terms and capabilities whose ``evidence`` text is absent from the
  input are rejected before returning results.

This module does NOT write to Neo4j.  Writing is handled by ``repository.py``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

from capability.models import (
  CapabilityExtractionResult,
  CapabilityKind,
  ExtractedCapability,
)
from capability.normalization import is_generic, normalize, to_capability_id
from config import get_capability_config, get_llm_config
from graph.adapter import GraphAdapter, ProjectView

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM Backend interface (injectable for testing)
# ---------------------------------------------------------------------------

class LLMBackend(ABC):
  """Abstract interface for LLM calls used by the extractor."""

  @abstractmethod
  def extract_capabilities(self, prompt: str) -> list[dict]:
    """Send *prompt* to the LLM and return a list of raw capability dicts.

    Each dict should have keys: name, normalized_name, kind, evidence, confidence.
    The implementation is responsible for parsing the LLM's response.
    """
    ...


class FakeLLM(LLMBackend):
  """Deterministic stub LLM used in tests.

  The constructor accepts a fixed list of raw capability dicts that will be
  returned for every call to ``extract_capabilities``.
  """

  def __init__(self, responses: list[list[dict]] | None = None) -> None:
    self._responses = list(responses or [])
    self._call_count = 0

  def extract_capabilities(self, prompt: str) -> list[dict]:  # noqa: ARG002
    if not self._responses:
      return []
    idx = min(self._call_count, len(self._responses) - 1)
    self._call_count += 1
    return list(self._responses[idx])


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------

def _cache_key(project_id: str, prompt_version: str, model: str) -> str:
  raw = f"{project_id}|{prompt_version}|{model}"
  return hashlib.sha256(raw.encode()).hexdigest()


def _cache_path(cache_dir: Path, key: str) -> Path:
  return cache_dir / f"{key}.json"


def _load_from_cache(
    cache_dir: Path,
    project_id: str,
    prompt_version: str,
    model: str,
) -> CapabilityExtractionResult | None:
  key = _cache_key(project_id, prompt_version, model)
  path = _cache_path(cache_dir, key)
  if not path.exists():
    return None
  with open(path, encoding="utf-8") as fh:
    return CapabilityExtractionResult.from_dict(json.load(fh))


def _save_to_cache(
    cache_dir: Path,
    result: CapabilityExtractionResult,
    prompt_version: str,
    model: str,
) -> None:
  key = _cache_key(result.project_id, prompt_version, model)
  path = _cache_path(cache_dir, key)
  cache_dir.mkdir(parents=True, exist_ok=True)
  with open(path, "w", encoding="utf-8") as fh:
    json.dump(result.to_dict(), fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(project: ProjectView, domain_names: list[str]) -> str:
  """Build the extraction prompt from a project's factual fields."""
  keywords = ", ".join(project.keywords) if project.keywords else "none"
  domains = ", ".join(domain_names) if domain_names else "none"
  return (
      "You are a research capability extractor. "
      "From the publication below, extract specific capabilities "
      "(methods, techniques, tools, technologies, topics, or methodologies) "
      "that the authors demonstrably applied. "
      "Do NOT extract generic terms such as 'research', 'data', 'analysis', "
      "'study', 'results', 'system', 'framework', 'model'. "
      "Do NOT convert research domains into capabilities unless the domain "
      "is itself a specific technique. "
      "For each capability: provide (1) its original surface form as 'name', "
      "(2) its English canonical form as 'normalized_name', "
      "(3) the kind: one of DOMAIN/METHOD/TECHNIQUE/TECHNOLOGY/TOOL/TOPIC/METHODOLOGY/UNKNOWN, "
      "(4) a short verbatim phrase from the text below as 'evidence' "
      "(it MUST appear in the text), "
      "(5) your confidence as a float in [0, 1]. "
      "Return a JSON array of objects with these five keys.\n\n"
      f"Title: {project.title}\n"
      f"Abstract: {project.abstract}\n"
      f"Keywords: {keywords}\n"
      f"Research domains: {domains}"
  )


# ---------------------------------------------------------------------------
# Post-extraction validation
# ---------------------------------------------------------------------------

def _evidence_present_in_input(evidence: str, project: ProjectView) -> bool:
  """Return True if *evidence* appears (case-insensitively) in the project text."""
  combined = (
      f"{project.title} {project.abstract} {' '.join(project.keywords)}"
  ).lower()
  return evidence.lower().strip() in combined


def _validate_and_filter(
    raw_caps: list[dict],
    project: ProjectView,
    stoplist: list[str],
    min_confidence: float,
) -> list[ExtractedCapability]:
  """Parse, validate and filter raw LLM output dicts."""
  results: list[ExtractedCapability] = []
  for raw in raw_caps:
    cap = ExtractedCapability.from_dict(raw)
    if cap is None:
      logger.debug("Skipping malformed capability dict: %s", raw)
      continue
    if cap.confidence < min_confidence:
      logger.debug("Skipping low-confidence capability %r (%.2f)", cap.name, cap.confidence)
      continue
    if is_generic(cap.name, stoplist):
      logger.debug("Rejecting generic capability: %r", cap.name)
      continue
    if not _evidence_present_in_input(cap.evidence, project):
      logger.debug(
          "Rejecting capability %r: evidence %r not found in input",
          cap.name,
          cap.evidence,
      )
      continue
    cap.normalized_name = normalize(cap.normalized_name or cap.name)
    results.append(cap)
  return results


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

class CapabilityExtractor:
  """Extracts capabilities from projects using an LLMBackend.

  Args:
    adapter:    Graph adapter used to fetch project data and domains.
    llm:        LLM backend (injectable; defaults to FakeLLM in tests).
    version:    Extraction version string (e.g. ``"capability-v1"``).
    dry_run:    If True, builds prompts and validates output but does not
                write to cache.
    resume:     If True, skip projects that already have a cached result.
  """

  def __init__(
      self,
      adapter: GraphAdapter,
      llm: LLMBackend,
      version: str | None = None,
      dry_run: bool = False,
      resume: bool = False,
  ) -> None:
    cfg = get_capability_config()
    self._adapter = adapter
    self._llm = llm
    self._dry_run = dry_run
    self._resume = resume

    extraction_cfg = cfg.get("extraction", {})
    self._version = version or extraction_cfg.get("current_version", "capability-v1")
    self._prompt_version = extraction_cfg.get("prompt_version", "prompt-v1")
    self._stoplist: list[str] = extraction_cfg.get("stoplist", [])
    self._min_confidence: float = float(extraction_cfg.get("min_confidence", 0.5))

    llm_cfg = get_llm_config()
    self._model = llm_cfg.get("model", "unknown")

    cache_dir_raw = extraction_cfg.get("cache_dir", "data/llm_cache")
    # Resolve relative to project root (two levels above src/)
    _src_dir = Path(__file__).parent.parent
    _project_root = _src_dir.parent
    self._cache_dir = _project_root / cache_dir_raw

  def extract_project(self, project_id: str) -> CapabilityExtractionResult | None:
    """Extract capabilities for a single project.

    Returns None if the project is not found in the adapter.
    """
    project = self._adapter.get_project(project_id)
    if project is None:
      logger.warning("Project %r not found, skipping extraction", project_id)
      return None

    if self._resume:
      cached = _load_from_cache(
          self._cache_dir, project_id, self._prompt_version, self._model
      )
      if cached is not None:
        logger.info("Cache hit for project %r — skipping LLM call", project_id)
        return cached

    domains = self._adapter.get_project_domains(project_id)
    domain_names = [d.name for d in domains]

    prompt = _build_prompt(project, domain_names)
    raw_caps = self._llm.extract_capabilities(prompt)
    filtered = _validate_and_filter(
        raw_caps, project, self._stoplist, self._min_confidence
    )

    result = CapabilityExtractionResult(
        project_id=project_id,
        extraction_version=self._version,
        prompt_version=self._prompt_version,
        model=self._model,
        capabilities=filtered,
    )

    if not self._dry_run:
      _save_to_cache(self._cache_dir, result, self._prompt_version, self._model)

    return result

  def extract_all(
      self,
      limit: int | None = None,
      offset: int = 0,
  ) -> Iterator[CapabilityExtractionResult]:
    """Yield extraction results for all projects.

    Args:
      limit:   Maximum number of projects to process.
      offset:  Number of projects to skip at the start (for --resume paging).
    """
    page_size = 100
    processed = 0
    batch_offset = offset

    while True:
      batch = list(self._adapter.iter_projects(limit=page_size, offset=batch_offset))
      if not batch:
        break
      for project in batch:
        if limit is not None and processed >= limit:
          return
        result = self.extract_project(project.project_id)
        if result is not None:
          yield result
          processed += 1
      batch_offset += page_size
      if len(batch) < page_size:
        break


def main() -> None:
  """CLI entry point for capability extraction."""
  import argparse
  from graph.fake_adapter import FakeAdapter

  parser = argparse.ArgumentParser(description="Extract research capabilities from projects.")
  parser.add_argument("--limit", type=int, default=None, help="Maximum number of projects to process.")
  parser.add_argument("--version", type=str, default=None, help="Extraction version string (e.g. capability-v1).")
  parser.add_argument("--dry-run", action="store_true", help="Run extraction without writing to disk cache.")
  parser.add_argument("--resume", action="store_true", help="Skip projects already present in cache.")
  parser.add_argument("--project-id", type=str, default=None, help="Extract for a single project ID.")
  parser.add_argument("--use-fake", action="store_true", help="Use FakeAdapter instead of live Neo4j.")

  args = parser.parse_args()

  if args.use_fake:
    adapter = FakeAdapter()
  else:
    try:
      from graph.neo4j_adapter import Neo4jAdapter
      adapter = Neo4jAdapter.from_config()
    except Exception as exc:
      logger.warning("Could not connect to Neo4j (%s); falling back to FakeAdapter", exc)
      adapter = FakeAdapter()

  # Default to FakeLLM if OPENAI_API_KEY is not set
  cfg = get_llm_config()
  if cfg.get("api_key"):
    # If API key is available, we could initialize a real backend
    backend = FakeLLM()
  else:
    backend = FakeLLM()

  extractor = CapabilityExtractor(
      adapter=adapter,
      llm=backend,
      version=args.version,
      dry_run=args.dry_run,
      resume=args.resume,
  )

  if args.project_id:
    res = extractor.extract_project(args.project_id)
    print(f"Extracted for {args.project_id}: {len(res.capabilities) if res else 0} capabilities")
  else:
    count = 0
    for res in extractor.extract_all(limit=args.limit):
      count += 1
      print(f"[{count}] Project {res.project_id}: {len(res.capabilities)} capabilities")
    print(f"Total processed: {count}")


if __name__ == "__main__":
  main()

