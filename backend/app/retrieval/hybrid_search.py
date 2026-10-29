"""Búsqueda híbrida: BM25 (palabras clave) + vectores densos (semántica), con fusión ponderada.

Resuelve los Casos 4 y 5 de docs/diagnostico_rag.csv:
- Caso 4 (miopía semántica): la búsqueda puramente vectorial confundió "me van a cobrar...
  descontándome" con "indemnizaciones" (Art. 485) en vez de encontrar el artículo real sobre
  descuentos salariales (Art. 110). BM25 encuentra la palabra literal "descuentos" que el vector
  por sí solo no priorizó lo suficiente.
- Caso 5 (cebo numérico): la búsqueda vectorial se distrajo con los números "6" y "2" de la pregunta
  y trajo un artículo sobre días de descanso que menciona "seis días" (Art. 69), en vez del artículo
  real de vacaciones (Art. 76). BM25 encuentra la palabra literal "vacaciones", sin que los números
  de la pregunta interfieran en el score de palabras clave.

No se usa LangChain (EnsembleRetriever) — rank_bm25 es una librería pura Python sin dependencias
pesadas, y la fusión de scores es lo bastante simple de implementar y explicar sin esa capa extra
(ver docs/refactorizacion_rag.md para la justificación completa de esta decisión).
"""

import logging
import os
import re
import unicodedata

import snowballstemmer
from qdrant_client.http import models as qmodels
from rank_bm25 import BM25Okapi

from app.rag import COLLECTION_NAME, embed_query, get_qdrant

logger = logging.getLogger(__name__)

# BM25 hace coincidencia EXACTA de tokens — "quincena." y "quincena" son palabras distintas para un
# split() ingenuo. Bug real encontrado el 2026-09-25: la puntuación pegada a las palabras (signos de
# interrogación en español, puntos, paréntesis) inflaba el vocabulario con tokens espurios y bajaba
# la calidad de las coincidencias. Esta regex se queda solo con letras (incluye acentos/ñ) y dígitos.
_TOKEN_RE = re.compile(r"[a-záéíóúñü0-9]+")

# BM25 pesa más que el vector a propósito (medido 2026-10-10 sobre los Casos 2, 4, 5 y 6): con
# stemming, el artículo correcto es #1-2 en BM25, pero en el vectorial queda #4, #30 y #119 porque
# en este corpus todos los cosenos se amontonan entre 0.78 y 0.90. 0.6/0.4 → 4/4 casos; 0.4/0.6
# también 4/4 pero con el Art. 76 colgado en #3 (se caía en corridas reales); RRF → 2-3/4.
# ponytail: calibrado con 4 casos; recalibrar si cambia el modelo de embeddings o el corpus.
PESO_BM25 = float(os.environ.get("PESO_BM25", "0.6"))
PESO_VECTORIAL = float(os.environ.get("PESO_VECTORIAL", "0.4"))

# Cuántos candidatos se traen de CADA LADO antes de fusionar. Los candidatos de BM25 que no salen
# en el pool vectorial reciben su coseno real (ver buscar_hibrido), así que el tamaño ya no decide
# si un artículo "pierde" la fusión; 100 sigue siendo barato con ~1300 documentos.
POOL_CANDIDATOS = 100
MAX_DEFINICIONES = 2

_bm25_index: BM25Okapi | None = None
_bm25_payloads: list[dict] | None = None
_bm25_ids: list[int] | None = None


# Stemming en español: sin él, "descuento" ≠ "descuentos" y "salario" ≠ "salarios" para BM25.
# Regresión real (2026-10-10, Caso 4): al cambiar a qwen la reescritura dijo "descuento salarial"
# y el Art. 110 ("Los descuentos en los salarios…") dejó de aparecer.
_STEMMER = snowballstemmer.stemmer("spanish")


def _tokenizar(texto: str) -> list[str]:
    return _STEMMER.stemWords(_TOKEN_RE.findall(texto.lower()))


# Palabras que aparecen en casi todos los nombres de capítulo y no distinguen un régimen de otro.
_STEMS_GENERICOS = set(_tokenizar("trabajo trabajadores personas de los las del la el en y a otros semejantes"))


# Cómo se dice en la calle lo que la ley llama de otro modo. Caso real (2026-10-26): "Trabajo en casa de
# una familia y vivo ahí" se reescribía como "trabajo doméstico", nunca "hogar", y el filtro descartaba
# el Art. 333 aunque era 2º en BM25 y en el vector.
_SINONIMOS_REGIMEN = {"Personas Trabajadoras del Hogar": "doméstico doméstica domésticos domésticas"}


