# Requerimientos de Usuario — RAG Legal Guerrero (MVP)

**Estado:** Borrador — resultado de sesión de entrevista con el stakeholder/product owner. Sujeto a validación conforme avance el sourcing del corpus y pruebas de infraestructura cloud gratuita.
**Última actualización:** 2026-09-23
**Método:** Docs-as-Code — este documento vive en el repo y debe actualizarse vía PR conforme cambien los requerimientos.
**Documentos relacionados:** [aviso_privacidad.md](aviso_privacidad.md), [security_checklist.md](security_checklist.md)

---

## 1. Visión del producto

Sistema RAG (Retrieval-Augmented Generation) que funciona como **memoria de consulta rápida para un abogado generalista** que ejerce en Guerrero, México. La analogía de diseño es la de un abogado en medio de una consulta o un trámite que necesita verificar un plazo, un artículo o un requisito procesal que no recuerda con exactitud o que puede estar desactualizado — el sistema debe responder ese tipo de consulta con precisión y trazabilidad hacia la fuente normativa.

**No es** un sustituto del criterio profesional del abogado ni genera asesoría vinculante (ver limitación de responsabilidad en [aviso_privacidad.md, Sección 2](aviso_privacidad.md)).

---

## 2. Alcance jurídico del MVP

El corpus debe cubrir de forma amplia, **no limitada a una sola rama del derecho**, dado que el usuario objetivo es un abogado generalista que puede recibir consultas de cualquier área:

- Derecho Penal (estatal y Código Nacional de Procedimientos Penales)
- Derecho Civil y Familiar (Código Civil y de Procedimientos Civiles del Estado de Guerrero)
- Derecho Laboral (Ley Federal del Trabajo)
- Derecho Administrativo y Fiscal estatal
- Amparo (Ley de Amparo, federal)
- Otras leyes y reglamentos estatales de Guerrero aplicables, conforme se identifiquen

No se prioriza una sola rama sobre otra para el MVP; el criterio de éxito es cobertura amplia con calidad de respuesta consistente, no profundidad en un solo nicho.

---

## 3. Comportamiento funcional esperado

### 3.1 Formato de respuesta: híbrido

Cada respuesta del sistema debe combinar:

1. **Respuesta conversacional breve** en lenguaje natural que resuma o interprete la consulta.
2. **Fragmentos textuales exactos** de la fuente (artículo, ley, código) que respaldan la respuesta, **citando explícitamente de dónde proviene** (ej. "Art. 123, Código Civil del Estado de Guerrero") para que el abogado pueda verificarlo por su cuenta.

Prioridad de diseño: **minimizar alucinación**. El fragmento textual con su fuente es el elemento no negociable de cada respuesta — la parte conversacional es un complemento, no un reemplazo del texto original.

### 3.2 Disclaimer obligatorio

Toda respuesta generada por el sistema debe incluir un aviso visible indicando que se trata de contenido generado por IA, que puede contener errores, y que debe ser verificado antes de su uso profesional. Este requerimiento es consistente con la limitación de responsabilidad ya redactada en [aviso_privacidad.md, Sección 2](aviso_privacidad.md) y debe implementarse a nivel de UI (no solo como texto legal en un documento aparte).

### 3.3 Generación de documentos/escritos

Actualización 2026-09-23: se implementó el **mecanismo** de generación de documentos (registro de plantillas + formulario dinámico + exportación a `.docx`), pero **sin ningún caso legal real todavía** — solo una plantilla de prueba ficticia para validar el mecanismo end-to-end (ver [manual_ingenieria_software.md §6.3](manual_ingenieria_software.md)). Completar un caso real (ej. demanda alimenticia) requiere redacción y revisión por un abogado antes de agregarse como plantilla.

### 3.4 Funciones adicionales de la interfaz (2026-09-23)

A petición del Product Owner, se ampliaron los requerimientos de interfaz:

- **Responsive y personalizable**: la interfaz debe adaptarse a distintos tamaños de pantalla, y permitir al usuario ajustar tema (claro/oscuro) y tamaño de texto a su preferencia.
- **Subir documentos**: el abogado puede adjuntar un documento (PDF/DOCX/TXT) para preguntar sobre él en esa sesión — de forma **temporal y aislada por sesión**, sin indexarse en el corpus legal permanente ni ser visible para otros usuarios.
- **Copiar/pegar**: botones para copiar la respuesta y cada fragmento citado al portapapeles.
- **Chat por voz**: dictado de la pregunta por micrófono y reproducción hablada de la respuesta, usando modelos **autoalojados y open source** (no un servicio de voz de un tercero), para no romper el compromiso de privacidad de [aviso_privacidad.md](aviso_privacidad.md).

---

## 4. Corpus documental (fuentes de datos)

