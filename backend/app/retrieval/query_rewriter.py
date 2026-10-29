"""Query Rewriting: traduce lenguaje coloquial a términos de búsqueda legal ANTES de embeder.

Resuelve el Caso 3 de docs/diagnostico_rag.csv: el retriever se perdía con narrativa coloquial
("me encerraron y amenazaron para firmar mi renuncia") y buscaba prácticamente solo por la palabra
literal "demandar", trayendo artículos sobre poderes notariales en vez de coacción/nulidad de renuncia.

Usa el mismo Ollama ya desplegado — no se agrega un segundo modelo al stack. El costo de esta decisión
es latencia: cada consulta ahora hace DOS llamadas al LLM (reescritura + generación) en vez de una, lo
que aproximadamente duplica el tiempo total de respuesta. Ver docs/refactorizacion_rag.md para el
tradeoff completo y alternativas futuras (modelo dedicado más pequeño, reescritura condicional).
"""

import logging
import os

import httpx

from app.rag import OLLAMA_NUM_CTX, OLLAMA_OPCIONES_MODELO, OLLAMA_TIMEOUT

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:4b")

REWRITER_PROMPT = """Eres un traductor de lenguaje coloquial a términos de búsqueda legal en México.

Tu única tarea: dada una narración coloquial de un problema legal (laboral, civil, familiar, penal,
administrativo...), devuelve una lista corta de
TÉRMINOS JURÍDICOS de búsqueda (3 a 6 términos o frases cortas, separados por comas). Responde
ÚNICAMENTE con la lista de términos — sin saludo, sin explicación, sin contestar la pregunta del
usuario, sin dar asesoría legal. Usa ortografía correcta del español y la forma sustantiva (de
diccionario) de cada término legal — nunca inventes palabras ni dejes términos en inglés.

Ejemplo 1:
Entrada: "me corrió y me encerró para que firmara mi renuncia"
Salida: despido injustificado, coacción, nulidad de renuncia, vicios del consentimiento

Ejemplo 2:
Entrada: "no me quieren pagar las horas que me quedé después de mi turno"
Salida: tiempo extraordinario, horas extra, jornada de trabajo, pago de tiempo extra

Ejemplo 3:
Entrada: "me están cobrando una herramienta descontándomela de mi quincena"
Salida: descuentos al salario, descuento salarial, deudas del trabajador con el patrón, salario mínimo

Ejemplo 4:
Entrada: "ya pasaron varios meses desde que me corrieron, ¿todavía puedo reclamar?"
Salida: prescripción de acciones, plazo para demandar, separación del trabajo, despido

Ejemplo 5:
Entrada: "mi ex no me deja ver a mis hijos y tampoco me da dinero para ellos"
Salida: guarda y custodia, régimen de convivencia, pensión alimenticia, alimentos, patria potestad

Ejemplo 6:
Entrada: "un vecino me dijo que me iba a golpear si no le pagaba"
Salida: amenazas, delito de amenazas, extorsión, denuncia penal

Ejemplo 7:
Entrada: "trabajo limpiando y cocinando en una casa y me quedo a dormir ahí"
Salida: personas trabajadoras del hogar, trabajo doméstico, descanso diario, jornada de trabajo

Ahora convierte esta narración:
Entrada: "{pregunta}"
Salida:"""


def reescribir_consulta(pregunta: str) -> str:
    """Devuelve términos de búsqueda optimizados para embeder, o la pregunta original si algo falla.

    Nunca debe romper el flujo de consulta: si Ollama no responde o da una salida vacía, se hace
    fallback silencioso a la pregunta original — el peor caso es que la búsqueda se comporte como
    antes de este cambio, no una falla dura de la API.
    """
    prompt = REWRITER_PROMPT.format(pregunta=pregunta)
    try:
        with httpx.Client(timeout=OLLAMA_TIMEOUT) as client:
            response = client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    **OLLAMA_OPCIONES_MODELO,
                    "prompt": prompt,
                    "stream": False,
                    # temperature baja a propósito: esto es una tarea de traducción de términos, no
                    # generación creativa. Con la temperatura por defecto de Ollama (0.8) se midió
                    # que la MISMA pregunta podía recuperar artículos distintos en llamadas
                    # consecutivas, y con 0.1 todavía variaba el Caso 1 — un rewriter que no es
                    # reproducible socava la confiabilidad de todo lo que viene después.
                    # num_ctx igual al de la respuesta: con otro valor Ollama recarga el modelo en cada llamada.
                    "options": {"num_predict": 60, "temperature": 0, "num_ctx": OLLAMA_NUM_CTX},
                },
            )
            response.raise_for_status()
            texto = response.json().get("response", "").strip()
    except httpx.HTTPError:
        logger.exception("Falló la reescritura de consulta; usando la pregunta original sin cambios.")
        return pregunta

    return texto or pregunta
