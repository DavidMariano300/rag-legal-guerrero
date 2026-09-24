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

## 5. Pendiente (no cubierto por este spike local)

- [ ] **Validación en ARM64 real** sobre una VM Oracle Cloud Always Free — este spike corrió en x86_64, no confirma compatibilidad de imágenes ni desempeño real en Ampere A1.
- [ ] **Prueba de concurrencia**: no se probó con múltiples usuarios simultáneos.
- [ ] **Calidad del modelo con corpus real**: la prueba usó datos ficticios; falta validar calidad de respuesta con legislación real de Guerrero una vez definido el sourcing ([requerimientos_usuario.md §4](requerimientos_usuario.md)).
- [ ] **Latencia**: no se midió tiempo de respuesta de forma sistemática; a medir en el entorno cloud real, que tendrá menos cómputo que esta máquina de desarrollo.
