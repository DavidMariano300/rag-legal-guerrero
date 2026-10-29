# Refactorización del RAG — Mecanismo Anti-Alucinaciones v2

**Estado:** Implementado y validado contra los 6 casos reales de `docs/diagnostico_rag.csv`. 4 de 6 casos
quedan resueltos de forma consistente; 2 quedan **parcialmente** resueltos (recuperación arreglada,
generación todavía inconsistente en un sub-caso) — ver Sección 4, no se oculta el resultado real.
**Fecha:** 2026-09-25
**Responsable:** Edgar David Mariano Ruiz
**Origen:** prueba de estrés documentada en `docs/diagnostico_rag.csv` (6 casos, no 5 — el "Efecto
Frankenstein" del Caso 6 también se abordó aunque no estaba en el resumen inicial de la solicitud).

---

## 1. Los 6 problemas diagnosticados

| # | Nombre | Síntoma |
|---|---|---|
| 1 | Inversión de roles | Aplicó un plazo procesal del patrón (48h para el Tribunal) al trabajador. |
| 2 | Alucinación matemática | Inventó una fórmula incorrecta (0.5 × 30 = 15) en vez de calcular con los datos reales del usuario. |
| 3 | Miopía narrativa | Lenguaje coloquial ("me encerraron y amenazaron") no encontró los artículos de coacción/nulidad — trajo poderes notariales. |
| 4 | Miopía semántica | "Descontándome" no encontró el artículo de descuentos salariales — trajo el de indemnizaciones. |
| 5 | Cebo numérico | Los números "6" y "2" de la pregunta desviaron la búsqueda hacia un artículo de días de descanso, no de vacaciones. |
| 6 | Efecto Frankenstein | Fusionó un artículo de maternidad con uno de trámites ante tribunales para inventar un procedimiento burocrático inexistente. |

## 2. Los 3 módulos y qué caso resuelve cada uno

### 2.1 `backend/app/prompts/system_prompt_v2.txt` — resuelve Casos 1, 2, 6

Reescritura completa del system prompt (cargado en vivo por `rag.py`, no es un archivo de exhibición).
Estructura en dos pasos explícitos:

- **Paso 1 (portón de decisión, una sola vez):** ¿el contexto es del tema/materia/figura correcta? Si no,
  rechaza y termina ahí. Si sí, **nunca vuelve a considerar rechazar** por otro motivo.
- **Paso 2 (ya con luz verde, responde):** reglas de aislamiento de artículos (Caso 6), asignación de
  roles patrón/trabajador (Caso 1), y cálculo obligatorio con regla de tres cuando el contexto da un
  monto/principio y el usuario da números (Caso 2).

**Por qué esta estructura en dos pasos y no una lista plana de reglas:** la primera versión (una lista de
6 reglas, con "cuándo rechazar" al final) hacía que el modelo, en preguntas que sí requerían cálculo,
terminara rechazando de todas formas — la instrucción de rechazo, al estar al final del prompt, tenía más
peso que la de calcular. Separar explícitamente "decide UNA VEZ si rechazar" de "ya que decidiste
continuar, nunca vuelvas a dudar" redujo (no eliminó del todo — ver Sección 4) ese problema.

### 2.2 `backend/app/retrieval/query_rewriter.py` — resuelve Caso 3, ayuda en 4

Traduce la narración coloquial del usuario a términos de búsqueda legal usando el mismo Ollama ya
desplegado (no se agrega un segundo modelo). Ejemplo real:

```
Entrada: "Me encerraron y amenazaron para firmar mi renuncia. ¿Puedo demandar?"
Salida:  renuncia forzada, coacción laboral, vicios del consentimiento, despido injustificado,
         acción legal por despido abusivo, derecho a la dignidad del trabajador
```

**Costo de esta decisión:** cada consulta ahora hace DOS llamadas al LLM (reescritura + generación) en
vez de una — la latencia total aumenta considerablemente (de ~4-8s a ~15-30s típico con el modelo de 3B
en esta máquina de desarrollo; en la VM ARM64 de producción será más lento todavía).

**Por qué se concatena la pregunta original con la reescrita, no se reemplaza (`rag.py`):** durante la
validación se encontró que el rewriter, al usar un LLM con muestreo, podía dar una reescritura pobre para
la MISMA pregunta en llamadas distintas (ver Sección 4) — concatenar en vez de reemplazar asegura que
palabras que YA funcionaban en la pregunta original (ej. "aguinaldo", "vacaciones") sigan aportando a la
búsqueda aunque el rewriter falle ese día.

### 2.3 `backend/app/retrieval/hybrid_search.py` — resuelve Casos 4 y 5

BM25 (`rank_bm25`, sin LangChain) + búsqueda vectorial existente, fusionados con pesos configurables
(`PESO_BM25=0.4`, `PESO_VECTORIAL=0.6` por defecto). BM25 encuentra coincidencias léxicas exactas
("descuentos", "vacaciones") que el vector por sí solo no siempre prioriza; el vector aporta comprensión
semántica que BM25 no tiene. Ver Sección 4 para dos bugs reales encontrados y corregidos en esta
implementación antes de que funcionara correctamente.

**Por qué no LangChain (`EnsembleRetriever`):** el proyecto ya había decidido no depender de LangChain
(`docs/arquitectura.md`). `rank_bm25` es una librería pura Python sin dependencias pesadas adicionales, y
la fusión de scores (normalizar + promedio ponderado) es un algoritmo simple de menos de 40 líneas —
no justifica adoptar un framework de orquestación completo solo para esto.

---

## 3. Bugs reales encontrados y corregidos durante la implementación

Ninguno de estos se asumió — cada uno se encontró probando el código real, no revisándolo.

1. **Corpus duplicado (2532 puntos en vez de ~1268):** `hash()` nativo de Python está aleatorizado por
   proceso; el mismo artículo generaba un ID de punto distinto en cada reinicio del contenedor, rompiendo
   la idempotencia del upsert. Corregido con `stable_point_id()` (SHA-256) en `rag.py`, aplicado en
   `ingest_lft.py` y `documents.py`.
2. **Tokenizador de BM25 ingenuo:** `texto.lower().split()` trataba `"quincena."` y `"quincena"` como
   palabras distintas. Corregido con una regex que se queda solo con letras y dígitos.
3. **Candidatos BM25 con score vectorial fantasma de 0.0:** un documento que BM25 rankeaba #1 pero que no
   estaba entre los primeros 20 resultados vectoriales recibía un 0.0 falso en esa dimensión al fusionar
   — lo hundía injustamente. Corregido ampliando el pool de candidatos vectoriales de 20 a 100 (el corpus
   es de ~1300 documentos, sigue siendo barato).
4. **Reescritura no determinista:** la temperatura por defecto de Ollama (0.8) hacía que la MISMA
   pregunta, en llamadas consecutivas, generara reescrituras de calidad distinta — y por tanto
   recuperaciones distintas. Corregido bajando `temperature` a 0.1 en el rewriter y a 0.2 en la
   generación final (ver Sección 4 para el caso donde esto todavía no fue suficiente).

---

## 4. Resultado de la validación contra los 6 casos reales (API real, no simulado)

| # | Caso | Recuperación | Generación | Veredicto |
|---|---|---|---|---|
| 1 | Inversión de roles | Mejoró (ya no trae Art. 922/407 del caso original) | "Sí, puedes presentar una demanda" — no repite la inversión de roles | **Corregido** |
| 2 | Alucinación matemática | Encuentra Art. 87 de forma consistente | **Inconsistente**: en prueba aislada con un solo fragmento limpio calculó bien paso a paso ($3,750); en el flujo real con 3 fragmentos (2 de ellos ruido) a veces evade con "no puedo calcular esto" | **Parcialmente corregido** — el bug original (inventar una fórmula incorrecta) no volvió a ocurrir en ninguna prueba, pero la evasión SIGUE ocurriendo a veces |
| 3 | Miopía narrativa | Ya no trae poderes notariales; trae artículos de validez de convenios/renuncia | "Sí, puedes demandar" | **Corregido** |
| 4 | Miopía semántica | Encuentra Art. 110 (descuentos) de forma consistente y con score dominante | "No, no es legal... no puede exceder el veinte por ciento del salario" — respuesta legalmente correcta | **Corregido** |
| 5 | Cebo numérico | Encuentra Art. 76/77 (vacaciones) de forma consistente — el bug de recuperación está resuelto | A veces rechaza responder en vez de comparar la cifra del usuario (8 días) contra la ley — mismo patrón de evasión que el Caso 2 | **Parcialmente corregido** — mismo patrón que el Caso 2 |
| 6 | Efecto Frankenstein | Encuentra Art. 170 (maternidad) correctamente | "No, no puedes" — ya NO inventa el trámite falso ante el Centro Federal de Conciliación | **Corregido** |

### Por qué los Casos 2 y 5 quedan "parcialmente" corregidos, honestamente

Ambos comparten el mismo patrón: la recuperación (el problema que originalmente los causó) está
resuelta y verificada de forma repetida. El problema que queda es distinto — el modelo de generación
(`llama3.2:3b`, 3B parámetros) es **inconsistente** entre llamadas: la misma pregunta, con el mismo
contexto recuperado, a veces calcula/compara correctamente y a veces evade con una negativa genérica. Se
probó y confirmó que el modelo SÍ es capaz de hacer el cálculo correctamente cuando se le da un contexto
limpio de un solo fragmento (ver commit history de este archivo / sesión de trabajo) — el problema
aparece específicamente cuando hay fragmentos adicionales de relevancia parcial en el contexto, que
aparentemente le generan duda suficiente para preferir la opción "segura" de rechazar.

Se intentaron 7 iteraciones distintas de la redacción del prompt para eliminar esto por completo; todas
mejoraron el comportamiento mayoritario pero ninguna lo hizo 100% consistente. Esto es una limitación
real y conocida de usar un modelo de 3B parámetros para una tarea que requiere combinar extracción de
datos, aritmética, y verificación de relevancia simultáneamente — no un error de implementación que
falte corregir con más tiempo de prompt-engineering.

**Nota importante de seguridad:** en ambos casos, la evasión es el fallo — no una alucinación. El bug
ORIGINAL y PELIGROSO reportado en el CSV (inventar una fórmula matemática incorrecta, o afirmar con
seguridad la aplicación de un plazo equivocado) **no volvió a ocurrir en ninguna de las ~10 pruebas
realizadas** contra estos dos casos. El sistema cambió de "a veces se equivoca con confianza" a "a veces
es demasiado cauteloso" — es un cambio en la dirección correcta para una herramienta legal, aunque no sea
la solución completa.

---

## 5. Recomendación para cerrar los Casos 2 y 5 por completo

No es recomendable seguir iterando el prompt indefinidamente — ya se intentaron 7 variantes con
retornos decrecientes. Las siguientes vías son más prometedoras:

1. **Modelo más grande para generación** (ej. `llama3.1:8b` o `qwen2.5:7b`) — modelos más grandes suelen
   manejar mejor instrucciones con múltiples condiciones simultáneas. Costo: más RAM/latencia, a evaluar
   contra el presupuesto de la VM de Oracle Cloud (`docs/arquitectura.md §2.2`).
2. **Reducir el ruido en el contexto**: en vez de pasar siempre `TOP_K=3` fragmentos al LLM, filtrar a
   solo los fragmentos cuyo score esté razonablemente cerca del mejor (ej. dentro del 15% del máximo),
   en vez de forzar siempre 3 aunque el segundo y tercero sean mucho más débiles.
3. **Separar la verificación de relevancia de la generación en dos llamadas explícitas** (en vez de
   pedirle al modelo que haga ambas cosas en un solo prompt) — más latencia, pero cada llamada individual
   es una tarea más simple y probablemente más confiable para un modelo pequeño.

---

## 6. Cómo se validó (no se afirma nada sin evidencia)

Cada uno de los 6 casos se probó contra la **API real corriendo** (`docker compose`, corpus real de la
Ley Federal del Trabajo, 1,268 artículos), con la pregunta **exacta** del CSV, no una paráfrasis. Los
casos 2, 4 y 5 se corrieron múltiples veces para verificar consistencia (no solo un run afortunado). Las
28 pruebas automatizadas existentes (`backend/tests/`) se corrieron después de cada cambio y siguen
pasando. El detalle completo de la sesión de depuración (incluyendo los prompts exactos probados y
descartados) queda en el historial de commits de esta rama.

---

## 7. Segunda ronda (2026-10-10): modelo `qwen2.5:7b` y recuperación por señal

### Cambios
1. **Modelo de generación y reescritura: `qwen2.5:7b`** en vez de `llama3.2:3b`. El de 3B no hacía
   aritmética confiable: en 3 corridas del Caso 2 dio una correcta, una evasión y una **incorrecta**
   ("$41.67" — planteó 15 ÷ 180 en vez de 15 × 6/12). Qwen: 4/4 correctas, incluida una variante con
   números distintos (4 meses a $320 → $1,600) para descartar que copiara el ejemplo del prompt.
2. **Stemming en español para BM25** (`snowballstemmer`): sin él "descuento" ≠ "descuentos".
3. **Score vectorial real para candidatos que solo encontró BM25** (antes recibían 0 y perdían la
   fusión aunque su coseno real fuera normal — Art. 110: 0.852, fuera del top 100 vectorial).
4. **Al LLM le llegan los 2 mejores de BM25 + los 2 mejores del vectorial** (≤ 4 fragmentos), no los
   top-3 fusionados. Ningún peso fijo servía para todos: más peso a BM25 perdía el Art. 518 del Caso 1
   (vectorial #2, BM25 #145); más peso al vector perdía el Art. 76 del Caso 5 (BM25 #1, vectorial #30).
   RRF (lo que usa `EnsembleRetriever`) salió peor: 2–3 de 4.
5. Se probó y **se descartó** un filtro por margen de score (descartar fragmentos a > 0.1 del mejor):
   ayudaba al modelo de 3B, pero con la recuperación nueva tiraba artículos correctos (Art. 110).

### Resultado (API real, respuestas verificadas contra el texto del corpus)

| # | Antes (3B) | Ahora (qwen 7B) |
|---|---|---|
| 1 | Sin inversión de roles, respuesta vaga | ✘ **Peligroso**: "estás a tiempo… hasta dos años". El Art. 518 dice que la acción por despido prescribe en **2 meses**. La reescritura varía entre corridas y a veces el 518 no llega al contexto; cuando falta, qwen rellena con conocimiento propio |
| 2 | Inconsistente (evade o calcula mal) | ✔ $3,750, 4/4 corridas |
| 3 | Respuesta vaga pero sin inventar | ✘ **Peligroso**: atribuye al Art. 407 que "la Secretaría puede desechar la renuncia"; el 407 real solo dice dónde se presenta una solicitud |
| 4 | Correcto | ✔ Correcto y más fundado (distingue topes de 20% y 30%) |
| 5 | Evadía | ✔ "No es correcto, Art. 76: 14 días" |
| 6 | "No, no puedes" (sin explicar) | ✔ "Hasta 4 de las 6 semanas, con autorización médica" — fiel al Art. 170 |

**Lectura honesta:** qwen convirtió las evasiones del modelo de 3B en respuestas útiles y correctas
(2, 5, 6), pero también es más "servicial": cuando el contexto no trae el artículo correcto o es
ambiguo, **inventa con seguridad** en vez de rechazar (1, 3). Para una herramienta legal, ese modo de
falla es más grave que la evasión.

**Nota sobre el Caso 1 del CSV:** la respuesta original ("ya estás fuera del plazo") probablemente tenía
la **conclusión correcta** según el Art. 518 (2 meses), con el razonamiento equivocado (citó el Art. 922).
El diagnóstico del CSV debería revisarse con un abogado.

**Latencia:** ~50–85 s por consulta en CPU local (vs. ~15–30 s con 3B).

## 8. Tercera ronda (2026-10-10): guardrails deterministas A/B/C

Motivo: la §7 mostró que qwen **inventa con seguridad**. Se agregaron tres barreras que no dependen de
que el modelo "se porte bien":

| | Qué hace | Dónde |
|---|---|---|
| **A. Citas verificadas** | La respuesta debe traer al menos una cita sustancial (≥ 20 caracteres) y **cada** cita entre comillas debe aparecer literalmente en el contexto. Con etiqueta `(Artículo N)`, en el fragmento de *ese* artículo. Sin etiqueta, en algún fragmento (o en la pregunta, si cita al usuario). Si no, se sustituye por el mensaje de rechazo y `respaldada=false` | `rag.verificar_citas` |
| **B. Calculadoras** | Aguinaldo (Art. 87), vacaciones (Art. 76, reforma 2022) y prima vacacional (Art. 80) se calculan en Python. El tipo de cálculo lo decide una regex; el LLM solo extrae los números (JSON). Sin antigüedad clara, se da la tabla del Art. 76 | `calculos.py` |
| **C. Régimen especial** | Los artículos del Título Sexto ("Trabajos Especiales") solo entran al contexto si la pregunta menciona su capítulo (ej. "trabajadora del hogar") | `ingest_lft.py`, `hybrid_search._regimen_aplica` |

Ajustes por evidencia:
- qwen usa comillas rectas `"..."` en ~2 de 3 respuestas aunque el prompt pida `«»`, y a veces omite la
  etiqueta. Exigir el formato rechazaba respuestas correctas (Caso 4). **El formato ahora es tolerante,
  pero el contenido es estricto.**
- **No** se toleran erratas dentro de la cita (qwen copió "subsecuiente"). Una tolerancia del ~3 %
  también dejaría pasar un "no" eliminado ("no podrá" → "podrá"), y en texto legal eso es inaceptable.
  Esas respuestas se rechazan.
- `/api/query` devuelve **503** si Ollama no responde en 120 s (antes era un 500 sin manejar). En
  CPU, dos consultas simultáneas bastan para provocarlo.

### Resultado (API real, qwen2.5:7b en CPU)

| # | Resultado | Lectura |
|---|---|---|
| 1 | ✘ Cita real del Art. 519, **mal aplicada**: "estás a tiempo, dos años". El Art. 518 (2 meses) estaba en el contexto | Falla de razonamiento, no de invención: A no la detecta |
| 2 | ✔ $3,750, con cálculo determinista y cita del Art. 87 | |
| 3 | ✘ Cita real del Art. 873 (convenios), **mal aplicada** a una renuncia coaccionada. En otras corridas: rechazo | Igual que el 1 |
| 4 | ✔ Prohibido; cita literal del Art. 110 | Antes de flexibilizar el formato, rechazaba |
| 5 | ✔ "No es correcto", cita literal del Art. 76; a veces omite la cifra de 14 días | En 1 de 4 corridas: rechazo por errata en la cita |
| 6 | Rechazo: alteró el texto del Art. 170 dentro de la cita | Rechazo correcto (no inventa) |
| Hogar | ✔ Art. 333: 9 h nocturnas + 3 h diarias | C no rompe preguntas legítimas de régimen especial |
| Salario mensual | ✔ $15,000/30 × 15 = $7,500 | B convierte en Python |

**Lectura honesta:** A elimina el texto legal **inventado**. En esta ronda se bloquearon citas falsas
como "Corresponde a las empresas otorgar 6 días de vacaciones...", y es la barrera más valiosa. Pero
no detecta un artículo **real aplicado al supuesto equivocado** (Casos 1 y 3). Probar una regla de prompt
("comprueba que el supuesto del artículo es el del usuario") no cambió nada en 2 de 2 corridas y se
retiró. Ese límite es del modelo de 7B. Mitigaciones posibles, en orden de costo:
1. **GPU**: la RTX 5060 (8 GB) no se usa: Ollama corre al 100 % en CPU, porque Docker no tiene el
   runtime de NVIDIA y la imagen `ollama/ollama:0.3.14` no soporta la serie 50. Con GPU, la latencia
   bajaría de ~60–100 s a pocos segundos, lo que haría viable el punto 2.
2. Segunda llamada de verificación ("¿el artículo citado regula el hecho del usuario?").
3. Un modelo de 14B (no cabe completo en 8 GB de VRAM; descarga parcial a RAM).

En cualquier caso, la UI debe presentar la cita y el fragmento como lo principal, y la prosa como
secundaria: el usuario final es un abogado que verifica la fuente.

## 9. Corpus multi-ley (2026-10-10): legislación de Guerrero + LFT, 22,669 fragmentos

Cambios necesarios para pasar de 1 ley a 154:
- **BM25 ignoraba el filtro de área.** No se notaba con un corpus 100 % laboral. Ahora el filtro se
  aplica antes de tomar el top 100.
- **Las calculadoras solo se activan si la búsqueda trajo artículos de la LFT.** Un servidor público
  de Guerrero se rige por la Ley 248 / Ley 51, y darle la cifra de la LFT sería incorrecto.
- El reescritor de consultas recibió ejemplos de familiar y penal (antes solo tenía laborales).

Validación (API real, qwen2.5:7b):

| Consulta (área) | Resultado |
|---|---|
| Servidor público, días de vacaciones (Laboral) | ✔ Ley 51, Art. 22 Bis (2 periodos de 10 días); la calculadora de la LFT no se activa |
| Aguinaldo 6 meses a $500 (Laboral) | ✔ $3,750 con cálculo determinista |
| Amenazas (Penal) | ✘ Recupera el Art. 218 "Amenazas", pero el modelo cita el 238 (violencia vicaria): falla de razonamiento, igual que §8 |
| Edad para ser diputado (Constitucional) | Rechazo: recupera el Art. 46, pero la cita no coincide literalmente |
| Pensión alimenticia (Civil y Familiar) | ✘ Recupera artículos de **sucesiones** que dicen literalmente "pensión alimenticia" (1159, 1174) en vez del capítulo "De los alimentos" |
| Descuento del 50 % (sin área) | ⚠ Responde con la Ley 51 (burócratas); el Art. 110 de la LFT ya no entra en el top |

**Lectura:** con un corpus 18 veces más grande, la recuperación sin filtro de área se diluye, y BM25
premia la frase literal aunque esté en el capítulo equivocado. La mejora más prometedora es indexar
cada artículo junto con su **título y capítulo** (ej. "Código Civil › De los alimentos"), para que la
búsqueda sepa en qué parte de la ley está el texto. El parser ya detecta esos encabezados en la LFT
(`ingest_lft.py`); falta generalizarlo a Guerrero.

## 10. Pruebas del cliente con la LNETB (2026-10-25): vigencia, burócratas y embeddings

### Los dos PDF del cliente
- `LeyesBiblio/pdf/LNETB.pdf`: Ley Nacional para Eliminar Trámites Burocráticos (texto de Diputados).
- `LeyesBiblio/abro/lgmr/LGMR_abro_16jul25.pdf`: **no es el texto de la Ley General de Mejora
  Regulatoria**. Es el decreto del DOF del 16-07-2025 que *expide la LNETB*; sus 114 artículos son los
  mismos, y su Transitorio Segundo abroga la LGMR. Se ingirió solo la LNETB en el corpus
  (`corpus/catalogo_federal.csv`); cargar los dos habría duplicado cada artículo en el contexto.

### Cambios
| Cambio | Por qué |
|---|---|
| `ingest_guerrero.py` → `ingest_leyes.py`, con catálogos CSV múltiples | Ya ingiere también leyes federales de Diputados |
| Encabezados de Diputados/DOF y líneas repetidas en cada página se eliminan | Un encabezado a media oración rompía la verificación de citas que cruzan la página |
| Se conservan los **transitorios del decreto original** | Ahí está "Se abroga la Ley General de Mejora Regulatoria" |
| La **subida de documentos** fragmenta por artículo cuando el PDF es una ley y busca con BM25 + vector | Con trozos fijos y la fuente sin número de artículo, la verificación rechazaba toda cita "(Artículo N)" de un documento subido |
| Área nueva **"Laboral burocrático"** (Leyes 18, 51, 248, 912) separada de "Laboral" (LFT y Ley 175) | Las leyes de servidores públicos desplazaban a la LFT: los Arts. 110, 170 y 518 del diagnóstico dejaron de llegar al contexto |
| **Vigencia determinista** (`app/vigencia.py`) | Ver abajo |
| El ingestor avisa de leyes indexadas que ya no están en ningún catálogo (no las borra) | La Ley 281 de Seguridad Pública salió del listado del portal; su PDF sigue publicado |

### Vigencia: el modelo contradecía al transitorio
A "¿Sigue vigente la Ley General de Mejora Regulatoria?", qwen2.5:7b respondió **"Sí"**, citando el
Art. 35 de la Ley 455 estatal (que la nombra como supletoria), con el Transitorio Segundo de la LNETB en
el contexto. Siguió diciendo "Sí" con un aviso explícito en el contexto y una regla en el prompt. Igual
que con los cálculos, la respuesta no depende del modelo:
- Al construir el índice se leen los **transitorios** del corpus ("Se abroga la Ley ..."): 57 leyes.
- Pregunta de vigencia que nombra una ley abrogada → respuesta armada en Python con la cita literal del
  transitorio (no pasa por el LLM).
- Cualquier otra respuesta cuyo contexto nombre una ley abrogada → se le anexa una nota del sistema.
- Se descartan los nombres contenidos en el de una ley vigente (la Ley Orgánica del Poder Legislativo
  231 abrogó a otra que se llamaba igual, sin número), y las abreviaturas ("No. 159") no cortan el nombre.
  Las dos fallas habrían marcado como abrogadas leyes vigentes.

### Comparación de embeddings
Dashboard: https://claude.ai/artifact/QLg1pKEoPcbk7kgJVb161t. Diez preguntas con artículo correcto
conocido; cada modelo ordena unos 250 candidatos por pregunta (top 200 BM25 + top 100 del vector actual
+ el correcto).

| Modelo | MRR | 1er lugar | En top 5 | Peor lugar | Llega al LLM con 2 / 3 / 5 del vector |
|---|---|---|---|---|---|
| multilingual-e5-small (actual) | 0.416 | 2 | 6 | 101 | 7 / 7 / 7 |
| multilingual-e5-base | 0.553 | 4 | 7 | 46 | 7 / 8 / 8 |
| SINAI legal-administrativo | 0.515 | 3 | 8 | 34 | 7 / 7 / 9 |
| **bge-m3** | **0.683** | **6** | **9** | **22** | 7 / **8** / **9** |

SINAI (entrenado en derecho administrativo español) separa mejor los cosenos, pero ordena peor que
bge-m3.

### Confirmación con el corpus completo (bge-m3 re-embebido, sistema real)
El corpus se re-embebió con bge-m3 en `legal_corpus_bge_m3` (`app/reembeber.py`; ~7 min en la RTX 5060
desde un venv del host, contra ~2 h estimadas en CPU). La colección de e5-small queda de respaldo.

Lugar del artículo correcto en la búsqueda vectorial sobre **toda** la colección del área: bge-m3 lo pone
1º en 7 de 10 preguntas (e5-small: 4) y su peor caso queda 39º (e5-small: 103º). Pero con la selección
de 2 fragmentos del vector perdía casos donde el correcto quedaba 4º o 5º, así que el lado vectorial
pasa a aportar 5 (`TOP_K_VECTOR`, BM25 sigue en 2).

Respuestas completas, 3 corridas × 10 preguntas, calificadas a mano (LLM qwen2.5:7b en GPU):

| Configuración | Correctas | Parciales | Incorrectas | Rechazos |
|---|---|---|---|---|
| e5-small + 2 del vector (anterior), 1 corrida | 2 / 10 | 2 | 3 | 3 |
| e5-small + 5 del vector | 9 / 30 | 9 | 0 | 12 |
| **bge-m3 + 5 del vector (nueva)** | **17 / 30** | 9 | 0 | 4 |

Nota sobre el caso del plazo: bge-m3 trae el Art. 47 y responde "aún estás dentro del plazo si no
recibiste el aviso de rescisión". Es correcto (Art. 47: la prescripción "no comenzará a correr sino
hasta que el trabajador reciba personalmente el aviso de rescisión"); e5-small cita el 518 (dos meses).
Cada uno cubre una rama de la respuesta completa: se calificaron como parciales.

Aplicado (2026-10-26): `EMBEDDING_MODEL=BAAI/bge-m3`, `QDRANT_COLLECTION=legal_corpus_bge_m3`,
`TOP_K_VECTOR=5` en `docker-compose.yml`; bge-m3 y Whisper quedan horneados en la imagen
(`HF_HUB_OFFLINE=1`: el contenedor ya no consulta huggingface.co al arrancar). Para regresar a
e5-small: cambiar las cuatro variables y reconstruir.
