import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from connectors.hal_client import HalClient
from logger import get_logger

logger = get_logger(__name__)


def _utc_timestamp() -> str:
  return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _get_requested_fields(client: Any) -> list[str]:
  fields = getattr(client, "fields", None)
  if isinstance(fields, str):
    return [field.strip() for field in fields.split(",") if field.strip()]
  if isinstance(fields, (list, tuple)):
    return [str(field) for field in fields]
  return []


def _normalize_author_fields(
    doc: dict[str, Any],
    requested_fields: list[str],
) -> dict[str, Any]:
  author_fields = {
      field
      for field in requested_fields
      if field.startswith("auth")
  } | {
      field
      for field in doc
      if field.startswith("auth")
  }
  if not author_fields:
    return doc

  author_values = {}
  for field in author_fields:
    value = doc.get(field)
    if value is None:
      values = []
    elif isinstance(value, list):
      values = value
    else:
      values = [value]
    author_values[field] = values

  names = author_values.get("authFullName_s")
  author_count = (
      len(names)
      if names
      else max((len(values) for values in author_values.values()), default=0)
  )

  normalized = dict(doc)
  for field, values in author_values.items():
    normalized[field] = (values + [0] * author_count)[:author_count]
  return normalized


def _extract_response(response: Any) -> dict[str, Any]:
  if not isinstance(response, dict):
    raise ValueError(
        "HAL response structure mismatch: expected top-level dictionary, "
        f"received {type(response).__name__}"
    )

  payload = response.get("response")
  if not isinstance(payload, dict):
    raise ValueError(
        "HAL response structure mismatch: expected 'response' dictionary, "
        f"received {type(payload).__name__}"
    )

  if "docs" not in payload or "numFound" not in payload:
    raise ValueError(
        "HAL response structure mismatch: expected 'docs' and 'numFound' "
        "inside the 'response' payload"
    )

  return payload


def _build_manifest(
    query: str,
    requested_fields: list[str],
    sort: str | None,
    num_found: int,
    fetched_count: int,
    timestamp: str,
    rows_per_page: int | None = None,
) -> dict[str, Any]:
  manifest = {
      "query": query,
      "requested_fields": requested_fields,
      "sort": sort,
      "numFound": int(num_found),
      "fetched_count": int(fetched_count),
      "timestamp": timestamp,
  }
  if rows_per_page is not None:
    manifest["rows_per_page"] = int(rows_per_page)
  return manifest


def create_hal_snapshot(
    query: str | None = None,
    max_rows: int | None = None,
    output_dir: str | Path | None = None,
    rows_per_page: int | None = None,
    client: Any | None = None,
    sort: str | None = "halId_s asc",
) -> dict[str, Path | dict[str, Any]]:
  """Fetch HAL publications in stable order and write JSONL plus a manifest."""
  client = client or HalClient()
  query = query or getattr(client, "query", "*:*")
  rows_per_page = rows_per_page or getattr(client, "rows_per_page", 100)
  output_dir = Path(output_dir or "exports/hal_snapshot")

  params = {
      "q": query,
      "fl": getattr(client, "fields", ""),
      "rows": rows_per_page,
      "start": 0,
      "wt": "json",
  }
  if sort:
    params["sort"] = sort
  response = client._get_json(params)
  payload = _extract_response(response)
  num_found = int(payload.get("numFound", 0))

  docs = client.fetch_publications(
      query=query,
      max_rows=max_rows,
      rows_per_page=rows_per_page,
      sort=sort,
  )

  timestamp = _utc_timestamp()
  snapshot_dir = output_dir / f"hal_snapshot_{timestamp}"
  snapshot_dir.mkdir(parents=True, exist_ok=True)

  requested_fields = _get_requested_fields(client)
  jsonl_path = snapshot_dir / "records.jsonl"
  with jsonl_path.open("w", encoding="utf-8") as jsonl_file:
    for doc in docs:
      jsonl_file.write(
          json.dumps(
              _normalize_author_fields(doc, requested_fields),
              ensure_ascii=False,
              sort_keys=True,
          ) + "\n"
      )

  manifest = _build_manifest(
      query=query,
      requested_fields=requested_fields,
      sort=sort,
      num_found=num_found,
      fetched_count=len(docs),
      timestamp=timestamp,
      rows_per_page=rows_per_page,
  )
  manifest_path = snapshot_dir / "manifest.json"
  with manifest_path.open("w", encoding="utf-8") as manifest_file:
    json.dump(manifest, manifest_file, ensure_ascii=False, indent=2, sort_keys=True)
    manifest_file.write("\n")

  return {
      "snapshot_dir": snapshot_dir,
      "jsonl_path": jsonl_path,
      "manifest_path": manifest_path,
      "manifest": manifest,
  }


def write_snapshot(
    query: str | None = None,
    max_rows: int | None = None,
    output_dir: str | Path | None = None,
    rows_per_page: int | None = None,
    client: Any | None = None,
    sort: str | None = "halId_s asc",
) -> dict[str, Path | dict[str, Any]]:
  return create_hal_snapshot(
      query=query,
      max_rows=max_rows,
      output_dir=output_dir,
      rows_per_page=rows_per_page,
      sort=sort,
      client=client,
  )


def main():
  parser = argparse.ArgumentParser(
      description="Fetch HAL publications and write a JSONL snapshot with a manifest."
  )
  parser.add_argument("--query", default="*:*", help="HAL query string.")
  parser.add_argument(
      "--max-rows",
      type=int,
      default=None,
      help="Optional maximum number of records to fetch.",
  )
  parser.add_argument(
      "--rows-per-page",
      type=int,
      default=100,
      help="Page size for HAL requests.",
  )
  parser.add_argument(
      "--sort",
      default="halId_s asc",
      help="Stable HAL sort expression used while paging.",
  )
  parser.add_argument(
      "--output-dir",
      type=str,
      default="exports/hal_snapshot",
      help="Directory where the snapshot files are written.",
  )
  args = parser.parse_args()

  result = create_hal_snapshot(
      query=args.query,
      max_rows=args.max_rows,
      output_dir=args.output_dir,
      rows_per_page=args.rows_per_page,
      sort=args.sort,
  )
  print(json.dumps(result["manifest"], ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
  main()
