# RAG Legal Guerrero

Sistema RAG (Retrieval-Augmented Generation) 100% open source para asistir a abogados generalistas que ejercen en el Estado de Guerrero, México. Funciona como memoria de consulta rápida sobre legislación estatal y federal aplicable, devolviendo respuestas híbridas (resumen conversacional + fragmentos textuales exactos citando su fuente) para minimizar alucinaciones y facilitar la verificación por un profesional del derecho.

> **Este proyecto es un prototipo (MVP) en desarrollo activo.** No constituye asesoría legal. Ver [docs/aviso_privacidad.md](docs/aviso_privacidad.md) para la limitación de responsabilidad completa.

## Principios del proyecto

1. **100% open source y sin APIs de pago** — modelos de HuggingFace, Ollama, y una base de datos vectorial libre.
2. **Contenerizado** — todo el stack corre vía Docker Compose.
3. **Docs-as-Code** — la documentación vive en este repositorio y evoluciona junto con el código, vía pull requests.

## Documentación

| Documento | Contenido |
|---|---|
| [docs/requerimientos_usuario.md](docs/requerimientos_usuario.md) | Alcance del MVP, funcionalidad esperada, restricciones del producto. |
| [docs/arquitectura.md](docs/arquitectura.md) | Diseño técnico: stack, cómputo cloud gratuito, flujo de una consulta. |
| [docs/security_checklist.md](docs/security_checklist.md) | Checklist de hardening de contenedores y prevención de prompt injection. |
| [docs/aviso_privacidad.md](docs/aviso_privacidad.md) | Aviso de privacidad y límite de responsabilidad (borrador, pendiente de revisión legal). |
| [docs/manual_ingenieria_software.md](docs/manual_ingenieria_software.md) | Justificación de cada decisión técnica en lenguaje accesible, buenas prácticas, y anexos de defensa legal (NDA, tratamiento de datos). |
| [docs/manual_usuario.md](docs/manual_usuario.md) | Guía de uso de la herramienta para el Product Owner (abogado). |
| [docs/spike_resultados.md](docs/spike_resultados.md) | Resultados de la validación técnica local del stack completo. |

## Cómo correr el proyecto en local

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec ollama ollama pull llama3.2:3b
docker compose exec backend python -m app.ingest
```

La interfaz queda disponible en `http://localhost:8080`.

## Estado actual

Stack completo (frontend + backend + Ollama + Qdrant + Postgres) validado end-to-end en entorno local con datos de prueba ficticios. Pendiente: despliegue real en Oracle Cloud (ARM64), sourcing del corpus legal real, y autenticación multiusuario — ver [docs/spike_resultados.md](docs/spike_resultados.md) y la sección de roadmap en [docs/manual_ingenieria_software.md](docs/manual_ingenieria_software.md#10-roadmap-técnico-y-pendientes).

## Licencia

Este proyecto se distribuye bajo la licencia [Apache 2.0](LICENSE).
