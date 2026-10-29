from app.ingest_lft import parse_articulos
from app.retrieval.hybrid_search import _regimen_aplica, _tokenizar

# Mismo formato de encabezados que el PDF oficial: nombre del título/capítulo en la línea siguiente.
TEXTO = """TITULO TERCERO
Condiciones de Trabajo
Artículo 76.- Vacaciones generales.
TITULO SEXTO
Trabajos Especiales
CAPITULO III
Trabajadores de los buques
Artículo 199.- Vacaciones de los marinos.
TITULO SEPTIMO
Relaciones Colectivas de Trabajo
Artículo 354.- Coalición.

TRANSITORIOS
"""


def test_parse_asigna_capitulo_solo_a_trabajos_especiales():
    por_numero = {a["numero"]: a["capitulo_especial"] for a in parse_articulos(TEXTO)}
    assert por_numero == {"76": None, "199": "Trabajadores de los buques", "354": None}


def test_regimen_especial_excluido_en_pregunta_general():
    assert not _regimen_aplica(set(_tokenizar("me tocan 8 días de vacaciones")), "Trabajadores de los buques")


def test_regimen_especial_incluido_si_la_pregunta_lo_nombra():
    assert _regimen_aplica(set(_tokenizar("soy marino en un buque, mis vacaciones")), "Trabajadores de los buques")
    assert _regimen_aplica(set(_tokenizar("soy trabajadora del hogar")), "Personas Trabajadoras del Hogar")


def test_articulo_general_siempre_aplica():
    assert _regimen_aplica(set(), None)
