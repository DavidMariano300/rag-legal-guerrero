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

## 6. Pendiente (no cubierto por este spike local)

- [ ] **Validación en ARM64 real** sobre una VM Oracle Cloud Always Free — este spike corrió en x86_64, no confirma compatibilidad de imágenes ni desempeño real en Ampere A1.
- [ ] **Prueba de concurrencia**: no se probó con múltiples usuarios simultáneos.
- [ ] **Calidad del modelo con corpus real**: la prueba usó datos ficticios; falta validar calidad de respuesta con legislación real de Guerrero una vez definido el sourcing ([requerimientos_usuario.md §4](requerimientos_usuario.md)).
- [ ] **Latencia**: no se midió tiempo de respuesta de forma sistemática; a medir en el entorno cloud real, que tendrá menos cómputo que esta máquina de desarrollo.
- [ ] **Micrófono/altavoz con hardware real**: la grabación de voz y la reproducción de audio no se probaron con un dispositivo real (ver Sección 5).
- [ ] **RAM real del backend con Whisper+Piper+embeddings cargados a la vez**, bajo carga, en la VM ARM64 — el límite de 3 GB en `docker-compose.yml` es una estimación, no una medición (ver [security_checklist.md §4.3](security_checklist.md)).
