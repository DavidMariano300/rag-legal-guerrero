"""Ingesta de la Ley Federal del Trabajo (texto REAL, oficial) — primer corpus real del proyecto.

Fuente única y verificable: el PDF oficial de la Cámara de Diputados del H. Congreso de la Unión
(https://www.diputados.gob.mx/LeyesBiblio/pdf/LFT.pdf). Se descarga en cada ejecución en vez de
guardarse en el repo, para no versionar un binario y para que siempre se use el texto vigente más
reciente publicado por la fuente oficial (el mismo patrón que ya usamos para el modelo de Ollama y
la voz de Piper: descargar el artefacto real en vez de copiarlo a mano).

Qué NO se ingiere: la sección de "TRANSITORIOS" del decreto original y el archivo histórico de
decretos de reforma que el PDF incluye al final — son historial legislativo, no el texto sustantivo
vigente que un abogado consultaría. El corte se hace en la primera aparición de "TRANSITORIOS"
después del cuerpo de artículos (verificado manualmente contra el PDF real antes de escribir esto,
ver docs/spike_resultados.md).

Uso: docker compose exec backend python -m app.ingest_lft
"""

import io
import re

import httpx
from qdrant_client.http import models as qmodels

from app.rag import COLLECTION_NAME, embed_passages, ensure_collection, get_embedder, get_qdrant, stable_point_id

LFT_URL = "https://www.diputados.gob.mx/LeyesBiblio/pdf/LFT.pdf"
FUENTE_LABEL = "Ley Federal del Trabajo (texto vigente, Cámara de Diputados del H. Congreso de la Unión)"

_HEADER_PATTERN = re.compile(
    r"LEY FEDERAL DEL TRABAJO\s*"
    r"CÁMARA DE DIPUTADOS DEL H\. CONGRESO DE LA UNIÓN\s*"
    r"Secretaría General\s*"
    r"Secretaría de Servicios Parlamentarios\s*"
    r"Última Reforma DOF [0-9\-]+\s*"
    r"(?:\d+ de \d+)?\s*",
    re.MULTILINE,
)

_ARTICLE_PATTERN = re.compile(
    r"(?m)^Art[ií]culo\s+([0-9]+(?:\s*o\.?)?(?:\s*(?:-\s*[A-ZÑ]|Bis|Ter|Qu[aá]ter|Quinquies))*)"
    r"\s*[.\-–]+\s*-?\s*"
)


def _descargar_pdf() -> bytes:
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        response = client.get(LFT_URL)
        response.raise_for_status()
        return response.content


def _extraer_texto(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _cuerpo_sustantivo(texto_completo: str) -> str:
    corte = texto_completo.find("\nTRANSITORIOS")
    if corte == -1:
        raise ValueError(
            "No se encontró el marcador 'TRANSITORIOS' esperado — el formato del PDF pudo haber "
            "cambiado desde la última verificación manual. Revisar antes de ingerir."
        )
    return _HEADER_PATTERN.sub("\n", texto_completo[:corte])


# Encabezados reales del PDF (verificados 2026-10-10): "TITULO SEXTO\nTrabajos Especiales",
# "CAPITULO III\nTrabajadores de los buques" — el nombre va en la línea siguiente.
_TITULO_PATTERN = re.compile(r"(?m)^\s*T[IÍ]TULO\s+[A-ZÉÍÓÚ]+(?:\s+BIS)?\s*\n(.*)")
_CAPITULO_PATTERN = re.compile(r"(?m)^\s*CAP[IÍ]TULO\s+[IVXLC]+(?:\s+BIS)?\s*\n(.*)")
TITULO_REGIMEN_ESPECIAL = "Trabajos Especiales"


def _ultimo_antes(encabezados: list[tuple[int, str]], posicion: int) -> tuple[int, str] | None:
    previos = [e for e in encabezados if e[0] < posicion]
    return previos[-1] if previos else None


def parse_articulos(texto_completo: str) -> list[dict]:
    cuerpo = _cuerpo_sustantivo(texto_completo)
    matches = list(_ARTICLE_PATTERN.finditer(cuerpo))
    titulos = [(m.start(), m.group(1).strip()) for m in _TITULO_PATTERN.finditer(cuerpo)]
    capitulos = [(m.start(), m.group(1).strip()) for m in _CAPITULO_PATTERN.finditer(cuerpo)]

    articulos = []
    for idx, match in enumerate(matches):
        etiqueta = re.sub(r"\s+", " ", match.group(1)).strip()
        inicio_cuerpo = match.end()
        fin_cuerpo = matches[idx + 1].start() if idx + 1 < len(matches) else len(cuerpo)
        cuerpo_articulo = re.sub(r"\s+", " ", cuerpo[inicio_cuerpo:fin_cuerpo]).strip()

        if not cuerpo_articulo:
            continue

        # Artículos del Título Sexto guardan el nombre de su capítulo (régimen especial: buques,
        # hogar, plataformas digitales...) para no usarlos en preguntas generales — ver hybrid_search.
        titulo = _ultimo_antes(titulos, match.start())
        capitulo = _ultimo_antes(capitulos, match.start())
        capitulo_especial = None
        if titulo and titulo[1] == TITULO_REGIMEN_ESPECIAL and capitulo and capitulo[0] > titulo[0]:
            capitulo_especial = capitulo[1]

        articulos.append({"numero": etiqueta, "texto": cuerpo_articulo, "capitulo_especial": capitulo_especial})

    return articulos


def main() -> None:
    print(f"Descargando texto oficial desde {LFT_URL} ...")
    pdf_bytes = _descargar_pdf()
    print(f"Descargado ({len(pdf_bytes) / 1024:.0f} KB). Extrayendo texto...")

    texto_completo = _extraer_texto(pdf_bytes)
    articulos = parse_articulos(texto_completo)
    print(f"Parseados {len(articulos)} artículos sustantivos (excluye transitorios e historial de reformas).")

    embedder = get_embedder()
    vector_size = embedder.get_sentence_embedding_dimension()
    ensure_collection(vector_size)

    client = get_qdrant()
    points = []
    for articulo in articulos:
        vector = embed_passages([articulo["texto"]])[0].tolist()
        points.append(
            qmodels.PointStruct(
                id=stable_point_id(f"LFT:{articulo['numero']}"),
                vector=vector,
                payload={
                    "texto": articulo["texto"],
                    "fuente": f"Artículo {articulo['numero']}, {FUENTE_LABEL}",
                    "area": "Laboral",
                    "ley": "Ley Federal del Trabajo",
                    "capitulo_especial": articulo["capitulo_especial"],
                },
            )
        )

    # Subida por lotes: 1264 artículos de una sola vez puede exceder límites de payload de Qdrant.
    LOTE = 100
    for i in range(0, len(points), LOTE):
        client.upsert(collection_name=COLLECTION_NAME, points=points[i : i + LOTE])
        print(f"  Indexados {min(i + LOTE, len(points))}/{len(points)}...")

    print(f"Listo. {len(points)} artículos reales de la Ley Federal del Trabajo indexados en '{COLLECTION_NAME}'.")


if __name__ == "__main__":
    main()