**Estado actual: pendiente de definir.** No se cuenta todavía con las fuentes digitalizadas. Requerimientos para cuando se defina el sourcing:

- Las fuentes deben tener **respaldo oficial y verificable**, por ejemplo:
  - Periódico Oficial del Estado de Guerrero (legislación estatal)
  - Diario Oficial de la Federación / Cámara de Diputados (leyes federales)
  - Semanario Judicial de la Federación / SCJN (jurisprudencia — a evaluar si entra en el MVP o en una fase posterior)
- La arquitectura de ingesta debe **anticipar actualizaciones** (reformas legislativas, nuevas tesis), de modo que no se requiera reconstruir el sistema completo cada vez que cambie una ley. Esto implica pensar desde ahora en un pipeline de ingesta versionado/reproducible, no en una carga manual única.
- Pendiente de definir en una fase posterior: mecanismo concreto de actualización (manual vs. semi-automatizado), y si se incluye jurisprudencia en el MVP o se deja para después.

---

## 5. Infraestructura y restricciones técnicas

- **Despliegue en la nube**, no local en el equipo del usuario — debe ser consultable desde cualquier dispositivo vía navegador.
- **Costo objetivo: $0** para este prototipo. Implica evaluar y diseñar sobre tiers gratuitos de proveedores cloud (ej. Hugging Face Spaces, Oracle Cloud Free Tier, Fly.io, Render free tier — a evaluar cuál se ajusta mejor a los requisitos de cómputo).
- **Stack 100% open source**, sin dependencia de APIs de pago (regla del proyecto): modelos de HuggingFace / Ollama, VectorDB libre, contenerizado con Docker Compose (ver [security_checklist.md](security_checklist.md) para el hardening de contenedores ya definido).
- **Riesgo identificado:** los tiers gratuitos de cómputo en la nube suelen ser equivalentes o más limitados que un escenario CPU-only local (RAM/CPU restringidos, sin GPU, posibles límites de tiempo de ejecución o "sleep" por inactividad). Esto condiciona el tamaño de modelo LLM y de embeddings viable (modelos pequeños, ej. rango 1B–3B–7B parámetros a evaluar según el proveedor elegido). Se deberá validar empíricamente antes de comprometer una arquitectura final.

---

## 6. Usuarios e interfaz

- **Multiusuario / multi-abogado concurrente**: el sistema debe soportar varios abogados consultando al mismo tiempo, lo cual implica:
  - Autenticación/login básico (no fue solicitado como anónimo).
  - Consideraciones de aislamiento de sesión y concurrencia en el backend (relevante para el dimensionamiento de la infraestructura gratuita del punto 5).
- **Interfaz estructurada**, no un chat simple tipo WhatsApp/ChatGPT. Implica (a definir en detalle en diseño de UI/UX):
  - Posibles filtros por área del derecho, tipo de fuente (ley, jurisprudencia), o similar.
  - Presentación diferenciada entre la respuesta conversacional y los fragmentos/citas de respaldo (ver Sección 3.1).

---

## 7. Riesgos y preguntas abiertas

| # | Tema | Riesgo / pregunta abierta |
|---|------|---------------------------|
| 1 | Corpus | No se ha definido el sourcing concreto ni si incluye jurisprudencia en el MVP. |
| 2 | Infraestructura gratuita | Los límites de cómputo de tiers gratuitos pueden no ser suficientes para un modelo de calidad aceptable con múltiples usuarios concurrentes — requiere validación técnica temprana (spike). |
| 3 | Autenticación | No se definió el mecanismo de auth (usuarios/roles, si hay distinción entre abogados de un mismo despacho, etc.) — pendiente de detallar en diseño técnico. |
| 4 | Actualización del corpus | No se definió el proceso ni la periodicidad para incorporar reformas legislativas. |
| 5 | Aviso de privacidad | [aviso_privacidad.md](aviso_privacidad.md) tiene campos pendientes (`[NOMBRE DEL RESPONSABLE]`, `[DOMICILIO]`, etc.) que deben completarse antes de cualquier despliegue accesible a terceros. |

---

## 8. Resumen de decisiones (para referencia rápida)

- **Alcance:** todas las ramas del derecho aplicables en Guerrero (estatal + federal relevante), sin priorización única.
- **Formato de respuesta:** híbrido (conversacional + fragmento textual citado), con disclaimer de IA obligatorio en cada respuesta.
- **Generación de documentos:** fuera del MVP, contemplada como evolución futura.
- **Corpus:** pendiente de sourcing; debe tener respaldo oficial y soportar actualizaciones futuras.
- **Infraestructura:** cloud (no local), open source, costo $0, contenerizado con Docker.
- **Usuarios:** multiusuario concurrente, con autenticación.
- **Interfaz:** estructurada, no chat simple.
