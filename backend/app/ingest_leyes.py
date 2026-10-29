"""Ingesta de leyes en PDF desde fuentes oficiales, guiada por catálogos CSV revisables.

Catálogos en app/corpus/*.csv (numero, nombre, area, url):
- catalogo_guerrero.csv: todo el portal de legislación del H. Congreso de Guerrero
  (https://congresogro.gob.mx/legislacion/), generado con el subcomando `catalogo`.
- catalogo_federal.csv: leyes federales/nacionales de la Cámara de Diputados, a mano.
Igual que la LFT, los PDF se descargan en cada ingesta y no se versionan.

  docker compose exec backend python -m app.ingest_leyes catalogo   # regenera el CSV de Guerrero
  docker compose exec backend python -m app.ingest_leyes            # ingiere todos los catálogos
  docker compose exec backend python -m app.ingest_leyes app/corpus/catalogo_federal.csv   # solo uno

El mismo parser lo usa la subida de documentos (app/documents.py) cuando el PDF subido es una ley.

Formato real de los PDF (por qué existe cada limpieza de abajo):
- Cada página repite "H. Congreso del Estado de Guerrero", "S.S.P./D.P.L.", el número de página y el
  título de la ley con letras triplicadas ("LLLEEEYYY DDDEEE ...", artefacto de las negritas).
- Notas de reforma intercaladas: "(REFORMADO, P.O. EDICIÓN 13 ...)" antes del artículo que modifican.
- Encabezados: "Artículo 1.-", "Artículo 5. -", "ARTICULO 1. -", "Artículo 1." (Constitución), "24 BIS".
- El Código Penal abre con la exposición de motivos, que cita tratados con su propio "Artículo 1"; por
  eso se toma la cadena de numeración más larga, no el primer "Artículo 1" que aparezca.
- Al final: "TRANSITORIOS" (a veces "T R A N S I T O R I O S", o "Transitorios" en los de Diputados) y
  el historial de decretos de reforma. Se conservan los transitorios del decreto ORIGINAL (hasta la
  primera "Rúbrica"): ahí dicen cuándo entra en vigor la ley y qué leyes abroga (la LNETB abroga la
  Ley General de Mejora Regulatoria en su transitorio segundo). El historial de reformas se descarta.
- Diputados y el DOF repiten en cada página el nombre de la ley, "CÁMARA DE DIPUTADOS...", "1 de 30" o
  "Miércoles 16 de julio de 2025 DIARIO OFICIAL (Edición Vespertina) 291". Un encabezado que cae a
  media oración rompe la verificación de citas que cruzan la página, por eso se quitan.
"""

import csv
import html
import logging
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin

import httpx
from pypdf.errors import PdfReadError
from qdrant_client.http import models as qmodels

from app.ingest_lft import _extraer_texto
from app.rag import COLLECTION_NAME, embed_passages, ensure_collection, get_embedder, get_qdrant, stable_point_id

logger = logging.getLogger(__name__)

PORTAL = "https://congresogro.gob.mx/legislacion/"
PAGINAS = ("codigos.php", "leyes-organicas.php", "leyes-ordinarias.php")
CORPUS = Path(__file__).resolve().parent / "corpus"
CATALOGO = CORPUS / "catalogo_guerrero.csv"
CAMPOS_CATALOGO = ("numero", "nombre", "area", "url")

# Fragmentos ≤ ~2000 caracteres: e5-small solo "ve" ~512 tokens, y 4 artículos enteros de la
# Constitución (hay de >10 000 caracteres) harían el prompt lentísimo en CPU.
MAX_CHARS_FRAGMENTO = 2000
# Hueco máximo entre artículos consecutivos de la cadena principal (artículos derogados sin encabezado).
SALTO_MAX = 50

_FILA_RE = re.compile(r'<td>\s*(\d+)\s*</td>\s*<td>\s*<a href="([^"]+\.pdf)"[^>]*>(.*?)</a>', re.S | re.I)
# La Constitución y la Ley reglamentaria solo están en el menú, con un <img> antes del texto.
_MENU_RE = re.compile(
    r'<a href="([^"]+\.pdf)"[^>]*>(?:\s*<img[^>]*>)?\s*(Constituci[oó]n Pol[ií]tica|Ley reglamentaria)\s*<', re.I
)
_NOMBRES_MENU = {
    "constitución política": "CONSTITUCIÓN POLÍTICA DEL ESTADO LIBRE Y SOBERANO DE GUERRERO",
    "ley reglamentaria": "LEY REGLAMENTARIA DEL EJERCICIO PROFESIONAL PARA EL ESTADO LIBRE Y SOBERANO DE GUERRERO",
}

