"""Re-embebe el corpus con el modelo de EMBEDDING_MODEL, copiando los fragmentos de otra colección.

No vuelve a descargar ni a parsear PDF: lee texto y metadatos de la colección origen (la del modelo
anterior) y los escribe, con los mismos IDs, en QDRANT_COLLECTION, creada con la dimensión del modelo
nuevo. La colección origen no se toca: es el respaldo para regresar al modelo anterior.

  docker compose exec -e EMBEDDING_MODEL=BAAI/bge-m3 -e QDRANT_COLLECTION=legal_corpus_bge_m3 \\
      backend python -m app.reembeber legal_corpus_test

Reanudable: si se interrumpe, al volver a correrlo salta los puntos que ya están en el destino.
Motivo del cambio de modelo: ver docs/refactorizacion_rag.md §10 (comparación de embeddings).
"""

import sys
import time

from qdrant_client.http import models as qmodels

from app.rag import COLLECTION_NAME, EMBEDDING_MODEL_NAME, embed_passages, ensure_collection, get_embedder, get_qdrant

LOTE = 64


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python -m app.reembeber <colección origen>")
    origen = sys.argv[1]
    if origen == COLLECTION_NAME:
        raise SystemExit("Origen y destino son la misma colección: define QDRANT_COLLECTION con el nombre nuevo.")

    client = get_qdrant()
    dimension = get_embedder().get_sentence_embedding_dimension()
    ensure_collection(dimension)
    destino = client.get_collection(COLLECTION_NAME).config.params.vectors.size
    if destino != dimension:
        raise SystemExit(f"{COLLECTION_NAME} tiene vectores de {destino} dimensiones y {EMBEDDING_MODEL_NAME} produce {dimension}.")

    total = client.count(origen).count
    hechos, offset, t0 = 0, None, time.time()
    while True:
        puntos, offset = client.scroll(origen, limit=LOTE, offset=offset, with_payload=True)
        ya_estan = {p.id for p in client.retrieve(COLLECTION_NAME, ids=[p.id for p in puntos])}
        nuevos = [p for p in puntos if p.id not in ya_estan]
        if nuevos:
            vectores = embed_passages([p.payload.get("texto", "") for p in nuevos])
            client.upsert(
                COLLECTION_NAME,
                points=[qmodels.PointStruct(id=p.id, vector=v.tolist(), payload=p.payload) for p, v in zip(nuevos, vectores)],
            )
        hechos += len(puntos)
        if hechos % (LOTE * 16) < LOTE or offset is None:
            print(f"{hechos}/{total} fragmentos ({time.time() - t0:.0f} s)", flush=True)
        if offset is None:
            break

    print(f"Listo: {client.count(COLLECTION_NAME).count} puntos en {COLLECTION_NAME} con {EMBEDDING_MODEL_NAME}.")


if __name__ == "__main__":
    main()
