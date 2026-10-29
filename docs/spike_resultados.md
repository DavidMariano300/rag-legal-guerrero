# Resultados del Spike Técnico — Validación Local

**Estado:** Spike parcial completado (validación de arquitectura en local, x86_64). Pendiente el spike en la VM real de Oracle Cloud (ARM64) — ver [arquitectura.md §6](arquitectura.md).
**Fecha:** 2026-09-23
**Responsable:** Edgar David Mariano Ruiz

---

## 1. Qué se validó

Se levantó el stack completo (`docker-compose.yml`: Ollama, Qdrant, PostgreSQL, backend FastAPI) en una máquina local x86_64 (16 cores / 22 GB RAM) y se probó el flujo completo de una consulta:

1. Ingesta de un corpus de prueba **ficticio** (`fixtures/sample_corpus.md`) → embeddings → Qdrant.
2. Consulta vía `POST /query` → recuperación de fragmentos relevantes → generación con `llama3.2:3b` vía Ollama.
3. Verificación de que la respuesta sigue el formato híbrido exigido (respuesta conversacional + fragmentos citados con fuente + disclaimer de IA).

## 2. Resultado

**Éxito.** Ejemplo real de la prueba:

- **Pregunta:** "¿Cuál es el plazo para contestar una demanda civil?"
- **Respuesta generada:** correctamente basada en el Artículo 1 (ficticio) recuperado, sin mezclar información de los otros artículos indexados.
- **Fragmento citado:** devuelto textual, con fuente (`Artículo 1 (ficticio, prueba)`) y score de similitud (0.93).
- **Disclaimer:** presente en la respuesta, tal como exige [requerimientos_usuario.md §3.2](requerimientos_usuario.md).

Esto confirma que el diseño de la Sección 6 de [arquitectura.md](arquitectura.md) (recuperación + generación + fragmento verificable) funciona correctamente end-to-end.

## 3. Problema encontrado y resuelto durante el spike

El contenedor del backend corre como usuario no-root (`appuser`, principio de menor privilegio — [security_checklist.md §1.2](security_checklist.md)), pero el `Dockerfile` inicial no le creaba un directorio "home", lo que hacía fallar la descarga del modelo de embeddings de HuggingFace (necesita un directorio de caché con permisos de escritura). Se corrigió creando explícitamente el home de `appuser` y fijando `HF_HOME` a una ruta dentro de ese home. Ver `backend/Dockerfile`.

## 4. Segunda ronda: frontend + filtro por área del derecho (2026-09-23)

Se agregó el frontend (React + Vite + TypeScript) servido por Caddy, que ahora es el único punto de entrada público del stack (el backend dejó de publicar su puerto al host, conforme a [security_checklist.md §1.3](security_checklist.md)). Se etiquetó el corpus de prueba con un campo `Área:` y se implementó el filtro correspondiente en Qdrant (`backend/app/rag.py`).

**Prueba realizada:** la pregunta "¿Cuánto dura la detención antes de resolver la situación jurídica?" (temática penal) se probó dos veces:

- **Sin filtro:** el sistema recuperó correctamente el artículo de materia Penal como más relevante (score 0.90).
- **Con filtro "Laboral":** el sistema excluyó correctamente el artículo Penal (aunque era el más similar) y, al no tener contexto relevante en el área filtrada, **respondió honestamente que no tenía la información** en vez de inventarla — el comportamiento anti-alucinación deseado.

Se verificó también visualmente en navegador (`http://localhost:8080`) que la interfaz muestra correctamente los tres paneles (respuesta, fragmentos citados con fuente/área/score, disclaimer).

## 5. Tercera ronda: UI avanzada, documentos y voz (2026-09-23)

Se agregaron y validaron en el contenedor real (no solo en un venv de prueba):