def _regimen_aplica(pregunta_stems: set[str], capitulo_especial: str | None) -> bool:
    """Un artículo de Trabajos Especiales solo aplica si la pregunta nombra su régimen.

    Caso 5: "¿me tocan 8 días de vacaciones?" traía el Art. 199 (vacaciones de marinos) y el
    modelo lo aplicaba a un trabajador general. "Soy trabajadora del hogar..." sí debe traer el
    capítulo del hogar.
    """
    if not capitulo_especial:
        return True
    nombres = f"{capitulo_especial} {_SINONIMOS_REGIMEN.get(capitulo_especial, '')}"
    return bool((set(_tokenizar(nombres)) - _STEMS_GENERICOS) & pregunta_stems)


# --- Ley mencionada en la pregunta ---
# "¿Cuál es el objeto de la Ley Nacional para Eliminar Trámites Burocráticos?": con 154 leyes, el Art. 1
# de la LNETB quedaba 34º en BM25 y 35º en el vector (todas las leyes tienen un Art. 1 con "objeto").
# Si la pregunta nombra una ley del corpus, se busca solo dentro de ella.
_RELLENO_NOMBRE = re.compile(
    r"\b(?:del estado(?: libre y soberano)? de guerrero|para el estado(?: libre y soberano)? de guerrero"
    r"|n[uú]m(?:ero)?\.?\s*\d+|no\.\s*\d+|\(.*?\))"
)
_PALABRAS_SIN_SIGLA = {"de", "del", "la", "las", "los", "el", "y", "para", "en", "a", "por", "que", "sus"}
_alias_leyes: list[tuple[str, str]] | None = None  # (alias normalizado o sigla, nombre de la ley)


def _sin_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _alias(nombre: str) -> list[str]:
    completo = " ".join(_sin_acentos(nombre).split())
    corto = " ".join(_RELLENO_NOMBRE.sub(" ", completo).replace(",", " ").split()).strip(" .")
    palabras = [w for w in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]+", corto) if w not in _PALABRAS_SIN_SIGLA]
    sigla = "".join(w[0] for w in palabras).upper()
    alias = [completo] + ([corto] if len(corto.split()) >= 2 and len(corto) >= 10 else [])
    return alias + ([f"SIGLA:{sigla}"] if len(sigla) >= 3 else [])


def ley_mencionada(pregunta: str) -> str | None:
    """Nombre de la ley del corpus que la pregunta menciona (completo, corto o en siglas), o None."""
    global _alias_leyes
    if _alias_leyes is None:
        construir_indice_bm25()
        leyes = {p.get("ley") for p in _bm25_payloads if p.get("ley")}
        _alias_leyes = [(a, ley) for ley in leyes for a in _alias(ley)]
    texto, siglas = _sin_acentos(pregunta), set(re.findall(r"\b[A-Z]{3,}\b", pregunta))
    if "estados unidos mexicanos" in texto:
        return None  # la Constitución federal no está en el corpus: no confundirla con la de Guerrero
    hallazgos = [
        (len(a), ley) for a, ley in _alias_leyes
        if (a.startswith("SIGLA:") and a[6:] in siglas) or (not a.startswith("SIGLA:") and re.search(rf"\b{re.escape(a)}\b", texto))
    ]
    if not hallazgos:
        return None
    mejor = max(hallazgos)[0]
    leyes = {ley for largo, ley in hallazgos if largo == mejor}
    return leyes.pop() if len(leyes) == 1 else None  # dos leyes con el mismo alias: no se adivina


def construir_indice_bm25(forzar: bool = False) -> None:
    """Construye (o reconstruye) el índice BM25 leyendo TODO el corpus desde Qdrant.

    Se cachea en memoria por la vida del proceso — si el corpus cambia (nueva ingesta), hay que
    llamar con forzar=True o reiniciar el backend para que el índice de palabras clave se entere.
    Misma limitación que ya tienen los singletons de embedder/cliente de Qdrant en rag.py.
    """
    global _bm25_index, _bm25_payloads, _bm25_ids

    if _bm25_index is not None and not forzar:
        return

    client = get_qdrant()
    payloads: list[dict] = []
    ids: list[int] = []
    offset = None
    while True:
        puntos, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in puntos:
            payloads.append(p.payload)
            ids.append(p.id)
        if offset is None:
            break

    corpus_tokenizado = [_tokenizar(p.get("texto", "")) for p in payloads]
    _bm25_index = BM25Okapi(corpus_tokenizado)
    _bm25_payloads = payloads
    _bm25_ids = ids
    logger.info("Índice BM25 construido con %d documentos.", len(payloads))


def payloads_corpus() -> list[dict]:
    """Los payloads de todo el corpus, ya cargados para BM25 (los usa app/vigencia.py)."""
    construir_indice_bm25()
    return _bm25_payloads


