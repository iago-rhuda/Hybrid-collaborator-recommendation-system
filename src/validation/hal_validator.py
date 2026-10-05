import re
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class ValidationIssue:
  code: str
  message: str
  field: str | None = None
  doc_index: int | None = None
  severity: str = "error"


@dataclass
class ValidationReport:
  errors: list[ValidationIssue] = field(default_factory=list)
  warnings: list[ValidationIssue] = field(default_factory=list)
  doc_count: int = 0
  num_found: int | None = None

  @property
  def is_valid(self) -> bool:
    return not self.errors

  @property
  def all_issues(self) -> list[ValidationIssue]:
    return self.errors + self.warnings


def _as_list(value):
  if value is None:
    return []
  if isinstance(value, list):
    return value
  return [value]


def _first_present(*values):
  for value in values:
    if value is not None and str(value).strip() != "":
      return value
  return None


def _is_blank(value) -> bool:
  if value is None:
    return True
  if isinstance(value, (list, tuple, set)):
    return len(value) == 0 or all(_is_blank(item) for item in value)
  return str(value).strip() == ""


def _validate_date_string(value, field_name: str, doc_index: int | None = None):
  if value is None or _is_blank(value):
    return []

  value = str(value).strip()
  if value.endswith("Z"):
    value = value[:-1]

  if re.fullmatch(r"\d{4}", value):
    return []

  try:
    date.fromisoformat(value)
  except ValueError:
    return [
        ValidationIssue(
            code="malformed_date",
            message=f"{field_name} is not a valid ISO date: {value!r}",
            field=field_name,
            doc_index=doc_index,
            severity="warning",
        )
    ]

  return []


def _validate_language_value(value, field_name: str, doc_index: int | None = None):
  if value is None or _is_blank(value):
    return []

  value = str(value).strip()
  normalized = value.lower()

  known_languages = {
      "en", "fr", "de", "es", "it", "pt", "nl", "ru", "zh", "ja", "ko",
      "ar", "tr", "cs", "pl", "sv", "fi", "el", "hu", "uk", "he", "id",
      "da", "ro", "sl", "no", "ca", "th", "vi", "sr",
  }

  if re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]+)?", value) and normalized.split("-")[0] in known_languages:
    return []

  return [
      ValidationIssue(
          code="malformed_language",
          message=f"{field_name} has an invalid language code: {value!r}",
          field=field_name,
          doc_index=doc_index,
          severity="warning",
      )
  ]


def _compare_parallel_array_lengths(doc: dict, field_names: list[str], doc_index: int | None = None):
  issues = []
  expected_length = None

  for field_name in field_names:
    if field_name not in doc:
      continue
    current_value = doc[field_name]
    current_length = len(_as_list(current_value))
    if expected_length is None:
      expected_length = current_length
    elif current_length not in (0, expected_length):
      issues.append(
          ValidationIssue(
              code="parallel_array_length_mismatch",
              message=(
                  f"Parallel arrays are misaligned for {field_name}; "
                  f"expected length {expected_length}, got {current_length}."
              ),
              field=field_name,
              doc_index=doc_index,
              severity="warning",
          )
      )

  return issues


