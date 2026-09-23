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

## Estado actual

Proyecto en fase de diseño — ver la sección de riesgos y preguntas abiertas en [docs/arquitectura.md](docs/arquitectura.md#6-spike-técnico-pendiente-antes-de-comprometer-esta-arquitectura) para los próximos pasos (spike técnico de infraestructura).

## Licencia

Este proyecto se distribuye bajo la licencia [Apache 2.0](LICENSE).
