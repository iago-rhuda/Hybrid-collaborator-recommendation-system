# Neo4j schema: discovered state

This document records the schema and counts observed in the configured live
Neo4j database on **2026-10-04**. Counts are a point-in-time snapshot and can
change as data is loaded or removed. The repository's graph-writing code is in
[`src/database/neo4j_manager.py`](../src/database/neo4j_manager.py).

## How to inspect the schema

Run these read-only statements in Neo4j Browser (or the Neo4j query interface)
against the database being documented:

```cypher
CALL db.schema.visualization();

SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;

CALL db.schema.nodeTypeProperties()
YIELD nodeType, propertyName, propertyTypes, mandatory
RETURN nodeType, propertyName, propertyTypes, mandatory
ORDER BY nodeType, propertyName;

CALL db.schema.relTypeProperties()
YIELD relType, propertyName, propertyTypes, mandatory
RETURN relType, propertyName, propertyTypes, mandatory
ORDER BY relType, propertyName;
```

Count nodes by label and relationships by type:

```cypher
MATCH (n)
UNWIND labels(n) AS label
RETURN label, count(*) AS count
ORDER BY label;

MATCH ()-[r]->()
RETURN type(r) AS relationship, count(*) AS count
ORDER BY relationship;
```

The schema procedures profile the current graph; the two count queries are
also useful for reproducing the data-volume snapshot. `SHOW CONSTRAINTS`
inspects actual database constraints rather than inferring them from ETL code.

## Live counts

| Node label | Count |
|---|---:|
| `Author` | 690 |
| `Conference` | 96 |
| `Organization` | 431 |
| `Project` | 221 |
| `ResearchDomain` | 106 |

| Relationship type | Count |
|---|---:|
| `HAS_ORGANIZATION` | 1,225 |
| `HAS_RESEARCH_DOMAIN` | 351 |
| `PART_OF` | 373 |
| `PRESENTED_AT` | 103 |
| `SUBDOMAIN_OF` | 95 |
| `WROTE` | 933 |

These are database-wide counts for the configured connection at inspection
time. They are not HAL `numFound` counts, and this document does not assert
that the database contains the complete HAL corpus.

## Discovered node properties

The property/type inventory below is reported by
`db.schema.nodeTypeProperties()` on the inspected database. Types represent
the values observed there; nullable/missing properties are not guaranteed to
have a single uniform type.

| Label | Properties observed |
|---|---|
| `Author` | `halId` (STRING), `firstName` (STRING), `lastName` (STRING), `fullName` (STRING), `emailDomain` (STRING), `orcidId` (STRING), `googleScholarId` (STRING), `researcherId` (STRING), `idrefId` (STRING), `personId` (INTEGER, optional) |
| `Conference` | `conferenceId` (STRING), `title` (STRING), `startDate` (STRING), `endDate` (STRING), `city` (STRING), `country` (STRING) |
| `Organization` | `halId` (INTEGER), `country` (STRING), `name` (STRING), `acronym` (STRING, optional), `type` (STRING), `status` (STRING), `ror` (STRING, optional), `code` (STRING, optional), `address` (STRING, optional) |
| `Project` | `halId` (STRING), `keywords` (LIST of STRING; empty lists also observed), `documentType` (STRING), `publicationYear` (INTEGER), `language` (LIST of STRING), `abstract` (STRING), `title` (STRING), `publicationDate` (STRING), `uri` (STRING), `doi` (STRING) |
| `ResearchDomain` | `id` (STRING), `name` (STRING), `nameFr` (STRING), `source` (STRING) |

`mandatory` from the schema-procedure output describes its discovered property
profile; it should not be confused with a `NOT NULL` database constraint.
Uniqueness constraints are listed separately below.

## Discovered relationship types

| Relationship | Direction and endpoints | Properties observed |
|---|---|---|
| `WROTE` | `(:Author)-[:WROTE]->(:Project)` | none |
| `PRESENTED_AT` | `(:Project)-[:PRESENTED_AT]->(:Conference)` | none |
| `HAS_RESEARCH_DOMAIN` | `(:Project)-[:HAS_RESEARCH_DOMAIN]->(:ResearchDomain)` | `primary` (BOOLEAN) |
| `SUBDOMAIN_OF` | `(:ResearchDomain)-[:SUBDOMAIN_OF]->(:ResearchDomain)` | none |
| `HAS_ORGANIZATION` | `(:Project)-[:HAS_ORGANIZATION]->(:Organization)` | none |
| `PART_OF` | `(:Organization)-[:PART_OF]->(:Organization)` | none |

All relationships in this table were observed in the database at inspection
time. No `Author`-to-`Organization` relationship type appeared in the
database-wide type count. This agrees with the ETL model: HAL organization
fields are record-level, and the repository stores project-to-organization
edges instead.

## Uniqueness constraints observed

`SHOW CONSTRAINTS` returned these five node-property uniqueness constraints:

| Constraint | Entity | Unique property |
|---|---|---|
| `author_hal_id` | `Author` | `halId` |
| `conference_id` | `Conference` | `conferenceId` |
| `organization_hal_id` | `Organization` | `halId` |
| `project_hal_id` | `Project` | `halId` |
| `research_domain_id` | `ResearchDomain` | `id` |

These constraints prevent future duplicate values for the constrained
properties; they do not establish that every node has a valid or meaningful
identifier, nor do they prove that historical ingestion was complete.

## What this schema proves

- At the inspection time, the connected database contained the five node
  labels and six relationship types listed above, with the listed counts.
- The listed uniqueness constraints were installed in that database.
- The observed graph contains the expected authorship, publication,
  conference, domain, organization, and hierarchy relationship patterns.
- The schema metadata reported the property names and observed value types
  listed above.

## What remains uncertain

- Counts alone do not prove that all expected HAL records were loaded. Compare
  the selected snapshot against Neo4j with
  [`src/validation/etl_compare.py`](../src/validation/etl_compare.py).
- The schema does not prove that property values are current, complete, or
  semantically correct. Persistence uses `ON CREATE SET`, so re-ingestion does
  not refresh existing node properties.
- A relationship type's presence does not prove every node has the expected
  edges, that edges are non-duplicated, or that a hierarchy is acyclic and
  well-formed. Run the Neo4j integrity and hierarchy checks.
- A uniqueness constraint is not a required-property constraint; null or
  absent identifiers may still need separate validation.
- `Organization.halId` was reported as INTEGER in the inspected data while
  the other keyed identifiers were reported as strings. The live profile and
  ETL typing should be reviewed before assuming IDs have a uniform type.
- `db.schema.*Properties()` describes what the procedure discovered in the
  current graph; it is not a complete business contract or a guarantee about
  future writes.
- The snapshot records database state at one time only. Re-run the inspection
  after significant ingestion or schema changes.

## Authoritative taxonomy policy

`ResearchDomain` IDs, labels, and hierarchy originate from HAL and are treated
as authoritative source facts. Recommendation logic may use those facts to
retrieve or compare publication evidence, but must not rename, re-parent, or
otherwise rewrite the taxonomy to improve a recommendation. Capabilities and
project requirements are derived concepts and belong in separate inferred
data with provenance; altering the source taxonomy would blur that distinction
and make recommendations modify the evidence they consume.
