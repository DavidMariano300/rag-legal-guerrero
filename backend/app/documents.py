"""Subida de documentos para consulta ad-hoc (NO se indexan en el corpus legal permanente).

Cada documento subido se asocia a un session_id generado por el frontend (una pestaña de
navegador = una sesión). Los fragmentos se guardan en una colección de Qdrant separada de
la del corpus legal ('session_documents'), y solo se recuperan cuando la consulta trae ese
mismo session_id — un usuario nunca puede ver los documentos subidos por otro.

No se guarda el archivo original, solo el texto extraído y troceado. Se purgan
automáticamente pasadas SESSION_DOCUMENT_TTL_SECONDS (ver iniciar_limpieza_periodica).
"""

import asyncio
import io
import logging
import os
import re
import time

from fastapi import HTTPException, UploadFile
from pypdf import PdfReader
from docx import Document as DocxDocument
from qdrant_client.http import models as qmodels
from rank_bm25 import BM25Okapi

from app.rag import embed_passages, embed_query, get_embedder, get_qdrant, stable_point_id

logger = logging.getLogger(__name__)

SESSION_COLLECTION_NAME = os.environ.get("QDRANT_SESSION_COLLECTION", "session_documents")  # una por modelo, como COLLECTION_NAME
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB
CHUNK_SIZE_CHARS = 1200
CHUNK_OVERLAP_CHARS = 150
MAX_FRAGMENTOS_SESION = 5000  # tope del scroll para BM25 (una ley grande ≈ 3000 fragmentos)
MIN_ARTICULOS_LEY = 3  # menos que eso: no es una ley, se trocea por tamaño

SESSION_DOCUMENT_TTL_SECONDS = int(os.environ.get("SESSION_DOCUMENT_TTL_SECONDS", str(24 * 3600)))
CLEANUP_INTERVAL_SECONDS = int(os.environ.get("SESSION_CLEANUP_INTERVAL_SECONDS", str(3600)))


def _validar_contenido_real(filename: str, content: bytes) -> None:
    """Verifica los 'magic bytes' del contenido, no solo la extensión declarada.

    Evita que un archivo renombrado (ej. algo.exe renombrado a algo.pdf) pase la validación
    solo por su nombre — un chequeo de extensión por sí solo es trivial de burlar.
    """
    suffix = filename.lower()
    if suffix.endswith(".pdf") and not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="El archivo no es un PDF válido.")
    if suffix.endswith(".docx") and not content.startswith(b"PK\x03\x04"):
        raise HTTPException(status_code=400, detail="El archivo no es un DOCX válido.")


