"""Subida de documentos para consulta ad-hoc (NO se indexan en el corpus legal permanente).

Cada documento subido se asocia a un session_id generado por el frontend (una pestaña de
navegador = una sesión). Los fragmentos se guardan en una colección de Qdrant separada de
la del corpus legal ('session_documents'), y solo se recuperan cuando la consulta trae ese
mismo session_id — un usuario nunca puede ver los documentos subidos por otro.

No se guarda el archivo original, solo el texto extraído y trceado. No hay expiración
automática todavía (ver docs/manual_ingenieria_software.md, roadmap).
"""

import io
import re

from fastapi import HTTPException, UploadFile
from pypdf import PdfReader
from docx import Document as DocxDocument
from qdrant_client.http import models as qmodels

from app.rag import get_embedder, get_qdrant

SESSION_COLLECTION_NAME = "session_documents"
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB
CHUNK_SIZE_CHARS = 1200
CHUNK_OVERLAP_CHARS = 150


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
    chunks = _chunk_text(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="No se pudo extraer texto legible del documento.")

    embedder = get_embedder()
    vector_size = embedder.get_sentence_embedding_dimension()
    _ensure_session_collection(vector_size)

    client = get_qdrant()
    points = []
    for idx, chunk in enumerate(chunks):
        vector = embedder.encode(f"passage: {chunk}").tolist()
        point_id_seed = f"{session_id}:{filename}:{idx}"
        points.append(
            qmodels.PointStruct(
                id=abs(hash(point_id_seed)) % (2**63),
                vector=vector,
                payload={
                    "session_id": session_id,
                    "filename": filename,
                    "texto": chunk,
                    "chunk_index": idx,
                },
            )
        )

    client.upsert(collection_name=SESSION_COLLECTION_NAME, points=points)
    return {"filename": filename, "fragmentos_indexados": len(points)}


def retrieve_session_fragments(session_id: str, question: str, top_k: int = 3) -> list[dict]:
    client = get_qdrant()
    if not client.collection_exists(SESSION_COLLECTION_NAME):
        return []

    embedder = get_embedder()
    query_vector = embedder.encode(f"query: {question}").tolist()

    query_filter = qmodels.Filter(
        must=[qmodels.FieldCondition(key="session_id", match=qmodels.MatchValue(value=session_id))]
    )

    hits = client.query_points(
        collection_name=SESSION_COLLECTION_NAME,
        query=query_vector,
        query_filter=query_filter,
        limit=top_k,
    ).points

    return [
        {
            "texto": hit.payload.get("texto"),
            "fuente": f"Documento subido: {hit.payload.get('filename')}",
            "area": "Documento del usuario",
            "score": hit.score,
        }
        for hit in hits
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