- **Tema/tamaño de texto/responsive:** confirmado por interacción real de clic (cambio a tema claro + tamaño grande, persistido en `localStorage`) y por redimensionado a viewport móvil (375px), donde el CSS responsive aplicó correctamente (padding reducido, botón a ancho completo).
- **Subida de documentos ad-hoc:** se subió un contrato de prueba vía `POST /api/documents/upload`, y una consulta posterior con `incluir_documentos: true` recuperó el fragmento del documento subido como el más relevante (score 0.90) y el LLM lo citó correctamente como "Cláusula Octava del contrato subido".
- **Generación de documentos:** `GET /api/documents/templates` y `POST /api/documents/generate/plantilla_prueba` devolvieron un `.docx` válido (verificado con `file`).
- **Voz:** antes de integrar Piper, se instaló el paquete real en un entorno aislado para verificar los flags exactos de su CLI y confirmar que la voz `es_MX-claude-high` existe de verdad (no se asumió) — ver la nota de buena práctica en [manual_ingenieria_software.md §6.4](manual_ingenieria_software.md). Ya dentro del contenedor real: `POST /api/voice/hablar` generó un WAV válido, y ese mismo WAV transcrito con `POST /api/voice/transcribir` recuperó el texto original casi perfecto ("El plazo para contestar una demanda civil es de nueve didas hábiles" — un único error menor de una vocal).

**Limitación de esta validación:** no fue posible probar grabación real de micrófono ni reproducción de audio por altavoz a través del navegador automatizado de este entorno (sin hardware de audio real). Se validó el circuito completo por API directamente, y el código del frontend que invoca esas mismas APIs (`MediaRecorder`, `Audio.play()`) está escrito y renderiza sin errores de consola, pero su comportamiento con un micrófono/altavoz humano real queda pendiente de probar por el usuario.

## 5.1 Corrección: la sugerencia de generar documento aparecía siempre (2026-09-23)

Feedback del Product Owner tras probar la interfaz: la sugerencia "¿quieres generar un documento?" aparecía después de **cualquier** respuesta, cuando debía aparecer solo si el tema realmente lo ameritaba. Se agregó `sugerir_plantilla()` en `backend/app/generation.py` (coincidencia de palabras clave entre la pregunta/respuesta y cada plantilla) y el endpoint `/api/query` ahora devuelve `plantilla_sugerida: null` en el caso normal.

**Bug encontrado durante la propia validación de la corrección:** la primera versión usaba `"demanda"` e `"indemnización"` como palabras clave — demasiado genéricas, coincidían con casi cualquier pregunta legal (ej. "¿plazo para contestar una **demanda** civil?" activaba la sugerencia de una plantilla sobre pensión alimenticia, sin relación real). Se corrigió a frases específicas (`"pensión alimenticia"`, `"demanda alimenticia"`). Verificado con 3 preguntas de prueba: 2 sin relación no sugieren nada, 1 sobre pensión alimenticia sí sugiere.

## 5.2 Primer corpus real: Ley Federal del Trabajo (2026-09-24)

A petición del Product Owner, se ingirió el **primer corpus 100% real** del proyecto: el texto completo y vigente de la **Ley Federal del Trabajo**, descargado directamente del sitio oficial de la Cámara de Diputados (`https://www.diputados.gob.mx/LeyesBiblio/pdf/LFT.pdf`, texto vigente con última reforma DOF 14-05-2026). Implementado en `backend/app/ingest_lft.py`, que:

- Descarga el PDF oficial en cada ejecución (no se versiona el binario en el repo).
- Corta el contenido en la primera aparición de "TRANSITORIOS" para excluir el archivo histórico de decretos de reforma (no es texto sustantivo vigente).
- Parsea **1,264 artículos** reales por su numeración oficial (incluye variantes como "3o. Bis", "153-F Bis", "512-D Ter") — verificado manualmente contra el texto extraído antes de escribir el regex final, sin duplicados.
- Indexa cada artículo con su número real como fuente (ej. "Artículo 87, Ley Federal del Trabajo...") en la misma colección de Qdrant que el corpus ficticio de prueba (coexisten sin conflicto porque el corpus ficticio sigue etiquetado explícitamente "(ficticio, prueba)").

