import hashlib
import logging
import os
import re
import time
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

QDRANT_HOST = os.environ.get("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:4b")
# Modelos con "pensamiento" (Qwen3.5): OLLAMA_THINK=false lo apaga en las tres llamadas al LLM. Sin esto,
# la reescritura (num_predict 60) se gastaba los tokens pensando y devolvía vacío. Sin definir no se
# envía nada: los modelos sin pensamiento (y el Ollama 0.3.14 del contenedor) no conocen la opción.
_THINK = os.environ.get("OLLAMA_THINK")
OLLAMA_OPCIONES_MODELO = {"think": _THINK == "true"} if _THINK in ("true", "false") else {}
# Pensar solo en la respuesta final (no en la reescritura ni en la extracción de datos): mejora el
# razonamiento sobre requisitos ("tengo 25 años, ¿puedo adoptar?"), pero cuesta ~3,000 tokens; solo es
# viable con GPU (docs/investigacion_nube_gpu.md).
PENSAR_RESPUESTA = os.environ.get("OLLAMA_THINK_RESPUESTA") == "true"
TOKENS_PENSAMIENTO = 6000
EMBEDDING_MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
# Cada modelo de embeddings tiene su propia colección (las dimensiones no coinciden: 384 en e5-small,
# 1024 en bge-m3). Cambiar de modelo = cambiar ambas variables; la colección anterior queda de respaldo.
COLLECTION_NAME = os.environ.get("QDRANT_COLLECTION", "legal_corpus_test")
# Prefijos que exige cada familia: e5 se entrenó con "query: "/"passage: " y rinde peor sin ellos;
# bge-m3 no usa ninguno. Un modelo que no esté aquí se usa sin prefijos.
_PREFIJOS_EMBEDDING = {
    "intfloat/multilingual-e5-small": ("query: ", "passage: "),
    "intfloat/multilingual-e5-base": ("query: ", "passage: "),
}
# Tope de tokens al embeber: los fragmentos son ≤ ~2000 caracteres (~600 tokens); sin tope, bge-m3
# acepta 8192 y un párrafo atípico se vuelve muy lento en CPU. e5 ya trae 512.
MAX_TOKENS_EMBEDDING = 1024
TOP_K = 2  # por señal (BM25 y vectorial): al LLM le llegan ≤ 4 fragmentos, ver buscar_hibrido
# Cuántos aporta el lado vectorial: con un modelo que ordena bien (bge-m3) el correcto suele quedar 1º-5º
# en el vector, y tomar solo 2 lo dejaba fuera. Ver docs/refactorizacion_rag.md §10.
TOP_K_VECTOR = int(os.environ.get("TOP_K_VECTOR", str(TOP_K)))

# NOTA HISTÓRICA: hasta el 2026-09-24 existía aquí un SCORE_THRESHOLD (umbral de similitud coseno)
# aplicado directamente sobre la búsqueda vectorial. Se retiró al migrar a búsqueda híbrida
# (app/retrieval/hybrid_search.py) porque el score fusionado (BM25 + coseno normalizados) ya no es
# comparable contra ese umbral crudo. El hallazgo que motivó documentar esto (el umbral de 0.75 no
# separaba de forma confiable preguntas relevantes de irrelevantes con este modelo de embeddings)
# sigue vigente y está documentado en docs/refactorizacion_rag.md — la defensa real contra
# alucinación por corpus insuficiente sigue siendo el SYSTEM_PROMPT de abajo.

REFUSAL_MESSAGE = "No cuento con la legislación necesaria en mi base de datos para responder a esta consulta."

# El prompt vive como archivo de texto versionado, no como string embebido en Python — así se puede
# iterar el prompt (revisarlo, compararlo en un diff, editarlo sin tocar código) sin duplicar contenido
# que se desincronice. Este archivo es la ÚNICA fuente de verdad del system prompt en producción.
_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "system_prompt_v2.txt"
SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8").format(REFUSAL_MESSAGE=REFUSAL_MESSAGE)

