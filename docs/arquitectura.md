# Arquitectura Técnica — RAG Legal Guerrero (MVP)

**Estado:** Propuesta del Arquitecto — pendiente de validación empírica (spike técnico, Sección 6) antes de comprometerse como definitiva.
**Última actualización:** 2026-09-23
**Deriva de:** [requerimientos_usuario.md](requerimientos_usuario.md)
**Documentos relacionados:** [security_checklist.md](security_checklist.md), [aviso_privacidad.md](aviso_privacidad.md)

---

## 1. Restricciones que gobiernan el diseño

Toda decisión de esta arquitectura está subordinada a estas restricciones, en orden de rigidez:

1. **Costo $0** — el prototipo no puede depender de un tier de pago ni de créditos promocionales que expiren.
2. **100% open source / self-hosted** — ningún modelo ni servicio propietario de pago (OpenAI, Anthropic API, Pinecone gestionado, etc.).
3. **Accesible desde la nube, multiusuario concurrente**, vía navegador.
4. **Contenerizado (Docker/Docker Compose)**, siguiendo el hardening ya definido en [security_checklist.md](security_checklist.md).

Estas cuatro restricciones combinadas son las que más limitan las opciones — no existe "cómputo gratuito ilimitado", así que la arquitectura debe ser explícita sobre qué se sacrifica (tamaño de modelo, latencia, concurrencia máxima).

---

## 2. Decisión de cómputo: Oracle Cloud Always Free (Ampere A1)

### 2.1 Opciones evaluadas

| Proveedor (free tier) | Recursos reales | Persistencia | Veredicto |
|---|---|---|---|
| **Oracle Cloud Always Free — Ampere A1** | Hasta 4 OCPU (ARM) + 24 GB RAM, repartibles en varias VMs | Permanente, sin expirar, sin tarjeta cobrada | **Elegido** |
| Hugging Face Spaces (free) | 2 vCPU / 16 GB RAM | Se duerme tras inactividad; orientado a un solo contenedor (Gradio/Docker SDK), no a docker-compose multi-servicio | Descartado como host principal; posible uso auxiliar (demo) |
| Google Cloud Free Tier (e2-micro) | 1 vCPU compartida / 1 GB RAM | Permanente | Insuficiente RAM para LLM + vector DB |
| AWS Free Tier (t2/t3.micro) | 1 vCPU / 1 GB RAM, y solo 12 meses | Expira | Insuficiente y no permanente |
| Fly.io / Render / Railway (free) | Variable, recortado agresivamente en 2024-2025 | Sueño por inactividad, requiere tarjeta en algunos casos | Descartado |

**Oracle Cloud Always Free** es la única opción con recursos suficientes (24 GB RAM es clave para correr un LLM cuantizado + una vector DB + el backend simultáneamente) que además es gratuita **de forma permanente**, no un trial. El costo de esta elección es doble:

- **Arquitectura ARM64**, no x86 — todas las imágenes Docker deben tener build o imagen disponible para `arm64`. Ollama, la mayoría de vector DBs open source y las imágenes base de Python lo soportan sin problema; hay que verificarlo imagen por imagen.
- **Disponibilidad de capacidad regional**: Oracle limita la creación de instancias Ampere A1 free por región y a veces hay que reintentar el aprovisionamiento (riesgo operativo, no técnico — documentado en Sección 6).

### 2.2 Sizing dentro del free tier

Con 4 OCPU / 24 GB RAM se propone repartir así (ajustable):

- **Ollama + LLM**: ~2 OCPU / 12–14 GB RAM
- **Vector DB**: ~1 OCPU / 4 GB RAM
- **Backend API** (embeddings + Whisper STT + Piper TTS + generación de documentos, todo en el mismo contenedor): ~1 OCPU / 3–4 GB RAM
- **Frontend/proxy (Caddy)**: overhead mínimo (~256 MB)
- Margen para el propio SO y overhead de Docker

Todo en **una sola VM Ampere A1** para el MVP (no varias VMs orquestadas) — simplifica networking y evita cruzar el límite gratuito de balanceadores/IPs.

**Actualización 2026-09-23:** al agregar voz (Whisper + Piper) y subida de documentos al mismo contenedor del backend, su necesidad de RAM subió de ~1 GB a ~3 GB en `docker-compose.yml` (validado localmente, pendiente medir en la VM ARM64 real — ver [spike_resultados.md](spike_resultados.md)). La suma de los límites configurados (Ollama 6 GB + Qdrant 2 GB + backend 3 GB + proxy 256 MB ≈ 11.3 GB) sigue dentro del presupuesto de 24 GB, pero el uso real bajo carga concurrente todavía no se ha medido — sigue siendo parte del spike pendiente de la Sección 6.

---

## 3. Stack de componentes

