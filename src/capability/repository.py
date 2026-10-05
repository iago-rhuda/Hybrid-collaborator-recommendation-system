"""Capability repository — writes Capability nodes and evidence relationships to Neo4j.

This is the ONLY module that writes inferred data to the graph.
The LLM has no write access.

Written nodes / relationships:
  (:Capability {id, name, kind, aliases})
  (:Project)-[:EVIDENCES_CAPABILITY {inferred, extractionVersion, extractionMethod,
      model, promptVersion, confidence, evidenceText, extractedAt}]->(:Capability)

All writes use MERGE so reruns are idempotent for the same (project, capability,
extractionVersion) triple.  A v2 run will create new EVIDENCES_CAPABILITY edges
and leave v1 edges intact.

The UNIQUE constraint on Capability.id is created by this module (idempotent).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from capability.models import CapabilityExtractionResult, ExtractedCapability
from capability.normalization import to_capability_id
from capability.resolution import CapabilityRecord, CapabilityResolver
from config import get_graph_mapping

logger = logging.getLogger(__name__)


def _now_iso() -> str:
  return datetime.now(timezone.utc).isoformat()


class CapabilityRepository:
  """Writes capability extraction results into the Neo4j graph.

  Args:
    driver:    A live ``neo4j.Driver`` instance.
    database:  Neo4j database name.
    resolver:  CapabilityResolver pre-loaded with existing capabilities.
               If None, a fresh resolver (empty index) is used.
  """

  def __init__(
      self,
      driver,
      database: str = "neo4j",
      resolver: CapabilityResolver | None = None,
  ) -> None:
    self._driver = driver
    self._database = database
    self._resolver = resolver or CapabilityResolver()
    m = get_graph_mapping()
    self._lbl = m.get("labels", {})
    self._rel = m.get("relationships", {})
    self._prop = m.get("properties", {})

  def _run(self, query: str, **params) -> list[dict]:
    with self._driver.session(database=self._database) as session:
      result = session.run(query, **params)
      return [dict(record) for record in result]

  def ensure_constraint(self) -> None:
    """Create UNIQUE constraint on Capability.id (idempotent)."""
    label = self._lbl.get("capability", "Capability")
    prop_id = self._prop.get("capability", {}).get("id", "id")
    self._run(
        f"CREATE CONSTRAINT capability_id IF NOT EXISTS "
        f"FOR (c:{label}) REQUIRE c.{prop_id} IS UNIQUE"
    )
    logger.info("Capability UNIQUE constraint ensured.")

  def _upsert_capability(self, record: CapabilityRecord, kind: str) -> None:
    """MERGE a Capability node; update aliases if it already exists."""
    label = self._lbl.get("capability", "Capability")
    self._run(
        f"""
        MERGE (c:{label} {{id: $cap_id}})
        ON CREATE SET c.name = $name, c.kind = $kind, c.aliases = $aliases
        ON MATCH SET  c.aliases = apoc_or_default(c.aliases, []) + [a IN $aliases WHERE NOT a IN c.aliases]
        """,
        cap_id=record.capability_id,
        name=record.name,
        kind=kind,
        aliases=record.aliases,
    )

  def _upsert_capability_simple(self, record: CapabilityRecord, kind: str) -> None:
    """MERGE a Capability node (compatible with Neo4j without APOC)."""
    label = self._lbl.get("capability", "Capability")
    self._run(
        f"""
        MERGE (c:{label} {{id: $cap_id}})
        ON CREATE SET c.name = $name, c.kind = $kind, c.aliases = $aliases
        """,
        cap_id=record.capability_id,
        name=record.name,
        kind=kind,
        aliases=record.aliases,
    )

  def _upsert_evidence(
      self,
      project_id: str,
      cap: ExtractedCapability,
      record: CapabilityRecord,
      extraction_version: str,
      model: str,
      prompt_version: str,
  ) -> None:
    """MERGE an EVIDENCES_CAPABILITY relationship for (project, capability, version)."""
    plabel = self._lbl.get("project", "Project")
    clabel = self._lbl.get("capability", "Capability")
    pprop = self._prop.get("project", {})
    rel = self._rel.get("evidences_capability", "EVIDENCES_CAPABILITY")
    ep = self._prop.get("evidences_capability", {})

    self._run(
        f"""
        MATCH (p:{plabel} {{{pprop.get('id', 'halId')}: $project_id}})
        MATCH (c:{clabel} {{id: $cap_id}})
        MERGE (p)-[r:{rel} {{{ep.get('extraction_version', 'extractionVersion')}: $ev}}]
              ->(c)
        ON CREATE SET
          r.{ep.get('inferred', 'inferred')} = true,
          r.{ep.get('extraction_method', 'extractionMethod')} = 'llm',
          r.{ep.get('model', 'model')} = $model,
          r.{ep.get('prompt_version', 'promptVersion')} = $prompt_version,
          r.{ep.get('confidence', 'confidence')} = $confidence,
          r.{ep.get('evidence_text', 'evidenceText')} = $evidence_text,
          r.{ep.get('extracted_at', 'extractedAt')} = $extracted_at
        """,
        project_id=project_id,
        cap_id=record.capability_id,
        ev=extraction_version,
        model=model,
        prompt_version=prompt_version,
        confidence=cap.confidence,
        evidence_text=cap.evidence,
        extracted_at=_now_iso(),
    )

  def save_extraction_result(
      self,
      result: CapabilityExtractionResult,
  ) -> dict[str, int]:
    """Persist all capabilities from one extraction result.

    Returns a summary dict: {"created": int, "merged": int, "skipped": int}.
    """
    summary = {"created": 0, "merged": 0, "skipped": 0}

    for cap in result.capabilities:
      try:
        record, created = self._resolver.resolve(
            name=cap.normalized_name,
            alias=cap.name if cap.name != cap.normalized_name else None,
        )
        self._upsert_capability_simple(record, cap.kind.value)
        self._upsert_evidence(
            project_id=result.project_id,
            cap=cap,
            record=record,
            extraction_version=result.extraction_version,
            model=result.model,
            prompt_version=result.prompt_version,
        )
        if created:
          summary["created"] += 1
        else:
          summary["merged"] += 1
      except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to persist capability %r for project %r: %s",
            cap.name,
            result.project_id,
            exc,
        )
        summary["skipped"] += 1

    logger.info(
        "Project %r: +%d created, %d merged, %d skipped",
        result.project_id,
        summary["created"],
        summary["merged"],
        summary["skipped"],
    )
    return summary