_embedder: SentenceTransformer | None = None
_qdrant: QdrantClient | None = None


def get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
        _embedder.max_seq_length = min(_embedder.max_seq_length or MAX_TOKENS_EMBEDDING, MAX_TOKENS_EMBEDDING)
    return _embedder


def embed_query(texto: str) -> list[float]:
    prefijo, _ = _PREFIJOS_EMBEDDING.get(EMBEDDING_MODEL_NAME, ("", ""))
    return get_embedder().encode(prefijo + texto).tolist()


def embed_passages(textos: list[str]):
    _, prefijo = _PREFIJOS_EMBEDDING.get(EMBEDDING_MODEL_NAME, ("", ""))
    return get_embedder().encode([prefijo + t for t in textos], batch_size=16)


def get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    return _qdrant


def stable_point_id(seed: str) -> int:
    """ID determinista para un punto de Qdrant a partir de un seed de texto.

    NUNCA usar hash() nativo de Python para esto: está aleatorizado por proceso
    (PYTHONHASHSEED), así que el mismo seed produce un ID distinto en cada
    reinicio del contenedor — romper la idempotencia del upsert y duplicar el
    corpus en cada re-ingesta (bug real encontrado el 2026-09-24: el corpus
    tenía 2532 puntos en vez de ~1268 por esta causa exacta).
    """
    return int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:15], 16)


def ensure_collection(vector_size: int) -> None:
    client = get_qdrant()
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
        )


# Ollama recorta por el PRINCIPIO un prompt más largo que su contexto (por defecto 2048 tokens en el
# Ollama 0.3.14 del contenedor, 4096 en el del host): conserva los 4 primeros tokens y borra los
# siguientes, que son el system prompt. Medido el 2026-10-26: 45 de 299 llamadas registradas llegaron
# truncadas ("input truncated n_ctx=2048 n_erase=1658"), o sea, sin reglas. Por eso el contexto se pide
# explícito y el prompt se arma para que quepa.
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
# Tope de espera de cada llamada a Ollama. En GPU sobra; en los 2 núcleos de la VM gratuita una respuesta pasa de
# 2 min, y la reescritura (que antes tenía 30 s) se cortaba en silencio: la recuperación bajaba de 94 % a 81 %.
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "120"))
MAX_TOKENS_RESPUESTA = 700  # tope de generación: un modelo pequeño puede entrar en bucle sin límite
_CHARS_POR_TOKEN = 3  # ponytail: estimación conservadora para español (~3.5–4 reales); sin tokenizador


def _armar_prompt(question: str, fragments: list[dict]) -> str:
    """El prompt completo, sin fragmentos de más: si no cabe en el contexto, se quitan los últimos (los de
    menor puntaje) y nunca el system prompt."""
    fragments = list(fragments)
    while True:
        context_block = "\n\n".join(f"[Fuente: {f['fuente']}]\n{f['texto']}" for f in fragments)
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"<contexto>\n{context_block}\n</contexto>\n\n"
            f"Pregunta del abogado: {question}\n\n"
            # Recordatorio al final a propósito: es lo último que lee el modelo. Sin él, qwen omitía las
            # citas en ~1 de cada 3 respuestas (regla 6 del system prompt) y verificar_citas las descartaba.
            f"Respuesta breve en texto plano (sin LaTeX), basada solo en el contexto anterior, que incluya "
            f"al menos una cita literal con el formato «texto copiado del fragmento» (Artículo N):"
        )
        if len(prompt) / _CHARS_POR_TOKEN + MAX_TOKENS_RESPUESTA <= OLLAMA_NUM_CTX or len(fragments) <= 1:
            return prompt
        logger.warning("El prompt no cabe en %d tokens: se omite el fragmento %s", OLLAMA_NUM_CTX, fragments[-1]["fuente"][:80])
        fragments.pop()