```
┌─────────────────────────────────────────────────────────┐
│                  VM Oracle Cloud (Ampere A1, ARM64)       │
│                                                             │
│  ┌────────────┐   ┌──────────────┐   ┌─────────────────┐ │
│  │  Frontend   │──▶│  Backend API  │──▶│  Ollama (LLM)   │ │
│  │ (estático)  │   │   (FastAPI)   │   │                 │ │
│  └────────────┘   └──────┬───────┘   └─────────────────┘ │
│                            │                                │
│                            ▼                                │
│                    ┌───────────────┐                        │
│                    │  Vector DB     │                        │
│                    │  (Qdrant)      │                        │
│                    └───────────────┘                        │
│                            │                                │
│                            ▼                                │
│                    ┌───────────────┐                        │
│                    │  Auth/Users DB │                        │
│                    │  (Postgres)    │                        │
│                    └───────────────┘                        │
│                                                             │
│         Reverse proxy (Caddy/Traefik) + TLS ─── único       │
│         puerto expuesto al exterior (443)                   │
└─────────────────────────────────────────────────────────┘
```

### 3.1 Componentes y justificación

| Componente | Elección | Por qué |
|---|---|---|
| **LLM runtime** | Ollama | Ya definido como regla del proyecto; soporta ARM64; gestiona cuantización (GGUF) fácilmente. |
| **Modelo LLM** | `llama3.2:3b` o `qwen2.5:3b` (cuantizado Q4) como punto de partida | Modelos pequeños con buen desempeño en español y viables en CPU ARM sin GPU. A validar empíricamente cuál rinde mejor en textos jurídicos en español (spike, Sección 6). |
| **Embeddings** | `intfloat/multilingual-e5-small` o `BAAI/bge-m3` (HuggingFace) | Modelos de embeddings multilingües con buen soporte de español, ligeros para CPU. |
| **Vector DB** | Qdrant | Open source, imagen oficial ARM64, buen soporte de filtros por metadata (útil para la interfaz estructurada por área del derecho — [requerimientos_usuario.md §6](requerimientos_usuario.md)), footprint razonable en RAM. |
| **Backend** | Python + FastAPI | Estándar para servir APIs RAG, fácil integración con LangChain/LlamaIndex si se decide usar un framework de orquestación, o implementación directa. |
| **Base de usuarios/auth** | PostgreSQL + JWT | Necesario por el requerimiento multiusuario concurrente con login ([requerimientos_usuario.md §6](requerimientos_usuario.md)). Postgres es liviano en modo single-instance para un MVP con pocos usuarios. |
| **Frontend** | React + Vite + TypeScript, compilado a estáticos | Decisión final (2026-09-23). La interfaz es **estructurada, no chat simple**: filtro por área del derecho, panel de respuesta separado del panel de fragmentos citados, disclaimer de IA siempre visible. Implementado y validado en `frontend/`. |
| **Reverse proxy / TLS** | Caddy (TLS automático) | Único punto expuesto al exterior — sirve los estáticos del frontend Y hace reverse proxy de `/api/*` al backend, coherente con el aislamiento de red ya definido en [security_checklist.md §1.3](security_checklist.md). El backend ya no publica puerto directo al host. |
| **STT (voz a texto)** | `faster-whisper` (modelo `small`, CPU, cuantizado int8) | Open source, autoalojado — el audio nunca sale de nuestra infraestructura (decisión 2026-09-23, ver [requerimientos_usuario.md §3.4](requerimientos_usuario.md)). Verificado end-to-end en local antes de integrarlo (ver [spike_resultados.md](spike_resultados.md)). |
| **TTS (texto a voz)** | Piper, voz `es_MX-claude-high` | Motor de síntesis open source, ligero en CPU, con voz en español mexicano ya verificada como real y descargable. Corre como subproceso dentro del contenedor del backend. |
| **Subida de documentos** | `pypdf` + `python-docx` para extracción, colección Qdrant separada (`session_documents`) filtrada por `session_id` | Consulta ad-hoc **temporal y aislada por sesión** (decisión 2026-09-23) — nunca se mezcla con el corpus legal permanente ni es visible entre usuarios. |
| **Generación de documentos** | Plantillas Jinja2 + `python-docx` para exportar `.docx` | Solo el mecanismo extensible por ahora (sin plantillas legales reales todavía) — agregar un caso nuevo no requiere tocar el resto del sistema. |

### 3.2 Orquestación de ingesta del corpus

Dado que el corpus está pendiente de sourcing ([requerimientos_usuario.md §4](requerimientos_usuario.md)), se propone un **pipeline de ingesta desacoplado** del servicio en vivo:

- Script/job de ingesta (no un contenedor persistente) que: descarga/recibe los documentos fuente → limpia y trocea (chunking) → genera embeddings → carga a Qdrant con metadata (ley, artículo, fecha de vigencia, fuente oficial).
- Este pipeline debe ser **re-ejecutable de forma idempotente** para soportar actualizaciones futuras (reformas) sin reconstruir todo el sistema, cumpliendo el requerimiento de extensibilidad.
- Sanitización de documentos antes de indexar, conforme a [security_checklist.md §2.2](security_checklist.md) (prevención de prompt injection indirecto vía documentos envenenados).

