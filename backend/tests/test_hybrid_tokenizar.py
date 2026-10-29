from app.retrieval.hybrid_search import _tokenizar


def test_singular_y_plural_coinciden():
    # Caso 4 del diagnóstico: la consulta dice "descuento salarial", el Art. 110 "descuentos en los salarios".
    assert _tokenizar("descuento salario") == _tokenizar("descuentos salarios")


def test_quita_puntuacion():
    assert _tokenizar("¿quincena?") == _tokenizar("quincena")