def generate_answer(question: str, fragments: list[dict]) -> str:
    prompt = _armar_prompt(question, fragments)

    with httpx.Client(timeout=600.0 if PENSAR_RESPUESTA else OLLAMA_TIMEOUT) as client:
        response = client.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                **(OLLAMA_OPCIONES_MODELO | ({"think": True} if PENSAR_RESPUESTA else {})),
                "prompt": prompt,
                "stream": False,
                # temperature baja (no cero: sigue siendo redacción, no una traducción mecánica) —
                # con la temperatura por defecto de Ollama (0.8) se midió que la MISMA pregunta con
                # el MISMO contexto podía evadir un cálculo en una corrida y resolverlo bien en la
                # siguiente (ver docs/refactorizacion_rag.md, caso 2). Para una herramienta de
                # consulta legal, la consistencia importa más que la variación creativa.
                "options": {
                    "temperature": 0.2,
                    # El pensamiento cuenta dentro de num_predict y del contexto: sin este margen, Qwen3.5
                    # agotaba el límite pensando y devolvía una respuesta vacía.
                    "num_ctx": OLLAMA_NUM_CTX + (TOKENS_PENSAMIENTO if PENSAR_RESPUESTA else 0),
                    "num_predict": MAX_TOKENS_RESPUESTA + (TOKENS_PENSAMIENTO if PENSAR_RESPUESTA else 0),
                },
            },
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()



# Cualquier estilo de comillas, con etiqueta (Artículo N) opcional: qwen pide «» en el prompt pero en
# la práctica usa "" en ~2 de cada 3 respuestas, y a veces omite la etiqueta. El formato es tolerante;
# lo que se exige es el CONTENIDO (ver verificar_citas).
FUENTE_CALCULO = "Cálculo determinista"
_CITA_RE = re.compile(r"(?:«([^»]+)»|\"([^\"]+)\"|“([^”]+)”)(?:\s*\(([^)]+)\))?")
_NUM_ARTICULO_RE = re.compile(r"\d+(?:\s*-?\s*(?:bis|ter|[a-z])\b)?", re.I)
_MIN_CITA_SUSTANCIAL = 20  # caracteres normalizados; «Sí» (Artículo 87) no respalda nada


def _normalizar_texto(s: str) -> str:
    # Sin espacios ni puntuación: el PDF trae artefactos como "independienteme nte" o "e rrores".
    return re.sub(r"[^a-z0-9áéíóúñü]", "", s.lower())


def _numero_articulo(s: str) -> str | None:
    """Número normalizado: 'Artículo 873-A, LFT' → '873a'; 'Ley Federal del Trabajo' → None."""
    m = _NUM_ARTICULO_RE.search(s)
    return re.sub(r"[\s-]", "", m.group().lower()) if m else None