# Primera coincidencia gana; el resto cae en "Administrativo y Fiscal". Heurística por nombre, con
# patrones específicos a propósito ("CIVIL" a secas metía "Protección Civil" y "Sociedad Civil" en
# Civil y Familiar). El CSV generado es lo que manda, y debe revisarlo un abogado.
_AREAS = (
    ("Constitucional y Electoral", r"CONSTITUCI[OÓ]N POL|ELECTORAL|COMISAR[IÍ]AS|\bDE PARTICIPACI[OÓ]N CIUDADANA"),
    ("Penal", r"C[OÓ]DIGO PENAL|EJECUCI[OÓ]N PENAL|JUSTICIA PARA ADOLESCENTES|EXTINCI[OÓ]N DE DOMINIO|TORTURA|"
              r"TRATA DE PERSONAS|DESAPARICI[OÓ]N DE PERSONAS|V[IÍ]CTIMAS|DEFENSOR[IÍ]A P[UÚ]BLICA|AMNIST[IÍ]A|"
              r"SUJETOS PROTEGIDOS|FISCAL[IÍ]A GENERAL|BIENES ASEGURADOS|DELINCUENCIA"),
    # Apartado B (servidores públicos) separado del A (LFT): con una sola área "Laboral", las leyes de
    # burócratas desplazaban a la LFT en preguntas de trabajadores privados (Arts. 110, 170 y 518 de
    # los casos del diagnóstico dejaron de llegar al contexto). La Ley 175 del Centro de Conciliación
    # Laboral concilia conflictos del apartado A, por eso queda en "Laboral".
    ("Laboral burocrático", r"TRABAJO DE LOS SERVIDORES|TRABAJADORES AL SERVICIO DEL ESTADO|"
                            r"SEGURIDAD SOCIAL DE LOS SERVIDORES|REMUNERACIONES DE LOS SERVIDORES"),
    ("Laboral", r"CONCILIACI[OÓ]N LABORAL|\bTRABAJO\b"),
    ("Civil y Familiar", r"C[OÓ]DIGO (?:PROCESAL )?CIVIL|REGISTRO CIVIL|DIVORCIO|NOTARIADO|CONDOMINIO|REGISTRAL|"
                         r"INMOBILIARIAS|VOLUNTAD ANTICIPADA|DERECHOS DE NIÑAS|ARANCELARIA|"
                         r"VIDA LIBRE DE VIOLENCIA|ADULTAS MAYORES"),
)
AREA_POR_DEFECTO = "Administrativo y Fiscal"

