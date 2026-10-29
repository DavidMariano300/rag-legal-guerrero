# Investigación: qué LLM usar en RAG Legal Guerrero

**Fecha:** 2026-10-26 · **Estado:** propuesta; la decisión se toma con la prueba propia de la §6.
**Relacionado:** [arquitectura.md](arquitectura.md), [refactorizacion_rag.md](refactorizacion_rag.md) §7–§10.

## 1. Qué necesita el producto (de lo que ya medimos)

| Requisito | Por qué, con evidencia de este proyecto |
|---|---|
| **Razonar si un artículo aplica al supuesto del usuario** | Es la falla que queda. Con el artículo correcto en el contexto, qwen2.5:7b respondió "puedes transferir [5 semanas] sin ir al doctor" (el Art. 170 permite hasta 4 y exige autorización médica), y en otras corridas citó el 517 (plazo del patrón) para un trabajador despedido. La búsqueda ya no es el cuello de botella (refactorizacion_rag.md §10). |
| **Fidelidad al contexto** | Cada cita se verifica contra el texto (`verificar_citas`); un modelo que copia mal ("subsecuiente") o inventa pierde la respuesta entera. |
| **Seguir formato** | Citas «...» (Artículo N) y JSON para las calculadoras (`format: json`). |
| **Español jurídico de México** | Corpus de la LFT, leyes de Guerrero y federales. |
| **Licencia abierta con uso comercial** | Regla del proyecto: 100 % open source, sin APIs de pago. Se prefieren Apache 2.0 / MIT; la licencia de Llama permite uso comercial, pero no es open source según la OSI. |
| **Caber en el hardware** | Ver §2. |

## 2. Dónde va a correr: dos escenarios muy distintos

| | Nube gratuita (producto final, hoy) | Local con GPU (desarrollo, demos) |
|---|---|---|
| Hardware | Oracle Always Free: **2 OCPU ARM, 12 GB RAM, sin GPU** | RTX 5060 Laptop, **8 GB VRAM** |
| Memoria para el LLM | ~5 GB (comparte con Qdrant, Postgres, backend, embeddings bge-m3 ≈ 2.3 GB) | ~7 GB con contexto |
| Lo que limita | En CPU, la velocidad depende del ancho de banda de memoria: a menos parámetros **activos**, más rápido. Leer el prompt (~3–5 mil tokens de artículos) domina la latencia. | Que pesos + caché quepan en 8 GB. |
| Referencia medida | qwen2.5:7b en 16 núcleos x86: 60–100 s por respuesta. En 2 núcleos ARM sería varias veces más lento. | qwen2.5:7b en la RTX 5060: **1–6 s** por respuesta (2026-10-26). |

Consecuencia: **un mismo modelo no sirve igual para los dos escenarios.** Se puede desarrollar con uno
más grande en la GPU, pero lo que se entregue en la nube gratuita tiene que ser pequeño o tener pocos
parámetros activos. La otra salida es presupuestar una VM con GPU.

## 3. Candidatos 2026 (pesos abiertos)

Tamaños de descarga de Ollama en Q4_K_M, salvo que se indique otra cosa.