---

## 4. Flujo de una consulta (respuesta híbrida)

1. Usuario autenticado envía una pregunta desde el frontend.
2. Backend genera el embedding de la consulta y recupera los *k* fragmentos más relevantes de Qdrant (con su metadata de fuente).
3. Backend construye el prompt: system prompt con reglas anti-injection ([security_checklist.md §2.3](security_checklist.md)) + fragmentos recuperados delimitados explícitamente como "contexto no confiable" + la pregunta del usuario.
4. Ollama genera la respuesta conversacional breve.
5. El backend devuelve al frontend **dos bloques separados**: (a) la respuesta conversacional, (b) los fragmentos textuales exactos con su cita de fuente — nunca fusionados, para que el frontend pueda mostrarlos en paneles distintos (requerimiento de interfaz estructurada).
6. El frontend antepone/adjunta el disclaimer de IA obligatorio ([requerimientos_usuario.md §3.2](requerimientos_usuario.md)) a cada respuesta, de forma visible y no descartable.

---

## 5. Autenticación y multiusuario

- Login con usuario/contraseña (hash con `bcrypt`/`argon2`) + JWT de sesión — sin necesidad de un proveedor de identidad externo de pago.
- Un solo rol por ahora ("abogado"); no se definieron roles diferenciados (ej. admin de despacho) — queda como pregunta abierta para una siguiente iteración si se requiere administrar múltiples abogados de un mismo despacho con permisos distintos.
- Límite de concurrencia: dado el sizing de la Sección 2.2, se debe definir un límite razonable de consultas simultáneas al LLM (cola simple en el backend) para no saturar la VM — a calibrar en el spike técnico.

---

## 6. Spike técnico pendiente (antes de comprometer esta arquitectura)

Este documento es una propuesta razonada, no una arquitectura validada. Antes de construir sobre ella, se recomienda un spike de 1-2 días que confirme:

1. **Aprovisionamiento real** de una VM Ampere A1 Always Free en una región con capacidad disponible.
2. **Compatibilidad ARM64** de las imágenes elegidas (Ollama, Qdrant, Postgres, Caddy) — build o pull directo sin necesidad de compilar desde cero.
3. **Desempeño real** del modelo LLM elegido (latencia por respuesta, calidad en español jurídico) corriendo en CPU ARM sin GPU, bajo el sizing de RAM propuesto.
4. **Concurrencia mínima viable**: cuántos usuarios simultáneos soporta la VM antes de degradación inaceptable, para calibrar el límite de cola del punto 5.

Si el spike revela que Oracle Cloud Always Free es insuficiente o inaccesible (por disponibilidad regional), la alternativa de respaldo a evaluar sería un modelo aún más pequeño (ej. 1B–1.5B parámetros) o replantear qué tan "en vivo" necesita ser el LLM (ej. respuestas más basadas en recuperación pura con menos generación).

---

## 7. Mapeo con la seguridad ya definida

Esta arquitectura debe cumplir el hardening ya documentado en [security_checklist.md](security_checklist.md), en particular:

- Redes Docker internas para Qdrant/Postgres/Ollama — solo el reverse proxy expuesto (§1.3).
- Contenedores no-root, `read-only` filesystem donde aplique, límites de recursos por contenedor (§1.2) — relevante aquí porque el sizing de la Sección 2.2 depende de que estos límites estén bien configurados para no competir por RAM en la VM compartida.
- Gestión de secretos (JWT signing key, credenciales de Postgres) vía `.env` no versionado (§1.4).
- Reglas anti-prompt-injection en el system prompt y tratamiento del contexto recuperado como no confiable (§2).

---

## 8. Resumen de decisiones

- **Cómputo:** VM única Oracle Cloud Always Free (Ampere A1, ARM64, 4 OCPU/24GB RAM) — gratuita de forma permanente.
- **LLM:** Ollama con modelo pequeño cuantizado (3B, a validar en spike).
- **Embeddings:** modelo multilingüe HuggingFace liviano (ej. multilingual-e5-small).
- **Vector DB:** Qdrant.
- **Backend:** FastAPI + PostgreSQL (auth) + JWT.
- **Frontend:** React + Vite + TypeScript, servido por Caddy en la misma VM (mismo dominio que la API, sin CORS) — interfaz estructurada con filtro por área del derecho, tema claro/oscuro, tamaño de texto ajustable y diseño responsive. Implementado y validado localmente.
- **Voz:** Whisper (`faster-whisper`) y Piper autoalojados, sin enviar audio a terceros. Implementado y validado localmente.
- **Documentos:** subida ad-hoc temporal (aislada por sesión, no permanente) + mecanismo extensible de generación de `.docx` (sin plantillas legales reales todavía). Implementado y validado localmente.
- **Pendiente antes de construir en producción:** spike técnico de 4 puntos (Sección 6) — ahora con mayor urgencia dado que el backend creció considerablemente en dependencias y uso de RAM.