# Líneas de ruido de página. Las de letras triplicadas exigen ≥ 9 caracteres para no borrar una
# fracción suelta como "III." o "XXXIII.-".
_RUIDO_RE = re.compile(
    r"(?m)^[ \t]*(?:H\. Congreso del Estado de Guerrero|S\.S\.P\./D\.P\.L\.|\d+|\d+ de \d+|.*\bDIARIO OFICIAL\b.*"
    r"|(?=\S.{8,})(?:(?:(\S)\1\1)+[ \t]*)+\S{0,2})[ \t]*$"
)
# Encabezados corridos que no tienen patrón fijo (el nombre de la ley en cada página de Diputados):
# una línea larga que se repite tal cual en varias páginas no es contenido.
MIN_REPETICIONES_ENCABEZADO = 4
MIN_CHARS_ENCABEZADO = 12
_NOTA_REFORMA_RE = re.compile(r"\((?:REFORMAD|ADICIONAD|DEROGAD|FE DE ERRATAS)[^)]*\)", re.I)
# "Artículo"/"ARTÍCULO"/"Art." con mayúscula inicial y separador obligatorio: "...lo dispuesto en el
# \nartículo 29 de este código" (referencia) no es un encabezado, ni "ARTÍCULO 198 DEL" (historial de
# decretos). Con ordinal pegado al número ("1o.-", "Articulo 1°  La" en la Ley 932) el separador es
# opcional. "Art. 1o.-" es el formato de la Ley Arancelaria.
_ARTICULO_RE = re.compile(
    r"(?m)^[ \t]*(?:Art[ií]culo|ART[IÍ]CULO|Art\.|ART\.)[ \t]*(?P<num>\d+)(?:(?P<ord>[oº°])(?![a-záéíóúñ])\.?)?"
    r"(?P<suf>(?i:[ \t]*-?[ \t]*(?:BIS|TER|QU[AÁ]TER|QUINQUIES|[A-Z])\b)*)[ \t]*(?(ord)[.\-–]*|[.\-–]+)[ \t]*-?"
)
_TRANSITORIOS_RE = re.compile(
    r"(?m)^[ \t]*(?:(?:ART[IÍ]CULOS[ \t]+)?T ?R ?A ?N ?S ?I ?T ?O ?R ?I ?O ?S|(?:Art[ií]culos[ \t]+)?Transitorios)[ \t]*\.?[ \t]*$"
)
_FIN_TRANSITORIOS_RE = re.compile(r"R[úu]brica|N\. DE E\.")
_TRANSITORIO_RE = re.compile(
    r"(?im)^[ \t]*(?:ART[IÍ]CULO[ \t]+)?(?P<ord>PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[EÉ]PTIMO|OCTAVO|"
    r"NOVENO|D[EÉ]CIMO(?:[ \t]+(?:PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[EÉ]PTIMO|OCTAVO|NOVENO))?|[UÚ]NICO)"
    r"[ \t]*[.\-–]+"
)
_DEROGADO_RE = re.compile(r"\W*(?:se\s+)?deroga(?:d[oa]s?)?\W*|\W*", re.I)
_ULTIMA_REFORMA_RE = re.compile(
    r"[ÚU]LTIMAS? (?:MODIFICACI|REFORMA).{0,250}?DE FECHA,?\s+(.+?\d{4})"  # Congreso de Guerrero
    r"|(?:Nueva Ley|[ÚU]ltima [Rr]eforma) (DOF \d{2}-\d{2}-\d{4})",  # Cámara de Diputados
    re.S,
)


def clasificar_area(nombre: str) -> str:
    return next((area for area, patron in _AREAS if re.search(patron, nombre.upper())), AREA_POR_DEFECTO)


def generar_catalogo() -> list[dict]:
    """Lee el portal del Congreso y devuelve una fila por PDF vigente (sin duplicados ni abrogadas)."""
    filas: dict[str, dict] = {}
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for pagina in PAGINAS:
            respuesta = client.get(urljoin(PORTAL, pagina))
            respuesta.raise_for_status()
            contenido = respuesta.text
            encontrados = _FILA_RE.findall(contenido) + [("0", h, t) for h, t in _MENU_RE.findall(contenido)]
            for numero, href, nombre in encontrados:
                nombre = " ".join(html.unescape(re.sub(r"<[^>]+>", "", nombre)).split())
                nombre = _NOMBRES_MENU.get(nombre.lower(), nombre)
                if "ABROGAD" in nombre.upper():
                    print(f"  Excluida (abrogada): {nombre}")
                    continue
                url = urljoin(urljoin(PORTAL, pagina), href)
                filas.setdefault(url, {"numero": numero, "nombre": nombre, "area": clasificar_area(nombre), "url": url})
    return list(filas.values())


def _limpiar(texto: str) -> str:
    lineas = _RUIDO_RE.sub("", texto).split("\n")
    conteo = Counter(linea.strip() for linea in lineas)
    encabezados = {
        linea for linea, n in conteo.items()
        if n >= MIN_REPETICIONES_ENCABEZADO and len(linea) >= MIN_CHARS_ENCABEZADO and not _ARTICULO_RE.match(linea)
    }
    return _NOTA_REFORMA_RE.sub("", "\n".join(l for l in lineas if l.strip() not in encabezados))