| Modelo | Publicado | Licencia | Tamaño Q4 | Notas para este producto |
|---|---|---|---|---|
| **qwen2.5:7b** (actual) | 2024 | Apache 2.0 | 4.7 GB | Línea base medida. |
| **Qwen3.5 4B** | mar 2026 | Apache 2.0 | 3.3 GB | Modelo de "pensamiento" (razona antes de responder): útil para la falla de aplicabilidad, pero gasta muchos tokens. Contexto de 256K. |
| **Qwen3.5 9B** | mar 2026 | Apache 2.0 | 6.6 GB | Cabe justo en la GPU de 8 GB; demasiado lento para 2 núcleos ARM. |
| **Gemma 4 E2B / E4B** | abr 2026 | Apache 2.0 (Gemma 3 tenía licencia propia) | 4.6 / 6.6 GB | ~2.3B / 4.5B parámetros efectivos; multimodal (texto, imagen, audio), por eso pesa más de lo que sugiere su tamaño efectivo. Preentrenado en más de 140 idiomas. |
| **Gemma 4 12B** | jun 2026 | Apache 2.0 | 7.7–8 GB | No cabe con holgura en 8 GB de VRAM. |
| **Gemma 4 26B-A4B** (MoE) | abr 2026 | Apache 2.0 | 16–18 GB | 3.8B activos: rápido en CPU, pero no cabe en 12 GB ni en 8 GB. |
| **Granite 4.0 Tiny-H** (7B, 1B activo) | oct 2025 | Apache 2.0 | 4.2 GB | Híbrido Mamba/MoE con **1B activo**: el más prometedor para CPU. IBM lo orienta a RAG y lista el español entre sus idiomas. |
| **Granite 4.0 Micro** (3B) | oct 2025 | Apache 2.0 | 1.9–2.1 GB | Opción mínima para CPU. |
| Llama 3.1 8B | 2024 | Llama Community (no OSI) | ~4.9 GB | Entre los mejores en español en La Leaderboard 2025, pero de 2024 y con licencia no abierta. |
| Salamandra 7B / ALIA 40B (BSC) | 2025–26 | Apache 2.0 | — | Hechos para el español de España; en La Leaderboard quedan detrás de los modelos generales en español. El de 40B no cabe. |
| Latam-GPT (CENIA) | feb 2026 | Llama 3.1 Community | ~40 GB Q4 | 70B, con español latinoamericano; inviable en nuestro hardware. |

## 4. Qué dice la evidencia pública (y qué no)