### Resultados de fidelidad (lo que se pidió verificar)

- **Prueba 1 — aguinaldo:** "¿Cuántos días de aguinaldo debe pagar el patrón?" → el sistema citó correctamente el **Artículo 87** real ("quince días de salario, por lo menos"), dato verificable y correcto. El artículo ficticio de prueba también apareció pero con menor relevancia, sin causar confusión (queda claramente etiquetado).
- **Prueba 2 — vacaciones (hallazgo importante):** "¿Cuántos días de vacaciones con un año de servicio?" → la recuperación encontró correctamente el **Artículo 76** real (el que sí establece "doce días laborables" tras la reforma vacacional), con score más alto entre los 3 fragmentos relevantes. **Pero el texto generado por el LLM le atribuyó el dato al Artículo 77** (que en realidad regula un supuesto distinto: trabajadores discontinuos/de temporada). El número (12 días) es correcto y proviene de una fuente real recuperada, pero la cita del artículo en la prosa es incorrecta.

**Conclusión de esta prueba:** la recuperación (retrieval) es fiel — encuentra el artículo real correcto. El punto débil detectado es que el LLM, al sintetizar entre varios fragmentos con scores muy cercanos (0.909, 0.905, 0.900, los tres sobre vacaciones), puede atribuir mal el número de artículo en su resumen. Esto **valida el diseño híbrido**: un abogado que solo leyera la respuesta generada se llevaría el dato equivocado del artículo, pero el fragmento textual mostrado junto a la respuesta (Art. 76, con el texto real) permite detectar y corregir el error — exactamente para eso existe esa sección, no es un adorno. Ver el requerimiento original en [requerimientos_usuario.md §3.1](requerimientos_usuario.md).

**Pendiente derivado de este hallazgo:** evaluar si instruir al modelo de forma más estricta (ej. "cita el número de artículo tal como aparece en la etiqueta [Fuente: ...], nunca lo infieras") reduce este tipo de error de atribución — no se intentó corregir en esta sesión, queda como mejora de prompt a probar.

## 5.3 Mecanismo anti-alucinación por desajuste de materia (2026-09-24)

**Reporte del Product Owner:** al preguntar sobre el Código Procesal Civil de Guerrero (no indexado — el corpus solo tenía la Ley Federal del Trabajo en ese momento), el sistema forzó una respuesta usando fragmentos laborales no relacionados, en vez de admitir que no tenía la información.

### Hallazgo antes de implementar la solución pedida

Se pidió un `score_threshold` de 0.75 sobre la similitud coseno del retriever. Antes de aplicarlo a ciegas, se midieron los scores reales de tres escenarios contra el corpus (solo LFT + 4 artículos ficticios):

| Pregunta | Relación real con el corpus | Score obtenido |
|---|---|---|
| Código Procesal Civil de Guerrero | Ninguna (no indexado) | 0.85 – 0.864 |
| "¿Mejor receta para hacer pozole?" | Ninguna (ni siquiera es una pregunta legal) | 0.795 – 0.802 |
| Preguntas genuinamente relevantes (aguinaldo, vacaciones) | Total | 0.85 – 0.90 |

**Conclusión:** con el modelo de embeddings actual (`multilingual-e5-small`) sobre texto legal en español formal, los rangos de similitud de contenido relevante e irrelevante **se superponen** — no existe un umbral fijo que los separe de forma confiable. Un `score_threshold` de 0.75 no habría filtrado ninguno de los dos casos irrelevantes de la tabla. **Actualización 2026-09-25:** este umbral se retiró del código al migrar a búsqueda híbrida (BM25 + vectorial) — ver [docs/refactorizacion_rag.md](refactorizacion_rag.md). El score fusionado ya no es comparable contra un umbral de coseno crudo. El hallazgo de esta sección sigue siendo la razón documentada por la que no se reintrodujo un umbral fijo equivalente.

