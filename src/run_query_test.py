from queries.graph_querier import GraphQuerier


def main():
  querier = GraphQuerier()

  print("=== Testando Consulta ao Grafo via Código ===")

  # Exemplo 1: Buscar coautores por termo no título
  search_term = "Data"
  print(f"\nBuscando publicações contendo '{search_term}' e seus autores...")
  results = querier.get_collaborators_network(search_term)

  for r in results[:5]:  # Mostra os 5 primeiros resultados
    print(f"- Artigo: {r['publication']}")
    print(f"  Autores: {', '.join(r['co_authors'])}")

  querier.close()


if __name__ == "__main__":
  main()