def _validate_document(doc: dict, doc_index: int | None = None):
  issues = []

  hal_id = _first_present(doc.get("halId_s"), doc.get("docid"))
  if _is_blank(hal_id):
    issues.append(
        ValidationIssue(
            code="missing_hal_id",
            message="Document is missing halId_s/docid.",
            field="halId_s",
            doc_index=doc_index,
        )
    )

  if _is_blank(doc.get("title_s")):
    issues.append(
        ValidationIssue(
            code="missing_title",
            message="title_s is required and missing or empty.",
            field="title_s",
            doc_index=doc_index,
        )
    )

  if _is_blank(doc.get("abstract_s")):
    issues.append(
        ValidationIssue(
            code="missing_abstract",
            message="abstract_s is missing or empty.",
            field="abstract_s",
            doc_index=doc_index,
            severity="warning",
        )
    )

  if _is_blank(doc.get("keyword_s")):
    issues.append(
        ValidationIssue(
            code="missing_keywords",
            message="keyword_s is missing or empty.",
            field="keyword_s",
            doc_index=doc_index,
            severity="warning",
        )
    )

  if _is_blank(doc.get("doiId_s")):
    issues.append(
        ValidationIssue(
            code="missing_doi",
            message="doiId_s is missing or empty.",
            field="doiId_s",
            doc_index=doc_index,
            severity="warning",
        )
    )

  if _is_blank(doc.get("authFullName_s")):
    issues.append(
        ValidationIssue(
            code="missing_authors",
            message="authFullName_s is required but missing or empty.",
            field="authFullName_s",
            doc_index=doc_index,
        )
    )

  domain_values = [
      doc.get("primaryDomain_s"),
      doc.get("domainAllCode_s"),
      doc.get("domain_s"),
  ]
  if all(_is_blank(value) for value in domain_values):
    issues.append(
        ValidationIssue(
            code="missing_domains",
            message="No research domain is present in primaryDomain_s/domainAllCode_s/domain_s.",
            field="primaryDomain_s",
            doc_index=doc_index,
            severity="warning",
        )
    )

  if "docType_s" in doc and _is_blank(doc.get("docType_s")):
    issues.append(
        ValidationIssue(
            code="missing_doc_type",
            message="docType_s is present but empty.",
            field="docType_s",
            doc_index=doc_index,
        )
    )

  if "publicationDate_s" in doc:
    issues.extend(
        _validate_date_string(
            doc.get("publicationDate_s"),
            "publicationDate_s",
            doc_index,
        )
    )
  if "producedDate_s" in doc:
    issues.extend(
        _validate_date_string(
            doc.get("producedDate_s"),
            "producedDate_s",
            doc_index,
        )
    )
  if "conferenceStartDate_s" in doc:
    issues.extend(
        _validate_date_string(
            doc.get("conferenceStartDate_s"),
            "conferenceStartDate_s",
            doc_index,
        )
    )
  if "conferenceEndDate_s" in doc:
    issues.extend(
        _validate_date_string(
            doc.get("conferenceEndDate_s"),
            "conferenceEndDate_s",
            doc_index,
        )
    )

  if "language_s" in doc:
    language_values = _as_list(doc.get("language_s"))
    for value in language_values:
      issues.extend(
          _validate_language_value(value, "language_s", doc_index)
      )

  if "publicationDateY_i" in doc and doc.get("publicationDateY_i") is not None:
    year_value = doc.get("publicationDateY_i")
    if not isinstance(year_value, int) and not str(year_value).isdigit():
      issues.append(
          ValidationIssue(
              code="malformed_publication_year",
              message=f"publicationDateY_i is not an integer: {year_value!r}",
              field="publicationDateY_i",
              doc_index=doc_index,
              severity="warning",
          )
      )

  author_fields = [
      "authFullName_s",
      "authIdHal_s",
      "authIdPerson_i",
      "authFirstName_s",
      "authLastName_s",
      "authEmailDomain_s",
      "authORCIDIdExt_s",
      "authGoogleScholarIdExt_s",
      "authResearcherIdIdExt_s",
      "authIdRefIdExt_s",
  ]
  issues.extend(_compare_parallel_array_lengths(doc, author_fields, doc_index))

  organization_fields = [
      "structId_i",
      "structName_s",
      "structAcronym_s",
      "structType_s",
      "structCountry_s",
      "structAddress_s",
      "structCode_s",
      "structValid_s",
      "structRorIdExt_s",
      "structIdrefIdExt_s",
      "structIsniIdExt_s",
      "structRnsrIdExt_s",
      "structWikidataIdExt_s",
  ]
  issues.extend(_compare_parallel_array_lengths(doc, organization_fields, doc_index))

  if isinstance(doc.get("title_s"), list) and len(doc.get("title_s")) > 1:
    issues.append(
        ValidationIssue(
            code="multi_title_value",
            message="title_s contains multiple values; only one title is expected.",
            field="title_s",
            doc_index=doc_index,
            severity="warning",
        )
    )

  return issues


