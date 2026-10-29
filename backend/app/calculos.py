"""Calculadoras deterministas para fórmulas fijas de la LFT: aguinaldo, vacaciones, prima vacacional.

El LLM solo extrae los datos de la pregunta; Python hace la cuenta. Motivo (2026-10-10): llama3.2:3b
respondió "$41.67" en vez de $3,750 en el Caso 2 del diagnóstico, y ningún modelo pequeño es
confiable en aritmética.

REQUIERE REVISIÓN DE UN ABOGADO antes de producción. Las fórmulas son la lectura literal del texto
vigente indexado (Art. 76 reformado DOF 27-12-2022, Art. 80, Art. 87) y deben revisarse con cada reforma.
Supuestos: "parte proporcional" del aguinaldo = meses trabajados / 12; salario semanal/quincenal/mensual
se convierte a diario dividiendo entre 7/15/30; se calcula el MÍNIMO legal (15 días, 25%).
"""

import json
import logging
import re

import httpx

from app.rag import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_NUM_CTX, OLLAMA_OPCIONES_MODELO, OLLAMA_TIMEOUT

logger = logging.getLogger(__name__)

# El tipo de cálculo lo decide Python, no el LLM: qwen devolvía "calculo": null cuando el usuario no
# pedía una cifra sino que validaba una ("me dijeron que me tocan 8 días, ¿es correcto?" — Caso 5).
# Orden importa: "prima vacacional" también contiene "vacaci".
_TIPOS = (
    # Despido + plazo: qwen3.5:4b citaba bien el Art. 518 (dos meses) y aun así concluía "Sí, estás a
    # tiempo" con un despido de hace 4 meses, en 3 de 3 corridas (docs/investigacion_llm.md §7).
    ("prescripcion_despido", re.compile(
        r"(?=.*\b(?:desp[ei]d|corri[eóo]|me\s+corrieron|separ))(?=.*\b(?:tiempo|plazo|demand|reclam|prescri))",
        re.IGNORECASE | re.DOTALL,
    )),
    ("prima_vacacional", re.compile(r"prima\s+vacacional", re.IGNORECASE)),
    ("aguinaldo", re.compile(r"aguinaldo", re.IGNORECASE)),
    ("vacaciones", re.compile(r"vacaci", re.IGNORECASE)),
)
_DIAS_POR_PERIODO = {"diario": 1, "semanal": 7, "quincenal": 15, "mensual": 30}
PLAZO_PRESCRIPCION_DESPIDO_MESES = 2  # Art. 518 LFT

_EXTRACCION_PROMPT = """Extrae los datos de esta consulta laboral. Responde SOLO un objeto JSON con estas claves:
"salario": el monto de salario que menciona el usuario (número) o null,
"periodo_salario": "diario", "semanal", "quincenal" o "mensual" según cómo lo dijo, o null,
"meses_trabajados": meses de servicio si los dice en meses, o null,
"anios_servicio": años de servicio cumplidos si los dice en años (o se deducen sin ambigüedad), o null,
"meses_desde_despido": meses transcurridos desde que lo despidieron o separaron, si los dice, o null,
"dias_desde_despido": días transcurridos desde que lo despidieron o separaron, si los dice en días, o null.
No conviertas ni calcules nada; solo copia los números que da el usuario. No inventes datos.
Consulta: "{pregunta}\""""


def aguinaldo(salario_diario: float, meses: float) -> tuple[float, float]:
    dias = 15 * min(meses, 12) / 12
    return dias, dias * salario_diario