def _normalizar(valores: list[float]) -> list[float]:
    """Min-max a [0, 1]. Si todos los valores son iguales, devuelve ceros (evita división por 0)."""
    if not valores:
        return []
    minimo, maximo = min(valores), max(valores)
    if maximo == minimo:
        return [0.0 for _ in valores]
    return [(v - minimo) / (maximo - minimo) for v in valores]


# "¿Qué es / qué se entiende por X?": la respuesta es una fracción de glosario ("XXXV. Trámite: ...").
# Caso real: "¿Qué se entiende por trámite en la LNETB?" no traía el Art. 3, porque dentro de esa ley
# "trámite" aparece en casi todos los artículos y ni BM25 ni el vector distinguían la definición.
_DEFINICION_RE = re.compile(
    r"^\W*qu[eé]\s+(?:es|son|significa|se\s+entiende\s+por)\s+(?:el|la|los|las|un|una)?\s*(.+?)"
    r"(?:\s+(?:seg[uú]n|en|de\s+acuerdo\s+con|para)\s+(?:la|el|los|las)\b.*)?\W*$",
    re.IGNORECASE,
)


def _termino_a_definir(pregunta: str) -> str | None:
    m = _DEFINICION_RE.match(pregunta.strip())
    return _sin_acentos(m.group(1)).strip() if m and len(m.group(1)) <= 60 else None