def validate_hal_payload(response, *, params=None, status_code=None):
  issues = []

  if status_code is not None and status_code >= 400:
    issues.append(
        ValidationIssue(
            code="http_error",
            message=f"HAL request failed with HTTP status {status_code}.",
            field="status_code",
            severity="error",
        )
    )

  if not isinstance(response, dict):
    return ValidationReport(
        errors=[
            ValidationIssue(
                code="invalid_response_root",
                message="HAL response root must be a dictionary.",
                field="response",
            )
        ],
        doc_count=0,
    )

  payload = response.get("response")
  if not isinstance(payload, dict):
    issues.append(
        ValidationIssue(
            code="invalid_response_payload",
            message="Expected a top-level 'response' dictionary containing HAL data.",
            field="response",
        )
    )
    return ValidationReport(errors=issues, doc_count=0)

  docs = payload.get("docs")
  num_found = payload.get("numFound")

  if docs is None:
    issues.append(
        ValidationIssue(
            code="missing_docs",
            message="Response payload is missing the 'docs' array.",
            field="docs",
        )
    )
    return ValidationReport(errors=issues, doc_count=0, num_found=num_found)

  if not isinstance(docs, list):
    issues.append(
        ValidationIssue(
            code="invalid_docs_type",
            message="The 'docs' field must be a list of document dictionaries.",
            field="docs",
        )
    )
    return ValidationReport(errors=issues, doc_count=0, num_found=num_found)

  seen_hal_ids = set()
  doc_issues = []
  for index, doc in enumerate(docs):
    if not isinstance(doc, dict):
      doc_issues.append(
          ValidationIssue(
              code="non_object_document",
              message=f"Document at index {index} is not an object.",
              field="docs",
              doc_index=index,
          )
      )
      continue

    hal_id = _first_present(doc.get("halId_s"), doc.get("docid"))
    if hal_id is not None:
      hal_key = str(hal_id).strip()
      if hal_key and hal_key in seen_hal_ids:
        doc_issues.append(
            ValidationIssue(
                code="duplicate_hal_id",
                message=f"Duplicate halId detected: {hal_key!r}",
                field="halId_s",
                doc_index=index,
            )
        )
      else:
        seen_hal_ids.add(hal_key)

    doc_issues.extend(_validate_document(doc, index))

  if isinstance(num_found, (int, float)) and len(docs) > num_found:
    issues.append(
        ValidationIssue(
            code="pagination_overflow",
            message=(
                f"Response contains {len(docs)} docs but numFound says {num_found}; "
                "this suggests pagination or response drift."
            ),
            field="numFound",
        )
    )

  if params:
    requested_rows = params.get("rows")
    start = params.get("start", 0)
    if requested_rows is not None:
      row_count = int(requested_rows)
      if len(docs) > row_count:
        issues.append(
            ValidationIssue(
                code="page_size_exceeded",
                message=(
                    f"Page returned {len(docs)} docs for a requested page size of "
                    f"{row_count}."
                ),
                field="rows",
            )
        )
      if isinstance(num_found, int) and start + len(docs) > num_found:
        issues.append(
            ValidationIssue(
                code="pagination_incomplete",
                message=(
                    f"Page start {start} + fetched {len(docs)} exceeds numFound {num_found}."
                ),
                field="start",
            )
        )

  return ValidationReport(
      errors=issues + [issue for issue in doc_issues if issue.severity == "error"],
      warnings=[issue for issue in doc_issues if issue.severity == "warning"],
      doc_count=len(docs),
      num_found=num_found,
  )


def validate_hal_documents(docs, *, num_found=None, params=None):
  issues = []
  seen_hal_ids = set()
  for index, doc in enumerate(docs):
    if not isinstance(doc, dict):
      issues.append(
          ValidationIssue(
              code="non_object_document",
              message=f"Document at index {index} is not an object.",
              field="docs",
              doc_index=index,
          )
      )
      continue

    hal_id = _first_present(doc.get("halId_s"), doc.get("docid"))
    if hal_id is not None:
      hal_key = str(hal_id).strip()
      if hal_key and hal_key in seen_hal_ids:
        issues.append(
            ValidationIssue(
                code="duplicate_hal_id",
                message=f"Duplicate halId detected: {hal_key!r}",
                field="halId_s",
                doc_index=index,
            )
        )
      elif hal_key:
        seen_hal_ids.add(hal_key)

    issues.extend(_validate_document(doc, index))

  if isinstance(num_found, (int, float)) and len(docs) > num_found:
    issues.append(
        ValidationIssue(
            code="pagination_overflow",
            message=(
                f"Received {len(docs)} documents but numFound is {num_found}."
            ),
            field="numFound",
        )
    )

  if params:
    requested_rows = params.get("rows")
    if requested_rows is not None and len(docs) > requested_rows:
      issues.append(
          ValidationIssue(
              code="page_size_exceeded",
              message=(
                  f"Fetched {len(docs)} docs while requesting a page size of {requested_rows}."
              ),
              field="rows",
          )
      )

  return ValidationReport(
      errors=[issue for issue in issues if issue.severity == "error"],
      warnings=[issue for issue in issues if issue.severity == "warning"],
      doc_count=len(docs),
      num_found=num_found,
  )