def dias_vacaciones(anios: int) -> int:
    # Art. 76: 12 días al cumplir el primer año, +2 por año hasta 20; desde el sexto año, +2 por cada 5.
    if anios <= 5:
        return 12 + 2 * (anios - 1)
    return 20 + 2 * ((anios - 6) // 5 + 1)


def construir_calculo(datos: dict) -> dict | None:
    """Arma el fragmento "Cálculo determinista" a partir de los datos extraídos, o None si faltan datos."""
    tipo = datos.get("calculo")
    divisor = _DIAS_POR_PERIODO.get(datos.get("periodo_salario") or "")
    salario = datos.get("salario") / divisor if datos.get("salario") and divisor else None
    anios = datos.get("anios_servicio")
    meses = datos.get("meses_trabajados") or (anios * 12 if anios else None)

    meses_despido = datos.get("meses_desde_despido") or (datos["dias_desde_despido"] / 30 if datos.get("dias_desde_despido") else None)

    # La conversión a salario diario va explícita: sin ella, qwen3.5:4b "explicaba" el resultado correcto
    # con cuentas inventadas ("$3,000 a la semana, aproximadamente $750 diarios").
    conversion = (
        f"Salario diario: ${datos['salario']:,.2f} {datos['periodo_salario']} ÷ {divisor} días = ${salario:,.2f}. "
        if salario and divisor != 1 else ""
    )

    if tipo == "prescripcion_despido" and meses_despido is not None:
        excepcion = (
            " Excepción: si nunca recibiste personalmente el aviso de rescisión, la prescripción todavía no "
            "empieza a correr (Art. 47: no comienza sino hasta que el trabajador reciba personalmente el aviso)."
        )
        if meses_despido > PLAZO_PRESCRIPCION_DESPIDO_MESES:
            texto = (f"Plazo para demandar por despido (Art. 518): dos meses desde el día siguiente a la separación. "
                     f"Han pasado {meses_despido:g} meses: el plazo de dos meses YA TRANSCURRIÓ." + excepcion)
        elif meses_despido == PLAZO_PRESCRIPCION_DESPIDO_MESES:
            texto = (f"Plazo para demandar por despido (Art. 518): dos meses desde el día siguiente a la separación. "
                     f"Han pasado justo {meses_despido:g} meses: el plazo vence ahora; hay que verificar la fecha exacta." + excepcion)
        else:
            texto = (f"Plazo para demandar por despido (Art. 518): dos meses desde el día siguiente a la separación. "
                     f"Han pasado {meses_despido:g} meses: TODAVÍA está dentro del plazo de dos meses.")
    elif tipo == "aguinaldo" and salario and meses:
        dias, total = aguinaldo(salario, meses)
        texto = (
            f"{conversion}Aguinaldo mínimo (Art. 87): 15 días de salario por año. Tiempo trabajado: {meses:g} meses → "
            f"15 × ({min(meses, 12):g}/12) = {dias:.2f} días. Salario diario ${salario:,.2f}: "
            f"{dias:.2f} × ${salario:,.2f} = ${total:,.2f}."
        )
    elif tipo == "vacaciones" and anios and anios >= 1:
        texto = f"Vacaciones (Art. 76): con {int(anios)} año(s) de servicio corresponden {dias_vacaciones(int(anios))} días laborables."
    elif tipo == "vacaciones":  # sin antigüedad clara (Caso 5): la tabla deja verificar la cifra que le dijeron
        tabla = "; ".join(f"{a} año(s): {dias_vacaciones(a)} días" for a in (1, 2, 3, 4, 5, 6, 11))
        texto = f"Vacaciones mínimas por antigüedad (Art. 76): {tabla} laborables."
    elif tipo == "prima_vacacional" and salario and anios and anios >= 1:
        dias = dias_vacaciones(int(anios))
        texto = (
            f"{conversion}Prima vacacional mínima (Art. 80, 25%): {dias} días de vacaciones (Art. 76, {int(anios)} año(s)) × "
            f"${salario:,.2f} × 25% = ${0.25 * dias * salario:,.2f}."
        )
    else:
        return None

    return {
        "texto": texto,
        "fuente": "Cálculo determinista, hecho por el sistema a partir de la LFT",
        "ley": "Cálculo del sistema (no es texto legal; requiere revisión de un abogado)",
        "area": "Laboral",
        "score": 1.0,
    }


def calcular_si_aplica(pregunta: str) -> dict | None:
    tipo = next((t for t, patron in _TIPOS if patron.search(pregunta)), None)
    if tipo is None:
        return None
    try:
        with httpx.Client(timeout=OLLAMA_TIMEOUT) as client:
            response = client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    **OLLAMA_OPCIONES_MODELO,
                    "prompt": _EXTRACCION_PROMPT.format(pregunta=pregunta),
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0, "num_ctx": OLLAMA_NUM_CTX},  # mismo num_ctx en todas las llamadas: otro valor recarga el modelo
                },
            )
            response.raise_for_status()
            datos = json.loads(response.json().get("response", "{}")) | {"calculo": tipo}
    except (httpx.HTTPError, ValueError, TypeError):  # TypeError: el JSON no era un objeto
        logger.exception("Falló la extracción de datos para cálculo; se responde sin cálculo determinista.")
        return None
    try:
        return construir_calculo(datos)
    except (TypeError, ValueError):  # el modelo devolvió texto donde se esperaba un número
        logger.warning("Datos de cálculo con formato inválido: %s", datos)
        return None
