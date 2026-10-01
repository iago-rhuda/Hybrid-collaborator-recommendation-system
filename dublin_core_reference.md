# Dublin Core / DCMI Metadata Terms --- Reference for Code Review

## Purpose

Use this document as a reference when reviewing the project's metadata
normalization code.

The goal is **not** to force every HAL field into Dublin Core. Dublin
Core should be reused when its semantics correctly match the metadata.
HAL-specific information that is richer or more precise should remain in
the project's canonical model.

Official reference:

-   DCMI Metadata Terms:
    https://www.dublincore.org/specifications/dublin-core/dcmi-terms/
-   Namespace: `http://purl.org/dc/terms/`

Prefer the modern `dcterms:` vocabulary when designing semantic
mappings.

------------------------------------------------------------------------

## Core terms relevant to publication metadata

### `dcterms:title`

**Definition:** A name given to the resource.

Use for: - publication title

HAL examples: - `title_s`

Recommended mapping:

``` text
HAL title_s -> Article.title -> dcterms:title
```

------------------------------------------------------------------------

### `dcterms:creator`

**Definition:** An entity responsible for making the resource.

Use for: - authors of an article - primary creators of a resource

HAL examples: - `authFullName_s` - structured Author entities extracted
from HAL

Recommended semantic relationship:

``` text
Article --dcterms:creator--> Author
```

Important:

`creator` and `contributor` are **not equivalent**.

An article author should normally be represented as a `creator`, not
merely as a `contributor`.

------------------------------------------------------------------------

### `dcterms:contributor`

**Definition:** An entity responsible for making contributions to the
resource.

Use for: - contributors who participated in the resource but are not its
primary creators

Do not automatically map every author to `contributor`.

------------------------------------------------------------------------

### `dcterms:subject`

**Definition:** A topic of the resource.

Use for: - keywords - subjects - research topics

HAL examples: - `keyword_s` - domain information when a simple metadata
representation is sufficient

Recommended mapping:

``` text
HAL keyword_s -> Article.keywords -> dcterms:subject
```

For the Knowledge Graph, ResearchDomain should preferably remain a
separate entity:

``` text
Article --HAS_RESEARCH_DOMAIN--> ResearchDomain
```

Do not flatten the complete research-domain hierarchy into a single
Dublin Core field.

------------------------------------------------------------------------

### `dcterms:description`

**Definition:** An account of the resource.

Can be used for: - general description - summary

However, for scientific publications prefer the more specific:

### `dcterms:abstract`

**Definition:** A summary of the resource.

HAL:

``` text
abstract_s -> Article.abstract -> dcterms:abstract
```

Do not map an abstract to `description` when `dcterms:abstract` can be
used.

------------------------------------------------------------------------

### `dcterms:publisher`

**Definition:** An entity responsible for making the resource available.

Use for: - actual publisher

Do **not** map a journal title directly to `publisher`.

Incorrect:

``` text
journaltitle_s -> publisher
```

A journal and a publisher are different concepts.

Example:

``` text
Article -> published in -> Journal
Journal -> publisher -> Publisher
```

------------------------------------------------------------------------

### `dcterms:date`

**Definition:** A point or period of time associated with an event in
the lifecycle of the resource.

This is a generic date property.

Prefer a more specific term when possible.

------------------------------------------------------------------------

### `dcterms:issued`

**Definition:** Date of formal issuance of the resource.

For publications, this is normally preferable for the publication date.

HAL:

``` text
publicationDate_s -> Article.publication_date -> dcterms:issued
```

`publicationDateY_i` may be retained as a derived `publication_year`
property for querying/analytics, but it does not need a separate Dublin
Core mapping.

------------------------------------------------------------------------

### `dcterms:type`

**Definition:** The nature or genre of the resource.

HAL:

``` text
docType_s -> Article.document_type -> dcterms:type
```

Examples: - journal article - conference paper - thesis

------------------------------------------------------------------------

### `dcterms:format`

**Definition:** File format, physical medium, or dimensions of the
resource.

Use for things such as: - `application/pdf` - `text/html`

Do not use it for publication/document type.

------------------------------------------------------------------------

### `dcterms:identifier`

**Definition:** An unambiguous reference to the resource within a given
context.

Possible publication identifiers: - HAL ID - DOI - URI

Semantically these may all relate to `dcterms:identifier`, but **do not
destroy their individual meaning in the canonical model**.

Recommended internal representation:

``` text
Article.hal_id
Article.doi
Article.uri
```

Semantic mappings:

``` text
Article.hal_id -> dcterms:identifier
Article.doi    -> dcterms:identifier
Article.uri    -> dcterms:identifier
```

Avoid transforming:

``` json
{
  "hal_id": "hal-...",
  "doi": "10....",
  "uri": "https://..."
}
```

into an unlabeled list such as:

``` json
{
  "identifier": ["hal-...", "10....", "https://..."]
}
```

if that transformation causes the application to lose which identifier
is HAL, DOI, or URI.

------------------------------------------------------------------------

### `dcterms:language`

**Definition:** A language of the resource.

HAL:

``` text
language_s -> Article.language -> dcterms:language
```

Important:

Publication language belongs to the **Article**, not the Author.

Never infer an author's spoken languages from publication language.

------------------------------------------------------------------------

### `dcterms:source`

**Definition:** A related resource from which the described resource is
derived.

Do not use `source` simply to record which API supplied the metadata
unless the semantics actually match.

Metadata provenance such as:

``` text
source_system = "HAL"
```

is an application/provenance concern and is not automatically equivalent
to `dcterms:source`.

------------------------------------------------------------------------

### `dcterms:relation`

**Definition:** A related resource.

