from app.ingest_leyes import MAX_CHARS_FRAGMENTO, _ultima_reforma, clasificar_area, parse_articulos

# Imita el PDF real del Congreso: ruido de página, preámbulo que cita tratados con su propio
# "Artículo 1" (Código Penal 499), notas de reforma, referencias a otros artículos y transitorios.
TEXTO = """H. Congreso del Estado de Guerrero
S.S.P./D.P.L.
1
CCCÓÓÓDDDIIIGGGOOO PPPEEENNNAAALLL
ÚLTIMA MODIFICACIÓN PUBLICADA EN EL PERIÓDICO OFICIAL DEL GOBIERNO DEL ESTADO EDICIÓN No. 41
ALCANCE VI, DE FECHA VIERNES 22 DE MAYO DE 2026. TEXTO ORIGINAL.
Exposición de motivos. La Convención dispone:
Artículo 1. Sancionar la explotación.
Artículo 2. Otra cita de tratado.
Artículo 1. Legalidad
A nadie se le podrá imponer pena sin ley previa.
(REFORMADO, P.O. EDICIÓN 13 ALCANCE IV, DE FECHA VIERNES 13 DE FEBRERO DE 2026)
Artículo 2.- Tipicidad. Se estará a lo dispuesto en el
artículo 29. Fin de la referencia.
H. Congreso del Estado de Guerrero
7
S.S.P./D.P.L.
III.
ARTICULO 3. - Culpabilidad.
Artículo 3 BIS.- Agravante.

T R A N S I T O R I O S

PRIMERO. El presente Decreto entrará en vigor.
Rúbrica.
N. DE E. A CONTINUACION SE TRANSCRIBEN LOS ARTICULOS TRANSITORIOS DE LOS DECRETOS DE REFORMAS.
ARTÍCULO 198 DEL CÓDIGO PENAL.
"""


def test_toma_la_cadena_real_y_corta_en_transitorios():
    articulos = parse_articulos(TEXTO)
    assert [a["numero"] for a in articulos] == ["1", "2", "3", "3 BIS", "TRANSITORIO PRIMERO"]
    assert articulos[0]["texto"] == "Legalidad A nadie se le podrá imponer pena sin ley previa."
    assert "artículo 29. Fin de la referencia" in articulos[1]["texto"]  # referencia, no encabezado
    assert "Agravante." == articulos[3]["texto"]  # no arrastra los transitorios
    assert articulos[4]["texto"] == "El presente Decreto entrará en vigor."  # ni el historial de reformas


def test_limpia_ruido_de_pagina_y_notas_de_reforma():
    texto = " ".join(a["texto"] for a in parse_articulos(TEXTO))
    for ruido in ("Congreso del Estado", "S.S.P.", "CCCÓÓÓ", "REFORMADO"):
        assert ruido not in texto
    assert "III." in texto  # una fracción suelta no es ruido


def test_articulo_largo_se_parte_por_parrafos():
    parrafo = "Texto del párrafo. " * 60  # ~1140 caracteres
    articulos = parse_articulos(f"Artículo 1.- {parrafo}\n\n{parrafo}\n\n{parrafo}\nArtículo 2.- Corto.")
    partes = [a for a in articulos if a["numero"] == "1"]
    assert len(partes) == 3 and all(len(p["texto"]) <= MAX_CHARS_FRAGMENTO for p in partes)
    assert partes[0]["partes"] == 3


def test_formatos_abreviado_y_ordinal_sin_separador():
    # Ley Arancelaria ("Art. 1o.-") y Ley 932 ("Articulo 1°  La", sin separador tras el ordinal).
    assert [a["numero"] for a in parse_articulos("Art. 1o.- Uno.\nArt. 2o. - Dos.")] == ["1", "2"]
    assert [a["numero"] for a in parse_articulos("Articulo 1°  La comisión.\nArtículo 2. La otra.")] == ["1", "2"]
    # Sin ordinal sigue exigiendo separador: una línea que empieza con "Artículo 10 obliga" no es encabezado.
    assert [a["numero"] for a in parse_articulos("Artículo 1.- Uno.\nArtículo 10 obliga a todos.")] == ["1"]


def test_articulos_derogados_se_omiten():
    articulos = parse_articulos("Artículo 1.- Vigente.\nArtículo 2.- Derogado.\nArtículo 3.- (Se deroga)\nArtículo 4.- Otro.")
    assert [a["numero"] for a in articulos] == ["1", "4"]