def _cadena_principal(encabezados: list[re.Match]) -> list[re.Match]:
    """La secuencia creciente más larga que empieza en el Artículo 1 (descarta citas de tratados, etc.)."""
    mejor: list[re.Match] = []
    for k, inicio in enumerate(encabezados):
        if int(inicio["num"]) != 1:
            continue
        cadena = [inicio]
        for m in encabezados[k + 1:]:
            numero, ultimo = int(m["num"]), int(cadena[-1]["num"])
            if numero == 1:
                break  # la numeración reinicia: empieza otro documento (el cuerpo real tras el preámbulo)
            if ultimo <= numero <= ultimo + SALTO_MAX:
                cadena.append(m)
        if len(cadena) > len(mejor):
            mejor = cadena
    return mejor


def _partir(texto: str) -> list[str]:
    """Parte un artículo largo por párrafos en trozos de ≤ MAX_CHARS_FRAGMENTO (un párrafo más largo queda entero)."""
    trozos: list[str] = []
    actual = ""
    for parrafo in (" ".join(p.split()) for p in re.split(r"\n[ \t]*\n", texto)):
        if not parrafo:
            continue
        if actual and len(actual) + len(parrafo) + 1 > MAX_CHARS_FRAGMENTO:
            trozos.append(actual)
            actual = parrafo
        else:
            actual = f"{actual} {parrafo}".strip()
    return trozos + [actual] if actual else trozos


def parse_articulos(texto_completo: str) -> list[dict]:
    texto = _limpiar(texto_completo)
    cadena = _cadena_principal(list(_ARTICULO_RE.finditer(texto)))
    if not cadena:
        return []
    fin_marcador = _TRANSITORIOS_RE.search(texto, cadena[0].start())
    fin = fin_marcador.start() if fin_marcador else len(texto)
    cadena = [m for m in cadena if m.start() < fin]

    articulos: list[dict] = []
    for idx, m in enumerate(cadena):
        etiqueta = " ".join(f"{m['num']} {m['suf']}".split()).upper().replace(" -", "-").replace("- ", "-")
        cuerpo = texto[m.end(): cadena[idx + 1].start() if idx + 1 < len(cadena) else fin]
        _agregar(articulos, etiqueta, f"Artículo {etiqueta}", cuerpo)

    if fin_marcador:  # transitorios del decreto original: vigencia y leyes que abroga
        cierre = _FIN_TRANSITORIOS_RE.search(texto, fin)
        bloque = texto[fin_marcador.end(): cierre.start() if cierre else len(texto)]
        transitorios = list(_TRANSITORIO_RE.finditer(bloque))
        for idx, m in enumerate(transitorios):
            ordinal = " ".join(m["ord"].split()).capitalize()
            cuerpo = bloque[m.end(): transitorios[idx + 1].start() if idx + 1 < len(transitorios) else len(bloque)]
            _agregar(articulos, f"TRANSITORIO {ordinal.upper()}", f"Transitorio {ordinal}", cuerpo)
    return articulos


def _agregar(articulos: list[dict], numero: str, titulo: str, cuerpo: str) -> None:
    if _DEROGADO_RE.fullmatch(cuerpo):
        return  # "Artículo 2942.- Derogado": nada que consultar y ensucia la búsqueda
    partes = _partir(cuerpo)
    for n, parte in enumerate(partes, start=1):
        articulos.append({"numero": numero, "titulo": titulo, "texto": parte, "parte": n, "partes": len(partes)})


def _ultima_reforma(texto_completo: str) -> str | None:
    m = _ULTIMA_REFORMA_RE.search(texto_completo[:3000])
    return " ".join((m.group(1) or m.group(2)).split()) if m else None


