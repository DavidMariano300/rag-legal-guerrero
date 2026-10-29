import pytest
from fastapi import HTTPException

from app import generation


def test_sugerir_plantilla_sin_coincidencia_devuelve_none():
    resultado = generation.sugerir_plantilla(
        "¿Cuál es el plazo para contestar una demanda civil?",
        "El plazo es de nueve días hábiles.",
    )
    assert resultado is None


def test_sugerir_plantilla_con_coincidencia_devuelve_plantilla():
    resultado = generation.sugerir_plantilla(
        "¿Qué porcentaje se fija de pensión alimenticia?",
        "El quince por ciento de los ingresos netos.",
    )
    assert resultado is not None
    assert resultado["id"] == "plantilla_prueba"


def test_sugerir_plantilla_palabra_generica_no_activa_falso_positivo():
    # Regresión: "demanda" sola era demasiado genérica y activaba la sugerencia
    # en cualquier pregunta sobre demandas, no solo las de pensión alimenticia.
    resultado = generation.sugerir_plantilla(
        "¿Cuánto es la indemnización por despido injustificado?",
        "Tres meses de salario.",
    )
    assert resultado is None


def test_generate_document_plantilla_inexistente():
    with pytest.raises(HTTPException) as exc_info:
        generation.generate_document("plantilla_que_no_existe", {})
    assert exc_info.value.status_code == 404


def test_generate_document_campos_faltantes():
    with pytest.raises(HTTPException) as exc_info:
        generation.generate_document("plantilla_prueba", {"nombre_actor": "Juana Pérez"})
    assert exc_info.value.status_code == 400


def test_generate_document_exitoso_produce_docx_valido():
    contenido = generation.generate_document(
        "plantilla_prueba",
        {
            "nombre_actor": "Juana Pérez",
            "nombre_contraparte": "Empresa de Prueba SA",
            "fecha": "2026-09-23",
            "asunto": "Prueba",
        },
    )
    assert contenido[:2] == b"PK"  # .docx es un ZIP; firma real, no solo por extensión
