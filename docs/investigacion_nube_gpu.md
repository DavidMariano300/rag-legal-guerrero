# Investigación: nube con GPU gratuita para RAG Legal Guerrero

**Fecha:** 2026-10-26 · **Relacionado:** [investigacion_llm.md](investigacion_llm.md) §8, [arquitectura.md](arquitectura.md) §2.

## Por qué se busca GPU

Con qwen3.5:4b en CPU el producto llega a 75 % de respuestas correctas en el conjunto de validación (meta:
> 80 %). La falla que queda es de razonamiento sobre requisitos ("tengo 25 años, ¿puedo adoptar?"), y el
modo "pensamiento" de Qwen3.5 la corrige, pero genera ~3,000 tokens antes de responder: 14–43 s en una GPU
de consumo, varios minutos en los 2 núcleos ARM de la nube gratuita de Oracle. Además, en CPU cada
respuesta tarda ~1–2 min aun sin pensamiento.

## Lo que hay (verificado el 2026-10-26)

**No existe GPU gratuita, permanente y permitida para servir un producto.** Lo disponible son créditos
recurrentes, créditos de prueba o de programas, y notebooks gratuitos que prohíben usarse como servidor.

| Opción | Qué es gratis | ¿Sirve para el producto? | Notas |
|---|---|---|---|
| **[Modal](https://modal.com/pricing) (plan Starter)** | **$30 USD de cómputo cada mes**, recurrentes | **Sí** | GPU por segundo: T4 $0.000164/s (~$0.59/h), L4 $0.000222/s (~$0.80/h). Escala a cero: sin consultas no cobra. Endpoints web incluidos (limitados en Starter). Contenedor vivo 60 s tras la última consulta (configurable y cobrado). Elegir región cuesta 1.15–1.75×. |
| [Hugging Face ZeroGPU](https://huggingface.co/docs/hub/en/spaces-zerogpu) | 5 min de GPU al día (cuenta gratuita); 40 min con PRO ($9/mes) | Solo demo pequeña | Solo Spaces de Gradio, no Docker ni Ollama; cola compartida. 5 min/día ≈ 10–20 respuestas con pensamiento. |
| [Google Colab](https://research.google.com/colaboratory/faq.html) | GPU variable, sin cuota publicada | **No** | Sus términos prohíben servicios web y proxies remotos en el plan gratuito. |
| [Kaggle](https://www.kaggle.com/docs/efficient-gpu-usage) | ~30 h de GPU por semana, sesiones de 12 h | **No** | Pensado para notebooks; sesiones que se cortan. |
| [Lightning AI](https://lightning.ai/docs/overview/ai-studio/) | Horas de GPU iniciales/mensuales (las fuentes no coinciden: 22–80 h) | Pruebas, no producción | Estudios interactivos; no se verificaron sus términos para servir tráfico. |
| [NVIDIA Inception](https://www.nvidia.com/en-us/startups/) | Membresía gratuita; acceso a créditos de socios (AWS, Nebius) | Sí, si se califica | Requiere empresa constituida, sitio web y al menos un desarrollador. NVIDIA no publica montos. |
| [Microsoft for Startups](https://www.microsoft.com/en-us/startups) | $200 iniciales; luego $1,000 → $5,000 al verificar el negocio | Sí, si se califica | Excluye a instituciones educativas como solicitantes (no a una startup fundada por un estudiante). |
| [AWS Activate](https://aws.amazon.com/activate/) Founders | $1,000 (hasta $5,000) | Sí, si se califica | Requiere empresa; los créditos vencen en 1–2 años. |
| [Google for Startups](https://cloud.google.com/startup) (Start) | $2,000 por un año | Sí, si se califica | Para startups de menos de 24 meses sin financiamiento. |
| Créditos de investigación ([Google](https://edu.google.com/programs/credits/research/), [AWS](https://pages.awscloud.com/aws-cloud-credit-for-research.html)) | Google: hasta $5,000 (docentes), $1,000 (doctorado). AWS: hasta $5,000 (estudiantes) | Sí, como proyecto de investigación | Requieren propuesta; no se confirmó que México esté en la lista de países de Google. |
| [Azure for Students](https://azure.microsoft.com/free/students) | $100 al año, con correo institucional | Dudoso | Las suscripciones de estudiante suelen no tener cuota de GPU. |
| APIs gratuitas de modelos abiertos (Groq, OpenRouter, etc.) | Llamadas gratis con límites | **No** | Rompen la regla del proyecto (autohospedado, sin terceros) y las consultas, que pueden traer datos de clientes, saldrían a un tercero sin control. |

No se encontró un programa de créditos de nube específico para México. Conviene preguntar a la oficina
de investigación o de TI de la UAGRO si tiene convenios institucionales de nube o acceso a cómputo de
alto desempeño.

## Estimación de costo en Modal para este producto

Arquitectura híbrida: la app (frontend, backend, Qdrant, Postgres y embeddings de consulta en CPU) sigue
en la VM gratuita de Oracle, y **solo la generación del LLM** se llama en Modal sobre GPU.

- Una consulta con pensamiento en una L4: ~20–40 s de GPU, más 60 s de contenedor vivo si es una consulta
  aislada → ~$0.013–0.027. **Los $30 mensuales alcanzan para ~1,100–2,300 consultas aisladas**, y para
  más si llegan seguidas (comparten el tiempo vivo).
- Mantenerlo caliente durante una demo cuesta ~$0.80/h en L4: ~37 h de demo al mes con el crédito gratuito.
- **Arranque en frío:** tras escalar a cero, la primera consulta debe cargar el modelo (~20–60 s). Para una
  demo se puede precalentar unos minutos antes.
- **Privacidad:** las consultas pasarían por servidores de un tercero en EE. UU. (Modal como encargado
  del tratamiento). Hay que declararlo en el aviso de privacidad (transferencia a proveedor de
  infraestructura, [aviso_privacidad.md](aviso_privacidad.md) §7).

## Recomendación

1. **Corto plazo (demo con abogados): Oracle gratuito + LLM en Modal (L4, escala a cero).** Cabe en los
   $30 mensuales para el volumen de una demo, sin tarjeta para empezar. Antes de construirlo, confirmar
   con la validación local que el modo pensamiento supera el 80 %.
2. **Mediano plazo:** al formalizar el proyecto (empresa o proyecto de investigación UAGRO), tramitar
   NVIDIA Inception (puerta a créditos de AWS/Nebius), Microsoft for Startups y créditos de investigación.
   Con eso se puede pasar a una VM con GPU dedicada y sin arranques en frío.
3. Descartados para producción: Colab y Kaggle (términos o sesiones), APIs gratuitas de terceros
   (privacidad y regla del proyecto). ZeroGPU solo como demo pública muy limitada.

## Medición: GPU en Docker vs. 2 núcleos de CPU (2026-10-27)

Con el NVIDIA Container Toolkit instalado, Ollama corre en la RTX 5060 dentro de Docker
(`docker-compose.gpu.yml`, activado en esta laptop vía `COMPOSE_FILE` en `.env`). Validación (17 × 3):

| | CPU 16 hilos (v4) | RTX 5060 |
|---|---|---|
| Recuperación | 94 % | 94 % |
| Correctas (calificación manual) | 75 % (38/51) | 76 % (39/51) |
| Segundos por consulta | ~37–56 | **1–5** |

Mismo modelo y mismos parámetros: la calidad no cambia, la velocidad sí. Antes de la GPU se corrigieron dos
pérdidas de tiempo: cada llamada a Ollama con un `num_ctx` distinto recargaba el modelo (2 recargas por
consulta), y la primera consulta tras arrancar cargaba embeddings, BM25 e índices (ahora se precalienta).

**2 núcleos de CPU** (Ollama fijado a 2 núcleos físicos de la laptop, como la VM gratuita de Oracle): la
respuesta sola tarda 91 s (lectura del contexto a 46 tokens/s); con la reescritura, ~110 s por consulta, y
en los núcleos ARM de Oracle será más. Por eso la demo se sirve desde la laptop
([arquitectura.md](arquitectura.md) §2.4).

## Medición: ¿el modo pensamiento llega al 80 %? (2026-10-26, RTX 5060 local)

Validación (17 preguntas × 3), qwen3.5:4b, pensamiento solo en la respuesta final (`OLLAMA_THINK_RESPUESTA=true`,
6,000 tokens extra de presupuesto):

| | Sin pensamiento (v4) | Con pensamiento |
|---|---|---|
| Correctas | 75 % (38/51) | 69 % (35/51) |
| **Incorrectas** | 3 | **0** |
| Rechazos | 4 | 15 |
| Latencia mediana por respuesta (GPU) | ~10 s | **57 s** (máx. 117 s) |

- **Pensar elimina las respuestas incorrectas**: resolvió en 3 de 3 la de adopción, que sin pensamiento
  fallaba en 3 de 3.
- **Pero aumentan los rechazos**, por dos causas:
  1. Con pensamiento responde bien pero **sin comillas** (15 casos), y la verificación lo descarta. Se
     puede corregir con formato o con un segundo paso que agregue la cita; falta medirlo.
  2. Las citas del cálculo determinista etiquetadas con el artículo (Art. 76) se rechazaban por un error
     de la verificación. **Corregido** (afectaba también al modo sin pensamiento).
- **Costo en Modal revisado** con la latencia medida: ~60 s de GPU por respuesta, más 60 s de contenedor
  vivo si llega aislada → ~$0.013–0.027 por consulta en L4: **~1,100–2,300 consultas al mes con el
  crédito gratuito.** Para una demo alcanza; para uso diario de un despacho, no.

**Lectura para el producto:** para un abogado, una respuesta incorrecta con cita real es peor que un
rechazo. Con pensamiento el sistema pasa a ser "no se equivoca, pero a veces no contesta". Falta corregir
el formato de las citas con pensamiento para ver si así se cruza el 80 %.
