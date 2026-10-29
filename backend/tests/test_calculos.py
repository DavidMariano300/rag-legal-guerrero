from app.calculos import aguinaldo, construir_calculo, dias_vacaciones


def test_aguinaldo_proporcional_caso_2():
    assert aguinaldo(500, 6) == (7.5, 3750)


def test_aguinaldo_no_pasa_de_15_dias():
    assert aguinaldo(400, 30) == (15, 6000)


def test_tabla_vacaciones_art_76():
    assert [dias_vacaciones(a) for a in (1, 2, 5, 6, 10, 11, 16)] == [12, 14, 20, 22, 22, 24, 26]


def test_salario_mensual_se_convierte_en_python():
    frag = construir_calculo({"calculo": "aguinaldo", "salario": 15000, "periodo_salario": "mensual", "meses_trabajados": 12})
    assert "$7,500.00" in frag["texto"]  # 15000/30 = 500 diarios × 15 días
    assert "$15,000.00 mensual ÷ 30 días = $500.00" in frag["texto"]  # la conversión va explícita


def test_vacaciones_caso_5():
    frag = construir_calculo({"calculo": "vacaciones", "anios_servicio": 2})
    assert "14 días" in frag["texto"]


def test_vacaciones_sin_antiguedad_da_la_tabla():
    frag = construir_calculo({"calculo": "vacaciones", "anios_servicio": None})
    assert "1 año(s): 12 días; 2 año(s): 14 días" in frag["texto"]


def test_prescripcion_despido_vencida_menciona_la_excepcion_del_art_47():
    frag = construir_calculo({"calculo": "prescripcion_despido", "meses_desde_despido": 4})
    assert "YA TRANSCURRIÓ" in frag["texto"] and "Art. 47" in frag["texto"]


def test_prescripcion_despido_en_plazo_y_en_dias():
    assert "TODAVÍA" in construir_calculo({"calculo": "prescripcion_despido", "meses_desde_despido": 1})["texto"]
    assert "YA TRANSCURRIÓ" in construir_calculo({"calculo": "prescripcion_despido", "dias_desde_despido": 90})["texto"]


def test_tipo_prescripcion_solo_con_despido_y_plazo():
    from app.calculos import _TIPOS
    tipo = lambda q: next((t for t, p in _TIPOS if p.search(q)), None)
    assert tipo("Fui despedido hace 4 meses... ¿Aún estoy a tiempo de demandar?") == "prescripcion_despido"
    assert tipo("Me corrieron hace 3 semanas, ¿puedo reclamar?") == "prescripcion_despido"
    assert tipo("Me despidieron, ¿me deben pagar aguinaldo?") == "aguinaldo"


def test_sin_datos_suficientes_no_calcula():
    assert construir_calculo({"calculo": "aguinaldo", "salario": 500, "periodo_salario": "diario"}) is None
    assert construir_calculo({"calculo": None}) is None