This is intentionally generic.

For the Knowledge Graph, prefer more specific relationships when known:

``` text
AUTHORED
AFFILIATED_WITH
PART_OF
HAS_RESEARCH_DOMAIN
PRESENTED_AT
SUBDOMAIN_OF
```

Do not replace precise graph relationships with generic
`dcterms:relation`.

------------------------------------------------------------------------

### `dcterms:rights`

**Definition:** Information about rights held in and over the resource.

Use for actual rights statements.

Related specific term:

### `dcterms:license`

Use for: - license documents/statements - Creative Commons licenses,
etc.

Important:

``` text
openAccess_bool != dcterms:rights
```

A boolean saying that an article is open access is not itself a rights
statement or license.

Keep, for example:

``` text
Article.open_access: true
```

as a separate property unless there is an appropriate vocabulary for
access status.

------------------------------------------------------------------------

### `dcterms:coverage`

**Definition:** Spatial or temporal topic of the resource, spatial
applicability, or jurisdiction.

Do not automatically map publication/conference location to coverage
unless that location is actually the subject or applicability of the
resource.

------------------------------------------------------------------------

## Recommended Article mapping for this project

  ----------------------------------------------------------------------------
  HAL field               Canonical model              Dublin Core / DCMI
  ----------------------- ---------------------------- -----------------------
  `halId_s`               `Article.hal_id`             `dcterms:identifier`

  `title_s`               `Article.title`              `dcterms:title`

  `abstract_s`            `Article.abstract`           `dcterms:abstract`

  `keyword_s`             `Article.keywords`           `dcterms:subject`

  `docType_s`             `Article.document_type`      `dcterms:type`

  `language_s`            `Article.language`           `dcterms:language`

  `publicationDate_s`     `Article.publication_date`   `dcterms:issued`

  `publicationDateY_i`    `Article.publication_year`   derived from issued
                                                       date

  `doiId_s`               `Article.doi`                `dcterms:identifier`

  `uri_s`                 `Article.uri`                `dcterms:identifier`

  `openAccess_bool`       `Article.open_access`        no direct DC mapping
                                                       recommended

  `peerReviewing_s`       `Article.peer_reviewed`      no direct DC mapping
                                                       recommended
  ----------------------------------------------------------------------------

Authors should be represented as entities/relationships rather than
flattened strings whenever possible:

``` text
Article --creator/AUTHORED--> Author
```

Research domains should remain entities:

``` text
Article --HAS_RESEARCH_DOMAIN--> ResearchDomain
```

Organizations should remain entities:

``` text
Author --AFFILIATED_WITH--> Organization
Organization --PART_OF--> Organization
```

------------------------------------------------------------------------

## Important distinction: canonical model vs semantic mapping

Do not design the internal data model as a lossy Dublin Core object.

Preferred architecture:

``` text
HAL API
   |
   v
HAL-specific parser
   |
   v
Canonical project model
   |
   +--> Article
   +--> Author
   +--> Organization
   +--> ResearchDomain
   +--> Conference
   |
   v
Semantic mappings
   |
   +--> Dublin Core / DCMI
   +--> other vocabularies later
```

Example:

``` text
Article.doi = "10.xxxx/example"
```

may have:

``` text
semantic mapping = dcterms:identifier
```

but the canonical model should still know that the value is specifically
a DOI.

------------------------------------------------------------------------

## Code review checklist

When reviewing the current implementation, verify:

1.  `creator` exists in the supported DCMI terms.
2.  HAL authors are not automatically reduced to `contributor`.
3.  `abstract_s` maps to `dcterms:abstract`, not only generic
    `description`.
4.  `publicationDate_s` maps to `dcterms:issued` rather than only
    generic `date`.
5.  `journaltitle_s` is NOT mapped to `publisher`.
6.  `openAccess_bool` is NOT treated as a rights statement/license.
7.  HAL ID, DOI, and URI retain their individual identities in the
    canonical model.
8.  `language_s` describes the Article only.
9.  `keyword_s` may map to `subject`, while ResearchDomain remains a
    first-class KG entity.
10. HAL organization fields are not forced into Dublin Core.
11. HAL-specific identifiers such as `authIdPerson_i`, IdHAL, ORCID,
    IdRef, ROR, and structure IDs are preserved where useful instead of
    being flattened into generic DC properties.
12. Specific graph relationships are not replaced with generic
    `relation`.
13. The implementation does not assume every source (HAL, ORCID, future
    APIs) has the same fields.
14. Dublin Core is used as a semantic vocabulary, not as a reason to
    discard source-specific information.
15. Tests verify that normalization does not silently lose identifier
    types or entity relationships.

------------------------------------------------------------------------

## Instruction for Codex

Review the project's existing Dublin Core transformer and metadata
models against this document.

Do not blindly modify the code to make every field Dublin
Core-compatible.

For every existing mapping:

1.  Identify the source field.
2.  Identify its current target.
3.  Compare its semantics with the DCMI definition.
4.  Mark it as:
    -   correct,
    -   questionable,
    -   incorrect, or
    -   intentionally project-specific.
5.  Explain any mismatch.
6.  Fix mappings that are clearly semantically incorrect.
7.  Preserve richer source-specific data when converting it to Dublin
    Core would lose information.
8.  Add/update tests for every corrected mapping.

Pay particular attention to: - creator vs contributor - abstract vs
description - issued vs date - journal vs publisher - open access vs
rights/license - HAL ID vs DOI vs URI - Article language vs Author
information

At the end, provide a concise report of: - mappings that were already
correct, - mappings changed, - mappings intentionally kept outside
Dublin Core, - any remaining ambiguities that require a modeling
decision.
