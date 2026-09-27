from queries.graph_querier import GraphQuerier


def main():
  querier = GraphQuerier()

  print("=== Testing Graph Query via Code ===")

  # Exemplo 1: Buscar coautores por termo no título
  search_term = "Data"
  print(f"\nSearching for publications containing '{search_term}' and their authors...")
  results = querier.get_collaborators_network(search_term)

  for r in results[:5]:  # Show the first 5 results.
    print(f"- Artigo: {r['publication']}")
    print(f"  Autores: {', '.join(r['co_authors'])}")

  querier.close()


if __name__ == "__main__":
  main()