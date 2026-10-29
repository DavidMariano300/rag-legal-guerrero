from app.ingest import parse_articles

FIXTURE_MUESTRA = """# Título

## Artículo 1 (ficticio, prueba)
Área: Civil y Familiar

Texto del primer artículo.

## Artículo 2 (ficticio, prueba)
Área: Laboral

Texto del segundo artículo.
"""


def test_parse_articles_extrae_area_y_texto():
    articulos = parse_articles(FIXTURE_MUESTRA)
    assert len(articulos) == 2
    assert articulos[0]["fuente"] == "Artículo 1 (ficticio, prueba)"
    assert articulos[0]["area"] == "Civil y Familiar"
    assert "primer artículo" in articulos[0]["texto"]
    assert articulos[1]["area"] == "Laboral"


def test_parse_articles_sin_area_usa_default():
    texto = "## Artículo X\nTexto sin línea de área.\n"
    articulos = parse_articles(texto)
    assert articulos[0]["area"] == "Sin clasificar"
