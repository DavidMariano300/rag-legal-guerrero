"""Script de ingesta para el spike local.

Uso: docker compose exec backend python -m app.ingest

Lee fixtures/sample_corpus.md (datos ficticios de prueba), lo trocea por artículo,
genera embeddings y los carga a Qdrant. No usar con el corpus legal real sin antes
adaptar el parseo al formato real de las fuentes oficiales.
"""

import re
from pathlib import Path

from qdrant_client.http import models as qmodels

from app.rag import COLLECTION_NAME, ensure_collection, get_embedder, get_qdrant

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "sample_corpus.md"


def parse_articles(raw_text: str) -> list[dict]:
    chunks = re.split(r"\n(?=## )", raw_text)
    articles = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.startswith("## "):
            continue
        title_line, _, body = chunk.partition("\n")
        articles.append({"fuente": title_line.replace("## ", "").strip(), "texto": body.strip()})
    return articles


def main() -> None:
    raw_text = FIXTURE_PATH.read_text(encoding="utf-8")
    articles = parse_articles(raw_text)
    print(f"Encontrados {len(articles)} artículos de prueba en {FIXTURE_PATH.name}")

    embedder = get_embedder()
    vector_size = embedder.get_sentence_embedding_dimension()
    ensure_collection(vector_size)

    client = get_qdrant()
    points = []
    for idx, article in enumerate(articles):
        vector = embedder.encode(f"passage: {article['texto']}").tolist()
        points.append(
            qmodels.PointStruct(
                id=idx,
                vector=vector,
                payload={"texto": article["texto"], "fuente": article["fuente"]},
            )
        )

    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"Indexados {len(points)} fragmentos en la colección '{COLLECTION_NAME}' de Qdrant.")


if __name__ == "__main__":
    main()
