from app.rag import verificar_citas

# Textos reales del corpus, incluido el artefacto del PDF ("independienteme nte").
FRAGMENTOS = [
    {
        "fuente": "Artículo 87, Ley Federal del Trabajo (texto vigente)",
        "texto": "Los trabajadores tendrán derecho a un aguinaldo anual que deberá pagarse antes del día "
        "veinte de diciembre, equivalente a quince días de salario, por lo menos. Los que no hayan "
        "cumplido el año de servicios, independienteme nte de que se encuentren laborando o no...",
    },
    {
        "fuente": "Artículo 407, Ley Federal del Trabajo (texto vigente)",
        "texto": "La solicitud se presentará al Centro Federal de Conciliación y Registro Laboral.",
    },
]


def test_cita_literal_pasa_aunque_el_pdf_tenga_espacios_rotos():
    r = "Te tocan 15 días: «equivalente a quince días de salario, por lo menos» (Artículo 87). " \
        "Y aplica «independientemente de que se encuentren laborando» (Artículo 87, LFT)."
    assert verificar_citas(r, FRAGMENTOS)


def test_cita_inventada_se_rechaza():
    # Caso 3 del diagnóstico: contenido que el Art. 407 no dice.
    r = "Sí: «la Secretaría del Trabajo puede desechar la renuncia firmada bajo amenazas» (Artículo 407)."
    assert not verificar_citas(r, FRAGMENTOS)


def test_cita_real_atribuida_a_otro_articulo_se_rechaza():
    r = "«equivalente a quince días de salario, por lo menos» (Artículo 407)."
    assert not verificar_citas(r, FRAGMENTOS)


def test_articulo_con_prefijo_parecido_no_cuenta():
    r = "«equivalente a quince días de salario, por lo menos» (Artículo 870)."
    assert not verificar_citas(r, FRAGMENTOS)


def test_sin_citas_se_rechaza():
    assert not verificar_citas("Tienes hasta dos años para demandar.", FRAGMENTOS)


def test_puntos_suspensivos_dentro_de_la_cita():
    r = "«Los trabajadores tendrán derecho a un aguinaldo anual ... quince días de salario» (Artículo 87)."
    assert verificar_citas(r, FRAGMENTOS)


def test_comillas_rectas_con_etiqueta_pasan():
    r = 'Te tocan 15 días: "equivalente a quince días de salario, por lo menos" (Artículo 87, LFT).'
    assert verificar_citas(r, FRAGMENTOS)


def test_comillas_rectas_mal_atribuidas_se_rechazan():
    r = '"equivalente a quince días de salario, por lo menos" (Art. 407).'
    assert not verificar_citas(r, FRAGMENTOS)


def test_cita_real_sin_etiqueta_pasa():
    # Caso 4 con qwen: «Según el artículo 110, "texto real"» sin (Artículo N) después de la cita.
    r = 'Según el artículo 87, "equivalente a quince días de salario, por lo menos".'
    assert verificar_citas(r, FRAGMENTOS)


def test_cita_inventada_sin_etiqueta_se_rechaza():
    r = 'Hay aguinaldo: "equivalente a quince días de salario, por lo menos" (Artículo 87). ' \
        'Además "el patrón puede descontar el aguinaldo si el trabajador renuncia".'
    assert not verificar_citas(r, FRAGMENTOS)


def test_citar_solo_al_usuario_no_respalda():
    pregunta = "Me van a cobrar una computadora descontándome el 50% de mi quincena."
    r = 'No: "cobrar una computadora descontándome el 50% de mi quincena" no está permitido.'
    assert not verificar_citas(r, FRAGMENTOS, pregunta)
    r += ' Además, "equivalente a quince días de salario, por lo menos" (Artículo 87).'
    assert verificar_citas(r, FRAGMENTOS, pregunta)


def test_el_prompt_cabe_en_el_contexto_y_conserva_las_reglas():
    from app.rag import MAX_TOKENS_RESPUESTA, OLLAMA_NUM_CTX, SYSTEM_PROMPT, _CHARS_POR_TOKEN, _armar_prompt

    # Caso real: Ollama borraba el principio del prompt (el system prompt) cuando no cabía.
    grandes = [{"fuente": f"Artículo {i}", "texto": "palabra " * 600} for i in range(1, 15)]
    prompt = _armar_prompt("¿pregunta?", grandes)
    assert prompt.startswith(SYSTEM_PROMPT)
    assert len(prompt) / _CHARS_POR_TOKEN + MAX_TOKENS_RESPUESTA <= OLLAMA_NUM_CTX
    assert "[Fuente: Artículo 1]" in prompt and "[Fuente: Artículo 14]" not in prompt  # se quitan los últimos


def test_cita_del_calculo_con_etiqueta_de_articulo():
    calculo = {"fuente": "Cálculo determinista, hecho por el sistema a partir de la LFT",
               "texto": "Vacaciones (Art. 76): con 3 año(s) de servicio corresponden 16 días laborables."}
    r = "Te tocan 16 días: «con 3 año(s) de servicio corresponden 16 días laborables» (Artículo 76)."
    assert verificar_citas(r, [calculo] + FRAGMENTOS)
    # Lo que no está en ningún fragmento sigue rechazándose aunque haya un cálculo en el contexto.
    assert not verificar_citas("«con 3 años corresponden 30 días» (Artículo 76).", [calculo] + FRAGMENTOS)


def test_cita_de_respaldo_del_articulo_que_la_respuesta_nombra():
    from app.rag import cita_de_respaldo

    adopcion = {"fuente": "Artículo 555, CODIGO CIVIL", "texto": "Las personas mayores de treinta años, en pleno "
                "ejercicio de sus derechos, podrán adoptar a un menor o a un incapacitado. Otra oración distinta del artículo."}
    respuesta = "Según el Artículo 555, solo las personas mayores de treinta años pueden adoptar; con 25 años no se cumple."
    reparada = cita_de_respaldo(respuesta, [adopcion] + FRAGMENTOS)
    assert reparada.endswith("«Las personas mayores de treinta años, en pleno ejercicio de sus derechos, podrán adoptar a un menor o a un incapacitado.» (Artículo 555)")
    assert verificar_citas(reparada, [adopcion] + FRAGMENTOS)


def test_sin_articulo_del_contexto_no_hay_cita_de_respaldo():
    from app.rag import cita_de_respaldo

    assert cita_de_respaldo("Según el Artículo 999, puedes adoptar.", FRAGMENTOS) is None  # no está en el contexto
    assert cita_de_respaldo("Puedes adoptar sin problema.", FRAGMENTOS) is None  # no nombra ningún artículo