def test_fecha_de_ultima_reforma():
    assert _ultima_reforma(TEXTO) == "VIERNES 22 DE MAYO DE 2026"


def test_clasificacion_por_nombre():
    assert clasificar_area("CODIGO CIVIL DEL ESTADO LIBRE Y SOBERANO DE GUERRERO NUMERO 358") == "Civil y Familiar"
    assert clasificar_area("CÓDIGO PENAL PARA EL ESTADO LIBRE Y SOBERANO DE GUERRERO, NÚMERO 499") == "Penal"
    assert clasificar_area("LEY DE TRABAJO DE LOS SERVIDORES PUBLICOS DEL ESTADO DE GUERRERO NUMERO 248") == "Laboral burocrático"
    assert clasificar_area("LEY NÚMERO 175 DEL CENTRO DE CONCILIACIÓN LABORAL DEL ESTADO DE GUERRERO") == "Laboral"
    assert clasificar_area("Constitución Política") == "Constitucional y Electoral"
    assert clasificar_area("CÓDIGO FISCAL DEL ESTADO DE GUERRERO NÚMERO 420") == "Administrativo y Fiscal"


def test_clasificacion_sin_falsos_positivos_por_palabra_suelta():
    for nombre in (
        "LEY NÚMERO 861 DE GESTIÓN INTEGRAL DE RIESGOS Y PROTECCIÓN CIVIL DEL ESTADO DE GUERRERO.",
        "LEY NÚMERO 458 PARA IMPULSAR A LAS ORGANIZACIONES DE LA SOCIEDAD CIVIL EN EL ESTADO DE GUERRERO",
        "LEY DE PREMIOS CIVILES DEL ESTADO DE GUERRERO NÚMERO 434",
    ):
        assert clasificar_area(nombre) == "Administrativo y Fiscal", nombre
    assert clasificar_area(
        "LEY NÚMERO 812 PARA LA PROTECCIÓN DE LOS DERECHOS DE NIÑAS, NIÑOS Y ADOLESCENTES DEL ESTADO DE GUERRERO"
    ) == "Civil y Familiar"


# Formato de la Cámara de Diputados (LNETB, DOF 16-07-2025): encabezado corrido en cada página,
# contador "N de M" y "Transitorios" en minúsculas; el transitorio segundo abroga la LGMR.
PAGINA_DIPUTADOS = """LEY NACIONAL PARA ELIMINAR TRÁMITES BUROCRÁTICOS
CÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN
Secretaría General
Secretaría de Servicios Parlamentarios
Nueva Ley DOF 16-07-2025
{n} de 30
"""


def _ley_diputados():
    cuerpo = [
        "Artículo 1. La presente Ley es de orden público.",
        "Artículo 2. Son objetivos de esta Ley eliminar",
        "trámites innecesarios.",  # la oración cruza la página
        "Artículo 3. Para los efectos de esta Ley se entenderá.",
        "Artículo 4. El Reglamento establecerá las disposiciones.",
        "Transitorios",
        "Primero.- El presente Decreto entrará en vigor al día siguiente de su publicación.",
        "Segundo.- Se abroga la Ley General de Mejora Regulatoria, publicada en el Diario Oficial de la "
        "Federación el 18 de mayo de 2018.",
        "Ciudad de México, a 9 de julio de 2025.- Rúbricas.",
        "Miércoles 16 de julio de 2025 DIARIO OFICIAL (Edición Vespertina) 291",
    ]
    return "".join(PAGINA_DIPUTADOS.format(n=i + 1) + linea + "\n" for i, linea in enumerate(cuerpo))


def test_formato_diputados_quita_encabezados_corridos():
    articulos = parse_articulos(_ley_diputados())
    assert articulos[1]["texto"] == "Son objetivos de esta Ley eliminar trámites innecesarios."
    assert not any("CÁMARA" in a["texto"] or "TRÁMITES BUROCRÁTICOS" in a["texto"] for a in articulos)


def test_transitorios_originales_se_conservan():
    por_titulo = {a["titulo"]: a["texto"] for a in parse_articulos(_ley_diputados())}
    assert por_titulo["Transitorio Segundo"].startswith("Se abroga la Ley General de Mejora Regulatoria")
    assert "Artículo 4" in por_titulo and "Rúbrica" not in " ".join(por_titulo.values())


def test_fecha_formato_diputados():
    assert _ultima_reforma(_ley_diputados()) == "DOF 16-07-2025"