def _extract_text(filename: str, content: bytes) -> str:
    _validar_contenido_real(filename, content)
    suffix = filename.lower()
    if suffix.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix.endswith(".docx"):
        doc = DocxDocument(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    if suffix.endswith(".txt"):
        return content.decode("utf-8", errors="ignore")
    raise HTTPException(status_code=400, detail="Formato de archivo no soportado.")


def _chunk_text(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE_CHARS
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP_CHARS
    return chunks


def _fragmentar(text: str) -> list[tuple[str | None, str]]:
    """Por artículo si el documento es una ley; si no, en trozos fijos.

    Con trozos fijos y la fuente "Documento subido: X" sin número de artículo, la verificación de citas
    (rag.verificar_citas) rechazaba toda cita etiquetada "(Artículo N)" de un documento subido.
    """
    from app.ingest_leyes import parse_articulos

    articulos = parse_articulos(text)
    if len(articulos) >= MIN_ARTICULOS_LEY:
        return [
            (a["titulo"] + (f" (parte {a['parte']} de {a['partes']})" if a["partes"] > 1 else ""), a["texto"])
            for a in articulos
        ]
    return [(None, chunk) for chunk in _chunk_text(text)]


def _ensure_session_collection(vector_size: int) -> None:
    client = get_qdrant()
    if not client.collection_exists(SESSION_COLLECTION_NAME):
        client.create_collection(
            collection_name=SESSION_COLLECTION_NAME,
            vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
        )


async def procesar_subida(session_id: str, file: UploadFile) -> dict:
    filename = file.filename or "documento"
    if not any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"Extensión no permitida. Formatos aceptados: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="El archivo excede el tamaño máximo permitido (15 MB).")

    text = _extract_text(filename, content)
    chunks = _fragmentar(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="No se pudo extraer texto legible del documento.")

    embedder = get_embedder()
    vector_size = embedder.get_sentence_embedding_dimension()
    _ensure_session_collection(vector_size)

    client = get_qdrant()
    vectores = embed_passages([texto for _, texto in chunks])
    points = []
    for idx, ((articulo, chunk), vector) in enumerate(zip(chunks, vectores)):
        point_id_seed = f"{session_id}:{filename}:{idx}"
        points.append(
            qmodels.PointStruct(
                id=stable_point_id(point_id_seed),
                vector=vector.tolist(),
                payload={
                    "session_id": session_id,
                    "filename": filename,
                    "articulo": articulo,
                    "texto": chunk,
                    "chunk_index": idx,
                    "uploaded_at": time.time(),
                },
            )
        )

    client.upsert(collection_name=SESSION_COLLECTION_NAME, points=points)
    return {"filename": filename, "fragmentos_indexados": len(points)}


def retrieve_session_fragments(session_id: str, question: str, top_k: int = 2) -> list[dict]:
    """Los top_k de BM25 + los top_k vectoriales de los documentos de la sesión (mismo criterio que
    hybrid_search.buscar_hibrido: en leyes los cosenos se amontonan y el vector solo no basta)."""
    from app.retrieval.hybrid_search import _tokenizar

    client = get_qdrant()
    if not client.collection_exists(SESSION_COLLECTION_NAME):
        return []

    query_filter = qmodels.Filter(
        must=[qmodels.FieldCondition(key="session_id", match=qmodels.MatchValue(value=session_id))]
    )
    # ponytail: BM25 se arma en cada consulta; barato con los cientos de fragmentos de una sesión.
    puntos, _ = client.scroll(
        collection_name=SESSION_COLLECTION_NAME, scroll_filter=query_filter, limit=MAX_FRAGMENTOS_SESION, with_payload=True
    )
    if not puntos:
        return []

    scores = BM25Okapi([_tokenizar(p.payload.get("texto", "")) for p in puntos]).get_scores(_tokenizar(question))
    por_bm25 = [puntos[i] for i in sorted(range(len(puntos)), key=lambda i: scores[i], reverse=True)[:top_k] if scores[i] > 0]

    por_vector = client.query_points(
        collection_name=SESSION_COLLECTION_NAME,
        query=embed_query(question),
        query_filter=query_filter,
        limit=top_k,
    ).points

    elegidos = {p.id: p for p in por_bm25 + por_vector}
    return [
        {
            "texto": p.payload.get("texto"),
            "fuente": ", ".join(filter(None, [p.payload.get("articulo"), f"Documento subido: {p.payload.get('filename')}"])),
            "ley": "Documento subido por el usuario (no es corpus legal indexado)",
            "area": "Documento del usuario",
        }
        for p in elegidos.values()
    ]


def eliminar_documentos_sesion(session_id: str) -> None:
    client = get_qdrant()
    if not client.collection_exists(SESSION_COLLECTION_NAME):
        return

    client.delete(
        collection_name=SESSION_COLLECTION_NAME,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="session_id", match=qmodels.MatchValue(value=session_id))]
            )
        ),
    )


def purgar_documentos_expirados() -> None:
    client = get_qdrant()
    if not client.collection_exists(SESSION_COLLECTION_NAME):
        return

    cutoff = time.time() - SESSION_DOCUMENT_TTL_SECONDS
    client.delete(
        collection_name=SESSION_COLLECTION_NAME,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="uploaded_at", range=qmodels.Range(lt=cutoff))]
            )
        ),
    )


async def _cleanup_loop() -> None:
    while True:
        try:
            purgar_documentos_expirados()
        except Exception:
            logger.exception("Error al purgar documentos de sesión expirados")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


def iniciar_limpieza_periodica() -> None:
    """Debe llamarse una vez en el startup de FastAPI (requiere un event loop corriendo)."""
    asyncio.create_task(_cleanup_loop())
