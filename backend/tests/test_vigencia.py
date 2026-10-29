from app.rag import verificar_citas
from app.vigencia import abrogadas_mencionadas, es_pregunta_de_vigencia, indice_abrogaciones, respuesta_determinista

CORPUS = [
    {"fuente": "Transitorio Segundo, LEY NACIONAL PARA ELIMINAR TRÁMITES BUROCRÁTICOS",
     "ley": "LEY NACIONAL PARA ELIMINAR TRÁMITES BUROCRÁTICOS",
     "texto": "Se abroga la Ley General de Mejora Regulatoria, publicada en el Diario Oficial de la Federación el 18 de mayo de 2018."},
    # Un artículo vigente que menciona la ley abrogada no es fuente de abrogación (caso real: Ley 455, Art. 35).
    {"fuente": "Artículo 35, LEY NÚMERO 455 DE MEJORA REGULATORIA", "ley": "LEY NÚMERO 455 DE MEJORA REGULATORIA",
     "texto": "Para los efectos de la presente Ley, se aplicará de manera supletoria la Ley General de Mejora Regulatoria."},
    {"fuente": "Transitorio Primero, CODIGO CIVIL", "ley": "CODIGO CIVIL", "texto": "Se abroga la Ley anterior."},
    # La ley nueva se llama igual que la abrogada (más su número): no debe marcarse la vigente.
    {"fuente": "Transitorio Segundo, LEY ORGÁNICA DEL PODER LEGISLATIVO DEL ESTADO DE GUERRERO NÚMERO 231",
     "ley": "LEY ORGÁNICA DEL PODER LEGISLATIVO DEL ESTADO DE GUERRERO NÚMERO 231",
     "texto": "Se abroga la Ley Orgánica del Poder Legislativo del Estado de Guerrero, publicada en 1999."},
    # Abreviatura dentro del nombre: no debe cortarse en "No".
    {"fuente": "Transitorio Segundo, LEY NÚMERO 1212 DE SALUD", "ley": "LEY NÚMERO 1212 DE SALUD",
     "texto": "Se abroga la Ley de Salud del Estado No. 159, publicada en el Periódico Oficial."},
]
INDICE = indice_abrogaciones(CORPUS)


def test_solo_cuenta_abrogaciones_expresas_en_transitorios():
    # "la Ley anterior" no nombra nada; la del Poder Legislativo está contenida en el nombre de la vigente.
    assert [a["abrogada"] for a in INDICE] == ["Ley General de Mejora Regulatoria", "Ley de Salud del Estado No. 159"]


def test_pregunta_de_vigencia_sobre_ley_abrogada_se_responde_sin_llm():
    pregunta = "¿Sigue vigente la ley general de mejora regulatoria?"
    en_pregunta, _ = abrogadas_mencionadas(pregunta, [], INDICE)
    assert es_pregunta_de_vigencia(pregunta) and [a["abrogada"] for a in en_pregunta] == ["Ley General de Mejora Regulatoria"]
    respuesta = respuesta_determinista(en_pregunta)
    assert respuesta.startswith("No. La Ley General de Mejora Regulatoria está abrogada.")
    # La cita del transitorio es literal: pasa la misma verificación que una respuesta del modelo.
    assert verificar_citas(respuesta, [en_pregunta[0]["fragmento"]])


def test_la_cita_incluye_la_abreviatura_completa():
    entrada = next(a for a in INDICE if "Salud" in a["abrogada"])
    assert entrada["cita"] == "Se abroga la Ley de Salud del Estado No. 159, publicada en el Periódico Oficial."


def test_ley_abrogada_mencionada_solo_en_el_contexto():
    en_pregunta, mencionadas = abrogadas_mencionadas("¿Qué ley se aplica supletoriamente?", [CORPUS[1]], INDICE)
    assert en_pregunta == [] and [a["abrogada"] for a in mencionadas] == ["Ley General de Mejora Regulatoria"]


def test_una_frase_con_no_no_dispara_el_aviso():
    assert abrogadas_mencionadas("¿La Ley de Salud del Estado no regula esto?", [], INDICE) == ([], [])


def test_sin_aviso_cuando_no_aparece():
    assert abrogadas_mencionadas("¿Qué comprenden los alimentos?", [{"texto": "La comida.", "ley": "CODIGO CIVIL"}], INDICE) == ([], [])