- **No existe un benchmark de razonamiento jurídico en español con modelos de 2026.** El más cercano,
  [La Leaderboard](https://aclanthology.org/2025.acl-long.1561/) (ACL 2025), evaluó modelos de 2024: en
  español quedaron arriba Gemma-2-9B y Llama-3.1-8B, prácticamente empatados (≈59 puntos).
  [LEXAM](https://proceedings.iclr.cc/paper_files/paper/2026/file/47cbdfce2fc71cd473bd7d409cd1bf4b-Paper-Conference.pdf)
  (ICLR 2026) y [LegalBench](https://proceedings.neurips.cc/paper_files/paper/2023/file/89e44582fd28ddfea1ea4dcb0ebbf4b0-Paper-Datasets_and_Benchmarks.pdf)
  no incluyen español.
- **Fidelidad al texto fuente** ([leaderboard de alucinación de Vectara](https://github.com/vectara/hallucination-leaderboard),
  mide resúmenes, no RAG; espejo de terceros de primavera de 2026): Gemma 3 12B 95.6 %, Qwen3 8B 95.2 %,
  Granite 4.0 (H-Small) 94.8 %, Gemma 4 26B-A4B 94.8 %, Qwen3 4B 94.3 %, Gemma 3 4B 93.6 %. Diferencias
  de un punto: no alcanzan para ordenar.
- **RAG legal en español:** un [estudio de 2025](https://aclanthology.org/2025.ldk-1.16.pdf) probó Mistral,
  Llama 3.2 y Granite 3 sobre corpus legales españoles; encontró que mejorar la búsqueda con terminología
  controlada ayuda más que cambiar de modelo.
- **Conclusión:** la evidencia pública sirve para hacer la lista corta, no para elegir. **La decisión
  tiene que salir de nuestras propias preguntas**, y con la GPU eso cuesta minutos.

## 5. Lista corta

| Escenario | Candidatos | Por qué |
|---|---|---|
| Nube gratuita (CPU, ≤ ~5 GB) | **Granite 4.0 Tiny-H**, **Qwen3.5 4B** (sin pensamiento), **Gemma 4 E2B** | 1B activo; el mejor 4B nuevo; el más pequeño de Gemma 4. Todos Apache 2.0. |
| Local con GPU (≤ ~7 GB) | **Qwen3.5 9B**, **Gemma 4 E4B**, qwen2.5:7b (base) | Lo mejor que cabe en 8 GB; Qwen3.5 permite medir si "pensar" corrige la falla de aplicabilidad. |

## 6. Cómo decidir: prueba propia

1. **Preguntas:** ampliar los 10 casos con artículo correcto conocido a unos 20 (más preguntas de
   aplicabilidad del tipo "¿aplica a mi caso?", que es donde falla el 7B), con la respuesta correcta
   escrita y verificada contra el texto oficial.
2. **Medir por modelo, 3 corridas:** respuestas correctas / parciales / **incorrectas** / rechazos (una
   incorrecta pesa más que un rechazo: el usuario es un abogado que confía en la cita), citas que pasan
   la verificación, JSON válido de las calculadoras y latencia en GPU.
3. **Para los candidatos de nube:** medir además la latencia en CPU limitada a 2 núcleos
   (`OLLAMA_NUM_THREADS=2` / `taskset`) como aproximación de la VM ARM, hasta poder correr el spike real.
4. **Criterio:** primero el menor número de respuestas incorrectas; luego más correctas; luego latencia.

**Requisito técnico:** el Ollama del contenedor (`ollama/ollama:0.3.14`) no puede correr Qwen3.5,
Gemma 4 ni Granite 4; hay que actualizar la imagen (lo cual también hace falta para la serie RTX 50).
La prueba se puede correr ya con el Ollama nativo del host (0.22.0, con GPU).

## 7. Resultados de la prueba propia (2026-10-26)

**Condiciones:** 21 preguntas (10 originales y 11 nuevas, varias de "¿aplica a mi caso?") × 3 corridas =
63 respuestas por modelo; pipeline real (`answer_query`) con búsqueda fija (bge-m3 + 5 del vector) para
medir solo el LLM; LLM en la RTX 5060 vía Ollama 0.40.11; Qwen3.5 y Gemma 4 sin "pensamiento"
(`OLLAMA_THINK=false`), como correrían en la nube. Calificación manual de cada respuesta.

**Antes de esta prueba se corrigió un bug que invalidaba las anteriores:** Ollama recortaba por el
principio los prompts más largos que su contexto (2048 tokens en el contenedor, 4096 en el host), es
decir, el system prompt completo (45 de 299 llamadas registradas en el contenedor). Ahora el contexto
se pide explícito (8192) y el prompt se arma para que quepa (`rag._armar_prompt`).

| Modelo | Q4 | ✔ Correctas | ◐ Parciales | ✘ Incorrectas | ○ Rechazos | Latencia GPU (mediana) |
|---|---|---|---|---|---|---|
| **qwen3.5:4b** | 3.3 GB | **46 (73 %)** | 5 | **4** | 8 | 10 s |
| qwen2.5:7b (anterior) | 4.7 GB | 33 (52 %) | 12 | 6 | 12 | 11 s |
| granite4:tiny-h | 4.2 GB | 16 | 6 | 8 | 33 | 9 s |
| gemma4:e2b | 4.6 GB | 5 | 3 | 1 | 54 | 11 s |
| qwen2.5:3b | 1.9 GB | 6 | 0 | 0 | 57 | 8 s |

Lo que distingue a qwen3.5:4b es justo la falla que se buscaba corregir, la **aplicabilidad**:
- "Renuncié después de **10** años, ¿me deben prima de antigüedad?" (Art. 162 exige 15): qwen3.5:4b
  respondió "No" en 3 de 3; qwen2.5:7b, "Sí, te deben pagar" (✘).
- Transferir 5 semanas prenatales sin médico: qwen3.5:4b "hasta cuatro semanas, y sí requiere
  autorización médica" (2 de 3); granite4 "Sí, puedes transferir 5 sin ir al médico" (✘).

Fallas de cada uno:
- **qwen3.5:4b:** el caso del plazo (despido hace 4 meses) en las 3 corridas: cita bien el Art. 518 (dos
  meses) y el Art. 47, pero concluye "Sí, estás a tiempo". Es un error de comparación numérica
  sistemático; candidato a resolverse en Python como las calculadoras (plazos de prescripción).
- **granite4:tiny-h:** cita artículos equivocados con seguridad (Art. 874 para la falta de aviso,
  Art. 395 de hermanos para la obligación de los hijos).
- **gemma4:e2b:** no pone comillas en sus citas ("...días multa (Artículo 219)"), así que
  `verificar_citas` las rechaza; además citó el Art. 390 (padres→hijos) para una pregunta hijos→padres.
  Seguir el formato es requisito del producto.
- **qwen2.5:3b:** casi siempre se rechaza a sí mismo con el prompt completo.

### Latencia en CPU con 2 hilos (aproximación de la VM gratuita)
Mismo Ollama forzado a CPU (`num_gpu: 0`, `num_thread: 2`) en la laptop (x86), con prompts reales:

| Modelo | Total por respuesta | Leer prompt (2.2–2.7 mil tokens) | Escribir |
|---|---|---|---|
| **qwen3.5:4b** | **54–68 s** | 47–59 s (~46 tok/s) | 6–7 s (~13 tok/s) |
| qwen2.5:7b | 73–174 s | 52–109 s | 21–47 s (~6.5 tok/s) |

En CPU domina leer el prompt. Un núcleo Ampere A1 rinde probablemente menos que uno de esta laptop: en la
VM gratuita se estiman **1–2 minutos por respuesta**, más ~10 s de la reescritura. Pendiente medirlo en
la VM real. Formas de bajarlo sin costo, por medir: conservar en caché el system prompt (~1,000 tokens
idénticos en cada consulta; con `OLLAMA_NUM_PARALLEL=2` la reescritura no lo desplazaría de la ranura) y
mandar menos fragmentos del vector (5 → 3).

**Recomendación:** qwen3.5:4b (Apache 2.0) para la nube y para local: más preciso que qwen2.5:7b y
1.5–2.5 veces más rápido en CPU. Requiere actualizar la imagen de Ollama del contenedor (0.3.14 no lo
puede cargar) y `OLLAMA_THINK=false`.

## 8. Hacia la meta del producto (2026-10-26): > 80 % de respuestas correctas, > 90 % de recuperación

**Método.** Evaluador en el repositorio (`backend/eval/evaluar.py`) con dos conjuntos:
- `eval/casos.json` (21 preguntas): con estas se ajustó el sistema; su cifra está inflada.
- `eval/casos_validacion.json` (17 preguntas, una de control que debe rechazarse): se escribieron
  después y no se usaron para ajustar hasta la v3. **Es la cifra que se reporta.**

Cada pregunta × 3 corridas; la exactitud se califica a mano contra la respuesta esperada.

| Versión | Cambios | Validación: recuperación | Validación: correctas | Incorrectas |
|---|---|---|---|---|
| v2 | qwen3.5:4b, contexto 8192, ley mencionada, búsqueda con pregunta + reescritura, sinónimos de régimen, cálculo de prescripción, orden por mejor evidencia, Paso 1 "al menos un fragmento" | 94 % | 69 % (35/51) | 6 |
| v3 | + "razonar antes de concluir" en el prompt | 94 % | — (descartada: el modelo parafraseó en vez de citar y la verificación rechazó 55 %) | — |
| **v4** | v2 + ruta de definiciones ("¿qué se entiende por X?") + conversión de salario explícita en el cálculo | **94 %** | **75 % (38/51)** | **3** |

**Lo que falta para el 80 %:**
1. **Razonamiento sobre requisitos** ("tengo 25 años, ¿puedo adoptar?" → "Sí" en 3/3; el Art. 555 exige
   más de 30). Con el modo pensamiento de Qwen3.5 lo resuelve, pero piensa ~3,000 tokens: 14–43 s en la
   RTX 5060, minutos en CPU. **Solo es viable con GPU en producción.**
2. Rechazos y parciales aleatorios (~1 de cada 12) por la temperatura 0.2.
3. **Muestra chica:** con 17 preguntas, cada una mueve ±6 %. La cifra de aceptación debe salir de
   preguntas reales de los abogados (20–30 con respuesta esperada), que no hayan servido para ajustar.