def verificar_citas(respuesta: str, fragments: list[dict], pregunta: str = "") -> bool:
    """True si hay al menos una cita sustancial y todas las citas aparecen literalmente en el contexto.

    - Cita con etiqueta de artículo: debe estar en el fragmento de ESE artículo (bloquea la mala
      atribución y el Caso 3: le atribuyó al Art. 407 algo que no dice).
    - Cita sin etiqueta: debe estar en algún fragmento, o en la pregunta (el modelo cita las palabras
      del usuario). Las cortas sin etiqueta se ignoran: son énfasis, no fundamento.
    No verifica la prosa fuera de las comillas: un párrafo libre puede seguir siendo impreciso aunque
    las citas sean reales — es una barrera contra texto legal inventado, no contra el mal razonamiento.
    """
    verificadas = 0
    for m in _CITA_RE.finditer(respuesta):
        cita = next(g for g in m.groups()[:3] if g is not None)
        numero = _numero_articulo(m.group(4) or "")
        piezas = [p for p in (_normalizar_texto(p) for p in re.split(r"\.\.\.|…", cita)) if p]
        sustancial = sum(map(len, piezas)) >= _MIN_CITA_SUSTANCIAL
        if not numero and not sustancial:
            continue
        def contiene(texto: str) -> bool:
            texto = _normalizar_texto(texto)
            return all(p in texto for p in piezas)

        # El cálculo del sistema no lleva número de artículo, pero el modelo lo cita con la etiqueta del
        # artículo que aplica ("«con 3 año(s)... 16 días» (Artículo 76)"): su texto sigue siendo verificable.
        en_fragmento = any(
            contiene(f["texto"]) for f in fragments
            if numero is None or f["fuente"].startswith(FUENTE_CALCULO)
            or _numero_articulo(f["fuente"].split(",")[0]) == numero
        )
        if not en_fragmento and not (numero is None and contiene(pregunta)):
            logger.warning("Cita no respaldada, respuesta descartada: «%s» (%s)", cita[:80], m.group(4))
            return False
        verificadas += sustancial and en_fragmento  # citar al usuario no fundamenta nada
    if not verificadas:
        logger.warning("Respuesta descartada: no trae ninguna cita literal del contexto entre comillas.")
    return verificadas > 0


# --- Cita de respaldo para respuestas sin comillas ---
# Con el modo pensamiento, qwen3.5:4b responde bien pero sin comillas en ~1 de cada 3 respuestas (15 de 51 en
# la validación del 2026-10-26), y verificar_citas las descartaba. Si la respuesta NOMBRA un artículo que
# está en el contexto, se le agrega la oración literal de ese artículo que más se parece a la respuesta.
# No cambia la barrera contra texto inventado: una respuesta con comillas que no coinciden se sigue
# rechazando, y una que no nombra ningún artículo del contexto, también.
_ARTICULO_EN_PROSA_RE = re.compile(r"art[íi]culo\s+(\d+(?:\s*(?:bis|ter|qu[aá]ter|-?\s*[a-z]\b))?)", re.IGNORECASE)
_PALABRA_RE = re.compile(r"[a-záéíóúñü]{4,}")
_ORACION_RE = re.compile(r"[^.;:]{30,}?[.;:](?=\s|$)|[^.;:]{30,}$")
MIN_PALABRAS_EN_COMUN = 3


def cita_de_respaldo(respuesta: str, fragments: list[dict]) -> str | None:
    """La respuesta con una cita literal agregada del artículo que ella misma nombra, o None."""
    nombrados = {_numero_articulo(m) for m in _ARTICULO_EN_PROSA_RE.findall(respuesta)}
    candidatos = [f for f in fragments if _numero_articulo(f["fuente"].split(",")[0]) in nombrados]
    palabras = set(_PALABRA_RE.findall(respuesta.lower()))
    opciones = [
        (len(palabras & set(_PALABRA_RE.findall(oracion.lower()))), oracion.strip(), f["fuente"].split(",")[0])
        for f in candidatos for oracion in _ORACION_RE.findall(f["texto"])
    ]
    if not opciones:
        return None
    en_comun, oracion, articulo = max(opciones, key=lambda o: o[0])
    if en_comun < MIN_PALABRAS_EN_COMUN:
        return None
    return f"{respuesta}\n\nFundamento (cita agregada por el sistema): «{oracion}» ({articulo})"


AI_DISCLAIMER = (
    "Esta respuesta fue generada por un sistema de inteligencia artificial y puede "
    "contener errores u omisiones. Verifique siempre la información contra la fuente "
    "original antes de utilizarla en cualquier trámite o gestión legal."
)


