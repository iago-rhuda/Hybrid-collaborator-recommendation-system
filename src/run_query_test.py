from queries.graph_querier import GraphQuerier
from logger import get_logger

logger = get_logger(__name__)


def main():
  querier = GraphQuerier()

  logger.info("=== Testing Graph Query via Code ===")

  # Exemplo 1: Buscar coautores por termo no título
  search_term = "Data"
  logger.info(f"Searching for publications containing '{search_term}' and their authors...")
  results = querier.get_collaborators_network(search_term)

  for r in results[:5]:  # Show the first 5 results.
    logger.info(f"- Artigo: {r['publication']}")
    logger.info(f"  Autores: {', '.join(r['co_authors'])}")

  querier.close()


if __name__ == "__main__":
  main()