from app.retrieval import hybrid_search as hs

LEYES = [
    "LEY NACIONAL PARA ELIMINAR TRÁMITES BUROCRÁTICOS",
    "Ley Federal del Trabajo",
    "CODIGO CIVIL DEL ESTADO LIBRE Y SOBERANO DE GUERRERO NUMERO 358",
    "CÓDIGO FISCAL DEL ESTADO DE GUERRERO NÚMERO 420",
    "CODIGO FISCAL MUNICIPAL NUMERO 152",
    "CONSTITUCIÓN POLÍTICA DEL ESTADO LIBRE Y SOBERANO DE GUERRERO",
]


def _con_leyes(monkeypatch):
    monkeypatch.setattr(hs, "_alias_leyes", [(a, ley) for ley in LEYES for a in hs._alias(ley)])


def test_nombre_completo_corto_y_siglas(monkeypatch):
    _con_leyes(monkeypatch)
    assert hs.ley_mencionada("¿Cuál es el objeto de la Ley Nacional para Eliminar Trámites Burocráticos?") == LEYES[0]
    assert hs.ley_mencionada("¿Qué dice la LNETB sobre Llave MX?") == LEYES[0]
    assert hs.ley_mencionada("Según la LFT, ¿cuántos días de vacaciones me tocan?") == LEYES[1]
    assert hs.ley_mencionada("¿Qué dice el código civil sobre los alimentos?") == LEYES[2]


def test_gana_el_alias_mas_largo_y_no_adivina(monkeypatch):
    _con_leyes(monkeypatch)
    assert hs.ley_mencionada("¿Qué impuestos cobra el código fiscal municipal?") == LEYES[4]
    assert hs.ley_mencionada("¿Qué dice el código fiscal?") == LEYES[3]
    assert hs.ley_mencionada("¿Cuántos días de vacaciones me tocan?") is None


def test_constitucion_federal_no_se_confunde_con_la_de_guerrero(monkeypatch):
    _con_leyes(monkeypatch)
    assert hs.ley_mencionada("¿Qué dice la Constitución Política de los Estados Unidos Mexicanos?") is None
    assert hs.ley_mencionada("¿Qué dice la Constitución Política de Guerrero sobre diputados?") == LEYES[5]


def test_sinonimo_de_regimen_hogar():
    stems = set(hs._tokenizar("trabajo doméstico, descanso nocturno"))
    assert hs._regimen_aplica(stems, "Personas Trabajadoras del Hogar")
    assert not hs._regimen_aplica(set(hs._tokenizar("vacaciones de un trabajador")), "Personas Trabajadoras del Hogar")


def test_termino_a_definir():
    assert hs._termino_a_definir("¿Qué se entiende por trámite en la Ley Nacional para Eliminar Trámites Burocráticos?") == "tramite"
    assert hs._termino_a_definir("¿Qué es Llave MX según la LNETB?") == "llave mx"
    assert hs._termino_a_definir("¿Qué es el concubinato según el Código Civil de Guerrero?") == "concubinato"
    assert hs._termino_a_definir("¿Cuántos días de vacaciones me tocan?") is None
