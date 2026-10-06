"""CLI and Interactive Terminal for collaborator recommendations and GraphRAG.

Usage:
  # Natural language message describing a task (connected to live Neo4j):
  python src/recommend_cli.py --query "Research in toxicology, lungs, and liver cellular interactions" --top-k 3

  # Interactive terminal session (enter task descriptions in loop):
  python src/recommend_cli.py --interactive

  # Recommend for an existing publication:
  python src/recommend_cli.py --project-id anses-03212886 --top-k 5

  # Run offline with static fixtures:
  python src/recommend_cli.py --query "Natural language processing with deep transformers" --use-fake-adapter
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

from config import get_llm_config
from graph.adapter import GraphAdapter, ProjectSpec
from graph.fake_adapter import FakeAdapter
from rag.context import build_explanation_context
from rag.explain import ExplanationLLMBackend, explain_candidate
from recommender.engine import recommend_collaborators

_STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas", "por", "pelo", "pela", "pelos", "pelas",
    "para", "com", "sem", "sobre", "entre", "que", "se", "ou", "e", "é", "são",
    "me", "te", "se", "nos", "vos", "meu", "minha", "seu", "sua", "nosso", "nossa",
    "projeto", "pesquisa", "preciso", "busco", "procuro", "quero", "encontrar",
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "with", "without",
    "by", "of", "from", "as", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "project", "research", "study",
    "looking", "need", "want", "seeking", "find", "collaborator", "collaborators",
    "le", "la", "les", "un", "une", "des", "du", "de", "dans", "en", "sur", "pour",
    "avec", "sans", "par", "et", "ou", "est", "sont", "projet", "recherche",
}


def extract_keywords_from_query(query: str) -> list[str]:
  """Extract informative keywords and keyphrases from natural language queries."""
  # Strip punctuation and normalize
  cleaned = re.sub(r"[^\w\s\-]", " ", query.lower())
  tokens = [t.strip() for t in cleaned.split() if len(t.strip()) > 2]
  meaningful = [t for t in tokens if t not in _STOPWORDS]

  # Generate unigrams and bigrams
  keywords: list[str] = []
  for w in meaningful:
    if w not in keywords:
      keywords.append(w)

  for i in range(len(meaningful) - 1):
    bigram = f"{meaningful[i]} {meaningful[i+1]}"
    if bigram not in keywords:
      keywords.append(bigram)

  return keywords[:10]


class LiveGeminiExplanationLLM(ExplanationLLMBackend):
  """Calls Google AI Studio Gemini API, returning grounded text."""

  def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
    self._api_key = api_key
    self._model = model

  def generate_explanation(self, prompt: str) -> str:
    import requests
    # Try requested model and active flash models
    models_to_try = [self._model]
    for fallback in ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-flash-latest"]:
      if fallback not in models_to_try:
        models_to_try.append(fallback)

    last_exc = None
    for model_name in models_to_try:
      clean_name = model_name.replace("models/", "")
      url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_name}:generateContent?key={self._api_key}"
      payload = {
          "contents": [
              {
                  "parts": [
                      {
                          "text": (
                              "You are a scientific collaborator recommendation assistant. "
                              "Explain why the candidate is recommended using evidence facts. "
                              "Only cite IDs in brackets [id] that are explicitly provided in the context.\n\n"
                              + prompt
                          )
                      }
                  ]
              }
          ],
          "generationConfig": {
              "temperature": 0.1,
          },
      }
      try:
        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code == 200:
          data = resp.json()
          candidates = data.get("candidates", [])
          if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
              return parts[0].get("text", "").strip()
        last_exc = RuntimeError(f"Gemini ({clean_name}) status {resp.status_code}: {resp.text[:120]}")
      except Exception as exc:
        last_exc = exc

    raise last_exc or RuntimeError("All Gemini models failed")


class LiveOpenAIExplanationLLM(ExplanationLLMBackend):
  """Calls OpenAI API if API key is provided, returning grounded text."""

  def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
    self._api_key = api_key
    self._model = model

  def generate_explanation(self, prompt: str) -> str:
    import requests
    headers = {
        "Authorization": f"Bearer {self._api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": self._model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a scientific collaborator recommendation assistant. "
                    "Only cite IDs in brackets [id] that are explicitly provided in the context."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
  parser = argparse.ArgumentParser(
      description="Recommend research collaborators using Graph facts and GraphRAG grounded explanations."
  )
  input_group = parser.add_argument_group("Input Target (choose one)")
  input_group.add_argument(
      "--query", "-q",
      type=str,
      help="Natural language task or project description (e.g. 'Modelos de difusão para imagens biomédicas')",
  )
  input_group.add_argument(
      "--interactive", "-i",
      action="store_true",
      help="Start an interactive terminal prompt to query collaborators in real time",
  )
  input_group.add_argument(
      "--project-id",
      type=str,
      help="HAL publication ID of an existing project in the graph (e.g. anses-03212886, hal-001)",
  )
  input_group.add_argument(
      "--title",
      type=str,
      help="Title of a new project specification",
  )
  parser.add_argument(
      "--abstract",
      type=str,
      default="",
      help="Abstract of a new project specification (used with --title)",
  )
  parser.add_argument(
      "--keywords",
      type=str,
      default="",
      help="Comma-separated keywords (used with --title)",
  )
  parser.add_argument(
      "--top-k",
      type=int,
      default=3,
      help="Number of recommendations to return (default: 3)",
  )
  parser.add_argument(
      "--use-fake-adapter",
      action="store_true",
      help="Use in-memory FakeAdapter with fixtures instead of connecting to live Neo4j",
  )
  parser.add_argument(
      "--format",
      choices=["text", "json"],
      default="text",
      help="Output format: 'text' (default) or 'json'",
  )
  parser.add_argument(
      "--no-explain",
      action="store_true",
      help="Disable grounded explanation generation",
  )
  return parser.parse_args(argv)


def get_adapter(use_fake: bool) -> GraphAdapter:
  """Get GraphAdapter instance (FakeAdapter or Neo4jAdapter)."""
  if use_fake:
    return FakeAdapter()
  try:
    from graph.neo4j_adapter import Neo4jAdapter
    return Neo4jAdapter.from_config()
  except Exception as exc:
    print(f"[Warning] Could not connect to live Neo4j ({exc}). Falling back to FakeAdapter.", file=sys.stderr)
    return FakeAdapter()


def get_llm_backend() -> ExplanationLLMBackend | None:
  """Return an LLM backend if API key is configured in .env, otherwise None (uses template)."""
  cfg = get_llm_config()
  api_key = cfg.get("api_key")
  provider = cfg.get("provider", "gemini")
  model = cfg.get("model", "gemini-2.5-flash")

  if api_key and not api_key.startswith("your-") and len(api_key) > 10:
    try:
      if provider in ("gemini", "google"):
        return LiveGeminiExplanationLLM(api_key=api_key, model=model)
      return LiveOpenAIExplanationLLM(api_key=api_key, model=model)
    except Exception:
      return None
  return None


def execute_recommendation(
    adapter: GraphAdapter,
    project_id: str | None = None,
    spec: ProjectSpec | None = None,
    top_k: int = 3,
    output_format: str = "text",
    explain: bool = True,
) -> None:
  """Execute recommendation pipeline and print formatted results."""
  res = recommend_collaborators(
      adapter=adapter,
      project_id=project_id,
      spec=spec,
      top_k=top_k,
  )

  llm_backend = get_llm_backend() if explain else None

  # Generate explanations
  explanations = []
  if explain:
    for cand in res.candidates:
      ev_items = adapter.get_candidate_evidence(
          person_id=cand.person_id,
          domain_ids=res.requirements.domain_ids,
          capability_ids=[
              c.capability_id
              for c in res.requirements.required_capabilities
              if c.capability_id
          ],
      )
      ctx = build_explanation_context(
          candidate=cand,
          evidence_items=ev_items,
          target_title=res.target_title,
          target_project_id=res.target_project_id,
          gaps=res.gaps,
      )
      exp_res = explain_candidate(ctx, llm_backend=llm_backend)
      explanations.append(exp_res)
  else:
    explanations = [None] * len(res.candidates)

  if output_format == "json":
    output: dict[str, Any] = {
        "target_project_id": res.target_project_id,
        "target_title": res.target_title,
        "team_members": res.team_member_ids,
        "gaps": [
            {
                "name": g.name,
                "importance": g.importance,
                "is_covered": g.is_covered,
                "covered_by": g.covered_by,
            }
            for g in res.gaps
        ],
        "recommendations": [],
    }
    for cand, exp in zip(res.candidates, explanations):
      output["recommendations"].append({
          "person_id": cand.person_id,
          "full_name": cand.full_name,
          "total_score": cand.total_score,
          "is_placeholder": cand.is_placeholder,
          "features": cand.features,
          "weights": cand.weights,
          "contributions": cand.contributions,
          "evidence_ids": cand.evidence_ids,
          "explanation": exp.explanation if exp else "",
          "cited_ids": exp.cited_ids if exp else [],
          "used_template": exp.used_template if exp else False,
      })
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return

  # Pretty text format
  print("\n" + "=" * 75)
  print(" RESEARCH COLLABORATOR RECOMMENDATION (GRAPHRAG)")
  print("=" * 75)
  if res.target_project_id:
    print(f"Target Publication: {res.target_project_id}")
  print(f"Target / Task:      {res.target_title or 'N/A'}")
  if res.team_member_ids:
    print(f"Current Team:       {', '.join(res.team_member_ids)}")
  if res.requirements.domain_ids:
    print(f"Matched Domains:    {', '.join(res.requirements.domain_ids)}")
  print("-" * 75)

  print("CAPABILITY GAP ANALYSIS:")
  if not res.gaps:
    print("  No explicit requirements registered; candidate matching based on research domains.")
  else:
    for g in res.gaps:
      status = "COVERED" if g.is_covered else "UNCOVERED GAP"
      cov = f"by {', '.join(g.covered_by)}" if g.is_covered else ""
      print(f"  - [{status}] {g.name} (importance: {g.importance:.2f}) {cov}")

  print("-" * 75)
  print(f"RANKED CANDIDATES (Top {len(res.candidates)}):")
  if not res.candidates:
    print("  No matching candidates found in the graph for this query.")
  else:
    for idx, (cand, exp) in enumerate(zip(res.candidates, explanations), start=1):
      ph_note = " [WARNING: UNRELIABLE PLACEHOLDER ID]" if cand.is_placeholder else ""
      print(f"\n{idx}. {cand.full_name} ({cand.person_id}){ph_note}")
      print(f"   Total Score: {cand.total_score:.4f}")
      print("   Feature Breakdown:")
      for feat, val in cand.features.items():
        w = cand.weights.get(feat, 0.0)
        c = cand.contributions.get(feat, 0.0)
        print(f"     * {feat:20s}: value={val:.3f} | weight={w:.2f} | contrib={c:.4f}")
      print(f"   Evidence IDs: {', '.join(cand.evidence_ids[:10]) if cand.evidence_ids else 'None'}" + ("..." if len(cand.evidence_ids) > 10 else ""))
      if exp:
        print(f"   Grounded Explanation: {exp.explanation}")
        if exp.cited_ids:
          print(f"   Verified Citations:   {', '.join(exp.cited_ids)}")
        if exp.used_template and exp.fallback_reason:
          print(f"   [Engine Notice]:      Grounding verified via deterministic graph facts ({exp.fallback_reason})")

  print("=" * 75 + "\n")


def run_interactive(adapter: GraphAdapter, top_k: int) -> None:
  """Run an interactive prompt loop in the terminal."""
  print("\n" + "=" * 75)
  print(" GRAPHRAG INTERACTIVE COLLABORATOR RECOMMENDER")
  print("=" * 75)
  print("Type your research task description, project idea, or topic.")
  print("Type 'exit' or 'quit' to terminate.\n")

  while True:
    try:
      user_input = input("Research Task > ").strip()
    except (EOFError, KeyboardInterrupt):
      print("\nExiting interactive session.")
      break

    if not user_input:
      continue
    if user_input.lower() in ("exit", "quit", "q"):
      print("Exiting interactive session.")
      break

    kws = extract_keywords_from_query(user_input)
    spec = ProjectSpec(
        title=user_input if len(user_input) <= 80 else user_input[:77] + "...",
        abstract=user_input,
        keywords=kws,
    )
    execute_recommendation(
        adapter=adapter,
        spec=spec,
        top_k=top_k,
        output_format="text",
        explain=True,
    )


def main(argv: list[str] | None = None) -> int:
  args = parse_args(argv)
  adapter = get_adapter(args.use_fake_adapter)

  if args.interactive:
    run_interactive(adapter, top_k=args.top_k)
    return 0

  if args.query:
    kws = extract_keywords_from_query(args.query)
    spec = ProjectSpec(
        title=args.query if len(args.query) <= 80 else args.query[:77] + "...",
        abstract=args.query,
        keywords=kws,
    )
    execute_recommendation(
        adapter=adapter,
        spec=spec,
        top_k=args.top_k,
        output_format=args.format,
        explain=not args.no_explain,
    )
    return 0

  if args.project_id:
    execute_recommendation(
        adapter=adapter,
        project_id=args.project_id,
        top_k=args.top_k,
        output_format=args.format,
        explain=not args.no_explain,
    )
    return 0

  if args.title:
    kw_list = [k.strip() for k in args.keywords.split(",") if k.strip()]
    spec = ProjectSpec(
        title=args.title,
        abstract=args.abstract,
        keywords=kw_list,
    )
    execute_recommendation(
        adapter=adapter,
        spec=spec,
        top_k=args.top_k,
        output_format=args.format,
        explain=not args.no_explain,
    )
    return 0

  print("Error: Please provide --query, --interactive, --project-id, or --title.", file=sys.stderr)
  print("Run 'python src/recommend_cli.py --help' for options.", file=sys.stderr)
  return 1


if __name__ == "__main__":
  sys.exit(main())
