"""Vigencia determinista: qué leyes abroga el propio corpus, según sus transitorios.

Caso real (2026-10-25): a "¿Sigue vigente la Ley General de Mejora Regulatoria?" qwen2.5:7b respondió
"Sí", citando el Art. 35 de la Ley 455 estatal (que todavía la nombra como supletoria), aunque en el
contexto estaba el Transitorio Segundo de la LNETB: "Se abroga la Ley General de Mejora Regulatoria".
La cita era real, así que verificar_citas no podía detenerlo, y siguió diciendo "Sí" aun con un aviso
explícito en el contexto y una regla en el prompt. Como con los cálculos (app/calculos.py), el dato
duro no depende del modelo:
- pregunta de vigencia sobre una ley abrogada → la respuesta la arma Python, con la cita del transitorio;
- cualquier otra respuesta cuyo contexto nombre una ley abrogada → se le anexa la nota del sistema.

REQUIERE REVISIÓN DE UN ABOGADO: solo detecta abrogaciones expresas en transitorios del corpus
("Se abroga la Ley ..."); no las tácitas ni las de leyes que no están indexadas.
"""

import re
import unicodedata

# El nombre sigue hasta la primera coma o punto, salvo el de una abreviatura: "Ley de Salud del Estado
# No. 159" se cortaba en "No" y entonces "la Ley de Salud del Estado no regula..." disparaba un aviso.
# La abreviatura va primero en la alternancia para que se pruebe antes que el carácter suelto.
_ABROGA_RE = re.compile(
    r"\bse\s+abrogan?\s+(?:la|el)\s+((?:ley|c[óo]digo|reglamento|estatuto)\b(?:\b(?:No|N[úu]m|Art)\.|[^,.;:]){10,200})",
    re.IGNORECASE,
)
_FIN_ORACION_RE = re.compile(r"(?<!\bNo)(?<!\bNúm)(?<!\bNum)(?<!\bArt)\.(?=\s|$)")
_PREGUNTA_VIGENCIA_RE = re.compile(r"vigen|abrog|derog|en vigor|sigue\s+aplic|todav[ií]a\s+aplic", re.IGNORECASE)
MIN_PALABRAS_NOMBRE = 4  # "Se abroga la Ley anterior" no nombra ninguna ley concreta

_indice: list[dict] | None = None


def _normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sin_acentos.lower().split())


def indice_abrogaciones(payloads: list[dict]) -> list[dict]:
    """Una entrada por ley abrogada en algún transitorio del corpus, con la oración que la abroga.

    Se descarta la abrogación cuyo nombre está contenido en el de una ley VIGENTE del corpus: la Ley
    Orgánica del Poder Legislativo 231 abrogó a la "Ley Orgánica del Poder Legislativo del Estado de
    Guerrero" anterior, y sin este filtro cada artículo de la 231 se habría marcado como abrogado.
    """
    vigentes = {_normalizar(p["ley"]) for p in payloads if p.get("ley")}
    abrogadas: dict[str, dict] = {}
    for p in payloads:
        if not (p.get("fuente") or "").startswith("Transitorio"):
            continue  # un artículo que menciona de pasada una abrogación no es la fuente de la abrogación
        texto = p.get("texto") or ""
        for m in _ABROGA_RE.finditer(texto):
            nombre = " ".join(m.group(1).split())
            clave = _normalizar(nombre)
            if len(nombre.split()) < MIN_PALABRAS_NOMBRE or any(clave in v for v in vigentes):
                continue
            fin = _FIN_ORACION_RE.search(texto, m.end())
            abrogadas[clave] = {
                "abrogada": nombre,
                "por": p.get("ley"),
                "transitorio": p["fuente"].split(",")[0],
                "cita": texto[m.start(): fin.end() if fin else len(texto)].strip(),
                "fragmento": {k: p.get(k) for k in ("texto", "fuente", "ley", "area")},
            }
    return list(abrogadas.values())


def abrogadas_mencionadas(pregunta: str, fragments: list[dict], indice: list[dict]) -> tuple[list[dict], list[dict]]:
    """(las nombradas en la pregunta, las nombradas en la pregunta o en el contexto)."""
    en_pregunta = [a for a in indice if _normalizar(a["abrogada"]) in _normalizar(pregunta)]
    contexto = _normalizar(" ".join(f"{f.get('ley') or ''} {f.get('texto') or ''}" for f in fragments))
    return en_pregunta, en_pregunta + [a for a in indice if a not in en_pregunta and _normalizar(a["abrogada"]) in contexto]


def es_pregunta_de_vigencia(pregunta: str) -> bool:
    return bool(_PREGUNTA_VIGENCIA_RE.search(pregunta))


def respuesta_determinista(abrogadas: list[dict]) -> str:
    return "No. " + " ".join(
        f"La {a['abrogada']} está abrogada. Así lo dispone el {a['transitorio']} de la {a['por']}: "
        f"«{a['cita']}» ({a['transitorio']})."
        for a in abrogadas
    )


def nota_del_sistema(abrogadas: list[dict]) -> str:
    leyes = "; ".join(f"la {a['abrogada']} está abrogada ({a['transitorio']} de la {a['por']})" for a in abrogadas)
    return f"Aviso del sistema: {leyes}. Verifique la ley vigente antes de aplicarla."


def indice() -> list[dict]:
    global _indice
    if _indice is None:  # se arma una vez por proceso con el mismo corpus que BM25
        from app.retrieval.hybrid_search import payloads_corpus

        _indice = indice_abrogaciones(payloads_corpus())
    return _indice
