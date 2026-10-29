from app.documents import ALLOWED_EXTENSIONS, MAX_FILE_SIZE_BYTES, _chunk_text, _fragmentar, _validar_contenido_real
from app.rag import verificar_citas
from fastapi import HTTPException
import pytest


def test_chunk_text_texto_vacio():
    assert _chunk_text("") == []
    assert _chunk_text("   ") == []


def test_chunk_text_respeta_tamano_maximo():
    texto = "a" * 3000
    chunks = _chunk_text(texto)
    assert all(len(c) <= 1200 for c in chunks)
    assert len(chunks) > 1


def test_chunk_text_tiene_overlap():
    texto = "0123456789" * 200  # 2000 caracteres
    chunks = _chunk_text(texto)
    # El final del primer chunk debe reaparecer al inicio del segundo (overlap)
    assert chunks[0][-50:] == chunks[1][:50]


def test_validar_contenido_pdf_falso_rechazado():
    with pytest.raises(HTTPException) as exc_info:
        _validar_contenido_real("contrato.pdf", b"esto no es un PDF real")
    assert exc_info.value.status_code == 400


def test_validar_contenido_pdf_real_aceptado():
    _validar_contenido_real("contrato.pdf", b"%PDF-1.4 resto del archivo")  # no lanza excepción


def test_validar_contenido_docx_falso_rechazado():
    with pytest.raises(HTTPException):
        _validar_contenido_real("contrato.docx", b"no es un zip")


def test_extensiones_permitidas_incluyen_formatos_esperados():
    assert ALLOWED_EXTENSIONS == {".pdf", ".docx", ".txt"}


def test_limite_tamano_archivo_razonable():
    assert MAX_FILE_SIZE_BYTES == 15 * 1024 * 1024


def test_ley_subida_se_fragmenta_por_articulo_y_sus_citas_se_verifican():
    ley = (
        "Artículo 1. La presente Ley es de orden público.\n"
        "Artículo 2. Son objetivos de esta Ley eliminar los trámites innecesarios para las personas.\n"
        "Artículo 3. Para los efectos de esta Ley se entenderá por trámite cualquier solicitud.\n"
    )
    fragmentos = [
        {"fuente": f"{art}, Documento subido: LNETB.pdf", "texto": texto} for art, texto in _fragmentar(ley)
    ]
    assert fragmentos[1]["fuente"] == "Artículo 2, Documento subido: LNETB.pdf"
    # Antes: la fuente no traía el artículo y esta cita (correcta) se rechazaba.
    assert verificar_citas("«eliminar los trámites innecesarios para las personas» (Artículo 2)", fragmentos)


def test_documento_que_no_es_ley_se_trocea_por_tamano():
    assert _fragmentar("Contrato de arrendamiento entre las partes. " * 50)[0][0] is None