def buscar_hibrido(
    pregunta: str,
    area: str | None = None,
    top_k: int = 3,
    top_k_vector: int | None = None,
    pregunta_original: str | None = None,
    top_k_original: int = 2,
) -> list[dict]:
    """Combina BM25 (palabras clave) y búsqueda vectorial (semántica) con fusión ponderada.

    `pregunta` es la consulta de búsqueda (pregunta + términos de la reescritura); con
    `pregunta_original` se hace además una búsqueda vectorial con la pregunta sola y se suman sus
    `top_k_original` mejores. Medido en los 21 casos de eval/casos.json: la reescritura acerca la
    terminología (Art. 110: 21º → 1º) pero diluye el sentido de otras preguntas ("¿me puedo casar a los
    17?": Art. 412 2º con la pregunta sola, 11º con la reescritura); tomar ambas cubre los dos casos.

    El umbral de "no hay candidatos suficientemente relevantes" no se aplica aquí sobre el score
    fusionado (BM25 crudo y coseno no son comparables en escala antes de normalizar) — se apoya en
    el system prompt (backend/app/prompts/system_prompt_v2.txt) para rechazar cuando el mejor
    candidato disponible igual no corresponde al tema preguntado.
    """
    construir_indice_bm25()
    assert _bm25_index is not None and _bm25_payloads is not None and _bm25_ids is not None

    id_a_indice = {pid: idx for idx, pid in enumerate(_bm25_ids)}

    # La ley nombrada en la pregunta manda sobre el área elegida: el usuario dijo explícitamente dónde buscar.
    ley = ley_mencionada(pregunta_original or pregunta)
    if ley:
        query_filter = qmodels.Filter(must=[qmodels.FieldCondition(key="ley", match=qmodels.MatchValue(value=ley))])
    elif area:
        query_filter = qmodels.Filter(must=[qmodels.FieldCondition(key="area", match=qmodels.MatchValue(value=area))])
    else:
        query_filter = None

    def admitido(i: int) -> bool:
        payload = _bm25_payloads[i]
        return payload.get("ley") == ley if ley else (not area or payload.get("area") == area)

    # --- Lado BM25 ---
    scores_bm25_crudos = _bm25_index.get_scores(_tokenizar(pregunta))

    candidatos: dict[int, dict[str, float]] = {}
    # El filtro va ANTES del top: con un corpus multi-ley, filtrar después dejaría que leyes de
    # otras áreas ocupen los 100 lugares del pool y la del área pedida no entre.
    indices_filtrados = [i for i in range(len(scores_bm25_crudos)) if admitido(i)]
    indices_bm25_top = sorted(indices_filtrados, key=lambda i: scores_bm25_crudos[i], reverse=True)[:POOL_CANDIDATOS]
    for i in indices_bm25_top:
        if scores_bm25_crudos[i] <= 0:
            continue
        candidatos[i] = {"bm25": float(scores_bm25_crudos[i]), "vector": 0.0, "original": 0.0}

    # --- Lado vectorial (reusa el mismo embedder y colección que rag.py) ---
    consultas = {"vector": embed_query(pregunta)}
    if pregunta_original and pregunta_original != pregunta:
        consultas["original"] = embed_query(pregunta_original)

    client = get_qdrant()
    for clave, vector in consultas.items():
        for hit in client.query_points(
            collection_name=COLLECTION_NAME, query=vector, query_filter=query_filter, limit=POOL_CANDIDATOS
        ).points:
            idx = id_a_indice.get(hit.id)
            if idx is None:
                continue  # documento nuevo desde que se construyó el índice — requiere reconstruir
            candidatos.setdefault(idx, {"bm25": float(scores_bm25_crudos[idx]), "vector": 0.0, "original": 0.0})
            candidatos[idx][clave] = hit.score

    pregunta_stems = set(_tokenizar(f"{pregunta} {pregunta_original or ''}"))
    candidatos = {
        i: c for i, c in candidatos.items()
        if _regimen_aplica(pregunta_stems, _bm25_payloads[i].get("capitulo_especial"))
    }

    # Candidatos que una consulta no encontró: pedir su coseno REAL, no asumir 0. En este corpus los
    # cosenos se amontonan, así que quedar fuera del top-N vectorial no es "irrelevante" (Caso 4: Art. 110
    # tenía coseno 0.852 pero quedaba fuera del top 100 y con 0 perdía la fusión).
    for clave, vector in consultas.items():
        faltantes = [_bm25_ids[i] for i, c in candidatos.items() if c[clave] == 0.0]
        if faltantes:
            for hit in client.query_points(
                collection_name=COLLECTION_NAME,
                query=vector,
                query_filter=qmodels.Filter(must=[qmodels.HasIdCondition(has_id=faltantes)]),
                limit=len(faltantes),
            ).points:
                candidatos[id_a_indice[hit.id]][clave] = hit.score

    if not candidatos:
        return []

    indices = list(candidatos.keys())
    bm25_norm = _normalizar([candidatos[i]["bm25"] for i in indices])
    vector_norm = _normalizar([max(candidatos[i]["vector"], candidatos[i]["original"]) for i in indices])
    fusion = {idx: PESO_BM25 * b + PESO_VECTORIAL * v for idx, b, v in zip(indices, bm25_norm, vector_norm)}

    # Se devuelven los top de CADA señal (sin duplicados), no los top fusionados: ningún peso fijo
    # sirvió para todos los casos — con más peso a BM25 se perdía el Art. 518 del Caso 1 (vectorial #2,
    # BM25 #145); con más peso al vector, el Art. 76 del Caso 5 (BM25 #1, vectorial #30). El score
    # fusionado solo ordena; el LLM elige entre los candidatos.
    elegidos = set(sorted(indices, key=lambda i: candidatos[i]["bm25"], reverse=True)[:top_k])
    elegidos |= set(sorted(indices, key=lambda i: candidatos[i]["vector"], reverse=True)[:top_k_vector or top_k])
    if "original" in consultas:
        elegidos |= set(sorted(indices, key=lambda i: candidatos[i]["original"], reverse=True)[:top_k_original])

    termino = _termino_a_definir(pregunta_original or pregunta)
    definiciones: set[int] = set()
    if termino:
        formas = {f"{termino}:", f"{termino.rstrip('s')}:"}
        definiciones = {
            i for i in indices_filtrados
            if any(forma in _sin_acentos(_bm25_payloads[i].get("texto", "")) for forma in formas)
        }
        definiciones = set(sorted(definiciones)[:MAX_DEFINICIONES])
        for i in definiciones:  # pueden no estar entre los candidatos de ninguna señal
            candidatos.setdefault(i, {"bm25": float(scores_bm25_crudos[i]), "vector": 0.0, "original": 0.0})
            fusion.setdefault(i, 0.0)
        elegidos |= definiciones

    # Orden: cada fragmento por su MEJOR lugar en cualquier señal (luego por fusión). Con el orden por
    # fusión, el Art. 412 ("¿me puedo casar a los 17?") quedaba último de 7 aunque era 2º con la pregunta
    # sola, y el modelo rechazaba al ver primero 6 fragmentos ajenos.
    mejor_lugar: dict[int, int] = {}
    for clave in ("bm25", "vector", "original"):
        if clave == "original" and "original" not in consultas:
            continue
        for lugar, i in enumerate(sorted(indices, key=lambda i: candidatos[i][clave], reverse=True), start=1):
            mejor_lugar[i] = min(mejor_lugar.get(i, lugar), lugar)
    for i in definiciones:
        mejor_lugar[i] = 0  # la definición literal va primero

    resultados = []
    for idx in sorted(elegidos, key=lambda i: (mejor_lugar[i], -fusion[i])):
        payload = _bm25_payloads[idx]
        resultados.append(
            {
                "texto": payload.get("texto"),
                "fuente": payload.get("fuente"),
                "ley": payload.get("ley"),
                "area": payload.get("area"),
                "score": round(fusion[idx], 4),
            }
        )
    return resultados