def answer_query(question: str, area: str | None = None, extra_fragments: list[dict] | None = None) -> dict:
    # Imports diferidos: hybrid_search y query_rewriter importan de este mismo módulo (get_embedder,
    # get_qdrant, COLLECTION_NAME) — importarlos aquí adentro, no arriba del archivo, evita un import
    # circular sin necesitar un tercer módulo compartido solo para eso.
    from app import vigencia
    from app.calculos import calcular_si_aplica
    from app.retrieval.hybrid_search import buscar_hibrido
    from app.retrieval.query_rewriter import reescribir_consulta

    t0 = time.perf_counter()
    consulta_optimizada = reescribir_consulta(question)
    # Se concatena la pregunta ORIGINAL con los términos reescritos, en vez de reemplazarla: si el
    # rewriter falla o da una reescritura pobre para esta pregunta en particular, las palabras
    # originales (que en varios casos YA encontraban el artículo correcto, ej. "aguinaldo") siguen
    # aportando a la búsqueda en vez de perderse. Ver docs/refactorizacion_rag.md — encontrar el
    # artículo correcto no debe depender de que el rewriter acierte siempre.
    consulta_busqueda = f"{question} {consulta_optimizada}"
    fragments = buscar_hibrido(
        consulta_busqueda, area, top_k=TOP_K, top_k_vector=TOP_K_VECTOR, pregunta_original=question
    )
    # Un documento subido que también está en el corpus (ej. la LNETB) no debe ocupar dos lugares.
    vistos = {_normalizar_texto(f["texto"]) for f in fragments}
    fragments += [f for f in (extra_fragments or []) if _normalizar_texto(f["texto"]) not in vistos]
    # Las fórmulas son de la LFT: solo aplican si la búsqueda trajo artículos de la LFT. Un servidor
    # público de Guerrero se rige por la Ley 248, y darle la cifra de la LFT sería incorrecto.
    if any(f.get("ley") == "Ley Federal del Trabajo" for f in fragments):
        calculo = calcular_si_aplica(question)
        if calculo:
            fragments = [calculo] + fragments
    abrogadas_en_pregunta, abrogadas_mencionadas = vigencia.abrogadas_mencionadas(question, fragments, vigencia.indice())
    t1 = time.perf_counter()

    respaldada = cita_agregada = False
    respuesta_conversacional = REFUSAL_MESSAGE
    if abrogadas_en_pregunta and vigencia.es_pregunta_de_vigencia(question):
        # Determinista: qwen contradecía el transitorio que abroga la ley aun teniéndolo en el contexto.
        fuentes = {f["fuente"] for f in fragments}
        fragments = [a["fragmento"] for a in abrogadas_en_pregunta if a["fragmento"]["fuente"] not in fuentes] + fragments
        respuesta_conversacional, respaldada = vigencia.respuesta_determinista(abrogadas_en_pregunta), True
    elif fragments:
        generada = generate_answer(question, fragments)
        respaldada = verificar_citas(generada, fragments, question)
        if not respaldada and not _CITA_RE.search(generada) and REFUSAL_MESSAGE not in generada:
            reparada = cita_de_respaldo(generada, fragments)
            if reparada and verificar_citas(reparada, fragments, question):
                logger.info("Respuesta sin comillas: se agregó la cita del artículo que nombra.")
                generada, respaldada, cita_agregada = reparada, True, True
        if respaldada:
            respuesta_conversacional = generada
        if abrogadas_mencionadas:  # también tras un rechazo: "esa ley está abrogada" sigue siendo útil
            respuesta_conversacional += "\n\n" + vigencia.nota_del_sistema(abrogadas_mencionadas)
    t2 = time.perf_counter()

    return {
        "respuesta": respuesta_conversacional,
        "respaldada": respaldada,
        "cita_agregada": cita_agregada,  # la cita la agregó el sistema (cita_de_respaldo), no el modelo
        "fragmentos": fragments,
        "disclaimer": AI_DISCLAIMER,
        "tiempos_ms": {
            "recuperacion": round((t1 - t0) * 1000, 1),
            "generacion": round((t2 - t1) * 1000, 1),
            "total": round((t2 - t0) * 1000, 1),
        },
    }
