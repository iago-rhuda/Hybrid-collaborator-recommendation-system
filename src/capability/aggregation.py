"""Author capability aggregation.

Aggregates per-project EVIDENCES_CAPABILITY relationships into per-author
HAS_CAPABILITY relationships with recency weighting and provenance metadata.

This module reads data via the GraphAdapter and writes HAS_CAPABILITY via a
passed Neo4j driver (not via the adapter — writes are always direct to Neo4j).

Spec §9.5 requirements implemented here:
- publicationCount, evidenceCount, avgExtractionConfidence
- recentPublicationCount (within half-life window), firstSeenYear, lastSeenYear
- Recency-weighted score (exponential decay)
- Skip / flag unknown_ authors (configurable prefix)
- Minimum evidence count gate (from config)
- Extraction confidence kept separate from author-level score
- v1 and v2 run independently (aggregationVersion in the relationship key)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from config import get_capability_config, get_graph_mapping

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AuthorCapabilityAggregate:
  """Accumulated evidence for one (author, capability) pair."""
  person_id: str
  capability_id: str
  publication_ids: list[str] = field(default_factory=list)
  confidences: list[float] = field(default_factory=list)
  years: list[int | None] = field(default_factory=list)

  @property
  def publication_count(self) -> int:
    return len(set(self.publication_ids))

  @property
  def evidence_count(self) -> int:
    return len(self.confidences)

  @property
  def avg_extraction_confidence(self) -> float:
    if not self.confidences:
      return 0.0
    return sum(self.confidences) / len(self.confidences)

  @property
  def first_seen_year(self) -> int | None:
    valid = [y for y in self.years if y is not None]
    return min(valid) if valid else None

  @property
  def last_seen_year(self) -> int | None:
    valid = [y for y in self.years if y is not None]
    return max(valid) if valid else None

  def recent_publication_count(self, reference_year: int, half_life: float) -> int:
    """Count publications within one half-life of the reference year."""
    cutoff = reference_year - half_life
    unique_recent: set[str] = set()
    for pub_id, year in zip(self.publication_ids, self.years):
      if year is not None and year >= cutoff:
        unique_recent.add(pub_id)
    return len(unique_recent)

  def recency_weighted_score(self, reference_year: int, half_life: float) -> float:
    """Compute a recency-weighted score in [0, 1].

    Each publication contributes weight = 0.5 ** ((reference_year - year) / half_life).
    Publications with no year receive weight 0.
    The score is normalised by the maximum possible weight (all in reference_year).
    """
    unique_pubs: dict[str, int | None] = {}
    for pub_id, year in zip(self.publication_ids, self.years):
      if pub_id not in unique_pubs:
        unique_pubs[pub_id] = year

    total_weight = 0.0
    for year in unique_pubs.values():
      if year is None:
        continue
      age = max(0, reference_year - year)
      total_weight += math.pow(0.5, age / half_life)

    max_weight = float(len(unique_pubs))
    if max_weight == 0:
      return 0.0
    return min(1.0, total_weight / max_weight)


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

class CapabilityAggregator:
  """Computes HAS_CAPABILITY relationship properties from evidence in the graph.

  Args:
    driver:           Live Neo4j driver.
    database:         Neo4j database name.
    extraction_version: The extraction version to aggregate (e.g. "capability-v1").
    aggregation_version: The aggregation run version written to the relationship.
    reference_year:   Year used for recency calculations (defaults to current year).
  """

  def __init__(
      self,
      driver,
      database: str = "neo4j",
      extraction_version: str | None = None,
      aggregation_version: str | None = None,
      reference_year: int | None = None,
  ) -> None:
    cfg = get_capability_config()
    agg_cfg = cfg.get("aggregation", {})
    ext_cfg = cfg.get("extraction", {})

    self._driver = driver
    self._database = database
    self._extraction_version = extraction_version or ext_cfg.get(
        "current_version", "capability-v1"
    )
    self._aggregation_version = aggregation_version or agg_cfg.get(
        "current_version", "agg-v1"
    )
    self._min_evidence_count: int = int(agg_cfg.get("min_evidence_count", 2))
    self._half_life: float = float(agg_cfg.get("recency_half_life_years", 5))
    self._skip_prefix: str = agg_cfg.get("skip_prefix", "unknown_")

    import datetime
    self._reference_year: int = reference_year or datetime.datetime.now().year

    m = get_graph_mapping()
    self._lbl = m.get("labels", {})
    self._rel = m.get("relationships", {})
    self._prop = m.get("properties", {})

  def _run(self, query: str, **params) -> list[dict]:
    with self._driver.session(database=self._database) as session:
      result = session.run(query, **params)
      return [dict(record) for record in result]

  def _fetch_evidence(self) -> list[dict[str, Any]]:
    """Fetch all EVIDENCES_CAPABILITY records for the target extraction version."""
    alabel = self._lbl.get("author", "Author")
    plabel = self._lbl.get("project", "Project")
    clabel = self._lbl.get("capability", "Capability")
    wrote_rel = self._rel.get("wrote", "WROTE")
    ev_rel = self._rel.get("evidences_capability", "EVIDENCES_CAPABILITY")
    aprop = self._prop.get("author", {})
    pprop = self._prop.get("project", {})
    cprop = self._prop.get("capability", {})
    ep = self._prop.get("evidences_capability", {})

    a_id = aprop.get("id", "halId")
    p_id = pprop.get("id", "halId")
    p_year = pprop.get("year", "publicationYear")
    c_id = cprop.get("id", "id")
    ev_version = ep.get("extraction_version", "extractionVersion")
    ev_conf = ep.get("confidence", "confidence")

    return self._run(
        f"""
        MATCH (a:{alabel})-[:{wrote_rel}]->(p:{plabel})
              -[ev:{ev_rel} {{{ev_version}: $extraction_version}}]->(c:{clabel})
        RETURN
          a.{a_id}           AS person_id,
          p.{p_id}           AS publication_id,
          p.{p_year}         AS year,
          c.{c_id}           AS capability_id,
          ev.{ev_conf}       AS confidence
        """,
        extraction_version=self._extraction_version,
    )

  def _build_aggregates(
      self,
      rows: list[dict[str, Any]],
  ) -> dict[tuple[str, str], AuthorCapabilityAggregate]:
    aggregates: dict[tuple[str, str], AuthorCapabilityAggregate] = {}
    for row in rows:
      person_id = row["person_id"]
      cap_id = row["capability_id"]

      if person_id.startswith(self._skip_prefix):
        logger.debug("Skipping placeholder author: %r", person_id)
        continue

      key = (person_id, cap_id)
      if key not in aggregates:
        aggregates[key] = AuthorCapabilityAggregate(
            person_id=person_id,
            capability_id=cap_id,
        )
      agg = aggregates[key]
      agg.publication_ids.append(row["publication_id"])
      agg.confidences.append(float(row.get("confidence") or 0.0))
      agg.years.append(row.get("year"))

    return aggregates

  def _write_has_capability(self, agg: AuthorCapabilityAggregate) -> None:
    alabel = self._lbl.get("author", "Author")
    clabel = self._lbl.get("capability", "Capability")
    aprop = self._prop.get("author", {})
    cprop = self._prop.get("capability", {})
    rel = self._rel.get("has_capability", "HAS_CAPABILITY")
    hp = self._prop.get("has_capability", {})

    a_id = aprop.get("id", "halId")
    c_id = cprop.get("id", "id")

    self._run(
        f"""
        MATCH (a:{alabel} {{{a_id}: $person_id}})
        MATCH (c:{clabel} {{{c_id}: $cap_id}})
        MERGE (a)-[r:{rel} {{
            {hp.get('extraction_version', 'extractionVersion')}: $ev,
            {hp.get('aggregation_version', 'aggregationVersion')}: $av
        }}]->(c)
        SET
          r.{hp.get('inferred', 'inferred')} = true,
          r.{hp.get('publication_count', 'publicationCount')} = $pub_count,
          r.{hp.get('evidence_count', 'evidenceCount')} = $ev_count,
          r.{hp.get('avg_extraction_confidence', 'avgExtractionConfidence')} = $avg_conf,
          r.{hp.get('recent_publication_count', 'recentPublicationCount')} = $recent_count,
          r.{hp.get('first_seen_year', 'firstSeenYear')} = $first_year,
          r.{hp.get('last_seen_year', 'lastSeenYear')} = $last_year,
          r.{hp.get('score', 'score')} = $score
        """,
        person_id=agg.person_id,
        cap_id=agg.capability_id,
        ev=self._extraction_version,
        av=self._aggregation_version,
        pub_count=agg.publication_count,
        ev_count=agg.evidence_count,
        avg_conf=agg.avg_extraction_confidence,
        recent_count=agg.recent_publication_count(
            self._reference_year, self._half_life
        ),
        first_year=agg.first_seen_year,
        last_year=agg.last_seen_year,
        score=agg.recency_weighted_score(self._reference_year, self._half_life),
    )

  def aggregate(self) -> dict[str, int]:
    """Run the full aggregation pass.

    Returns a summary: {"written": int, "skipped_low_evidence": int, "skipped_placeholder": int}.
    """
    rows = self._fetch_evidence()
    aggregates = self._build_aggregates(rows)

    summary = {
        "written": 0,
        "skipped_low_evidence": 0,
        "skipped_placeholder": 0,
    }

    for agg in aggregates.values():
      if agg.person_id.startswith(self._skip_prefix):
        summary["skipped_placeholder"] += 1
        continue
      if agg.evidence_count < self._min_evidence_count:
        logger.debug(
            "Skipping (%r, %r): evidence_count=%d < min=%d",
            agg.person_id,
            agg.capability_id,
            agg.evidence_count,
            self._min_evidence_count,
        )
        summary["skipped_low_evidence"] += 1
        continue

      self._write_has_capability(agg)
      summary["written"] += 1

    logger.info(
        "Aggregation complete: written=%d, skipped_low_evidence=%d, skipped_placeholder=%d",
        summary["written"],
        summary["skipped_low_evidence"],
        summary["skipped_placeholder"],
    )
    return summary