def _ingerir_ley(client, fila: dict, pdf_bytes: bytes) -> int:
    texto = _extraer_texto(pdf_bytes)
    articulos = parse_articulos(texto)
    if not articulos:
        return 0
    reforma = _ultima_reforma(texto)
    sufijo_fuente = f"{fila['nombre']} (última reforma: {reforma})" if reforma else fila["nombre"]

    ocurrencias: dict[str, int] = {}
    puntos = []
    vectores = embed_passages([a["texto"] for a in articulos])
    for articulo, vector in zip(articulos, vectores):
        if articulo["parte"] == 1:
            ocurrencias[articulo["numero"]] = ocurrencias.get(articulo["numero"], 0) + 1
        parte = f" (parte {articulo['parte']} de {articulo['partes']})" if articulo["partes"] > 1 else ""
        semilla = f"GRO:{fila['url']}:{articulo['numero']}:{ocurrencias[articulo['numero']]}:{articulo['parte']}"
        puntos.append(
            qmodels.PointStruct(
                id=stable_point_id(semilla),
                vector=vector.tolist(),
                payload={
                    "texto": articulo["texto"],
                    "fuente": f"{articulo['titulo']}{parte}, {sufijo_fuente}",
                    "area": fila["area"],
                    "ley": fila["nombre"],
                    "url": fila["url"],
                    "ultima_reforma": reforma,
                    "capitulo_especial": None,
                },
            )
        )

    # Re-ingesta limpia: si la ley perdió artículos desde la última vez, no deben quedar huérfanos.
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=qmodels.Filter(must=[qmodels.FieldCondition(key="url", match=qmodels.MatchValue(value=fila["url"]))]),
    )
    for i in range(0, len(puntos), 256):
        client.upsert(collection_name=COLLECTION_NAME, points=puntos[i:i + 256])
    return len(puntos)


def _reportar_huerfanos(client, urls_catalogo: set[str]) -> None:
    """Avisa de leyes indexadas que ya no están en ningún catálogo, sin borrarlas.

    Caso real (2026-10-25): la Ley 281 de Seguridad Pública desapareció del listado del portal aunque su
    PDF sigue publicado. Salir del listado no prueba que esté abrogada: lo decide una persona y se
    borra a mano (filtro por "url" en Qdrant).
    """
    conteo: dict[str, int] = {}
    offset = None
    while True:
        puntos, offset = client.scroll(COLLECTION_NAME, limit=1000, offset=offset, with_payload=["url"])
        for p in puntos:
            url = p.payload.get("url")
            if url and url not in urls_catalogo:  # sin url: LFT y fixtures, que tienen su propio ingestor
                conteo[url] = conteo.get(url, 0) + 1
        if offset is None:
            break
    for url, n in conteo.items():
        print(f"  AVISO: {n} fragmentos de una ley que ya no está en ningún catálogo: {url}")


def main() -> None:
    if sys.argv[1:] == ["catalogo"]:
        filas = generar_catalogo()
        CATALOGO.parent.mkdir(exist_ok=True)
        with CATALOGO.open("w", newline="", encoding="utf-8") as f:
            escritor = csv.DictWriter(f, fieldnames=CAMPOS_CATALOGO)
            escritor.writeheader()
            escritor.writerows(sorted(filas, key=lambda r: (r["area"], int(r["numero"]))))
        print(f"Catálogo con {len(filas)} documentos en {CATALOGO}. Revisar el área de cada ley antes de ingerir.")
        return

    # Sin argumentos: todos los catálogos. Con rutas: solo esos (ej. corpus/catalogo_federal.csv).
    catalogos = [Path(a) for a in sys.argv[1:]] or sorted(CORPUS.glob("*.csv"))
    filas = []
    for catalogo in catalogos:
        with catalogo.open(encoding="utf-8") as f:
            filas += list(csv.DictReader(f))
    ensure_collection(get_embedder().get_sentence_embedding_dimension())
    client = get_qdrant()

    total, omitidas = 0, []
    with httpx.Client(timeout=120.0, follow_redirects=True) as http:
        for n, fila in enumerate(filas, start=1):
            try:
                respuesta = http.get(fila["url"])
                respuesta.raise_for_status()
                fragmentos = _ingerir_ley(client, fila, respuesta.content)
            except (httpx.HTTPError, PdfReadError, ValueError) as e:
                omitidas.append(f"{fila['nombre']}: {type(e).__name__}: {e}")
                continue
            if not fragmentos:
                omitidas.append(f"{fila['nombre']}: sin artículos reconocibles (¿escaneado o sin numeración?)")
                continue
            total += fragmentos
            print(f"[{n}/{len(filas)}] {fragmentos:5d} fragmentos — {fila['nombre'][:90]}", flush=True)

    print(f"\nListo: {total} fragmentos de {len(filas) - len(omitidas)} documentos.")
    if not sys.argv[1:]:
        _reportar_huerfanos(client, {fila["url"] for fila in filas})
    if omitidas:
        print(f"Omitidos ({len(omitidas)}), revisar a mano:")
        for o in omitidas:
            print(f"  - {o}")


if __name__ == "__main__":
    main()