### Qué se implementó

1. **`score_threshold=0.75`** en la consulta a Qdrant (`backend/app/rag.py`, función `retrieve`) — se implementó tal como se pidió, como una capa de defensa adicional (evita el caso extremo de que ni un solo fragmento supere ni ese piso), aunque la medición de arriba muestra que su efecto real es limitado con este modelo de embeddings.
2. **Metadato `ley`** agregado a cada fragmento indexado (`backend/app/ingest.py`, `backend/app/ingest_lft.py`, `backend/app/documents.py`) — permite en el futuro filtrar o mostrar explícitamente de qué ley proviene cada fragmento, no solo inferirlo del texto de "fuente".
3. **System prompt reescrito** (`backend/app/rag.py`, `SYSTEM_PROMPT`) para exigir explícitamente: responder solo con el contexto, evaluar si el contexto corresponde a la materia preguntada, y responder EXACTAMENTE con la frase «No cuento con la legislación necesaria en mi base de datos para responder a esta consulta.» si no corresponde o si no hay contexto. Esta es la defensa que realmente resuelve el reporte del Product Owner, no el umbral.

### Validación

- **Código Procesal Civil de Guerrero** (el caso reportado): el sistema ahora responde exactamente la frase de rechazo esperada. ✅
- **Pozole** (control, no legal): el sistema **rechazó responder**, pero con su propia redacción ("No puedo proporcionar una respuesta a esta pregunta.") en vez de la frase EXACTA pedida. El modelo `llama3.2:3b` (3B parámetros) no sigue la instrucción de frase literal el 100% de las veces, aunque sí cumple la propiedad de seguridad real (no alucina, no usa contexto ajeno). **No se debe asumir que la frase de salida es siempre parseable de forma exacta** — si en el futuro se necesita detectar programáticamente un rechazo (ej. para métricas), conviene una verificación más flexible (contiene "no cuento" O "no puedo" + ausencia de contenido legal citado) en vez de comparar el string exacto.
- **Pregunta real de control** (aguinaldo): el sistema respondió correctamente, citando el Artículo 87 real — confirma que el ajuste no volvió al sistema demasiado conservador.

## 6. Pendiente (no cubierto por este spike local)

- [ ] **Validación en ARM64 real** sobre una VM Oracle Cloud Always Free — este spike corrió en x86_64, no confirma compatibilidad de imágenes ni desempeño real en Ampere A1.
- [ ] **Prueba de concurrencia**: no se probó con múltiples usuarios simultáneos.
- [ ] **Calidad del modelo con corpus real**: la prueba usó datos ficticios; falta validar calidad de respuesta con legislación real de Guerrero una vez definido el sourcing ([requerimientos_usuario.md §4](requerimientos_usuario.md)).
- [ ] **Latencia**: no se midió tiempo de respuesta de forma sistemática; a medir en el entorno cloud real, que tendrá menos cómputo que esta máquina de desarrollo.
- [ ] **Micrófono/altavoz con hardware real**: la grabación de voz y la reproducción de audio no se probaron con un dispositivo real (ver Sección 5).
- [ ] **RAM real del backend con Whisper+Piper+embeddings cargados a la vez**, bajo carga, en la VM ARM64 — el límite de 3 GB en `docker-compose.yml` es una estimación, no una medición (ver [security_checklist.md §4.3](security_checklist.md)).
- [ ] **Cumplimiento exacto de la frase de rechazo**: `llama3.2:3b` no siempre usa la frase literal pedida al rechazar una pregunta fuera de tema (sí rechaza, pero con su propia redacción) — ver Sección 5.3. Evaluar si un modelo más grande sigue mejor la instrucción, o si conviene verificar el rechazo por contenido en vez de por string exacto.
