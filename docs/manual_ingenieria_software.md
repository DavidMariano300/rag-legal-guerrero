# Manual de Ingeniería de Software — RAG Legal Guerrero

**Autor / Responsable técnico del proyecto:** Edgar David Mariano Ruiz
**Estado:** Borrador vivo — se actualiza conforme el proyecto avanza (Docs-as-Code).
**Última actualización:** 2026-09-23
**Audiencia de este manual:** cualquier persona que se sume al proyecto **sin experiencia previa en buenas prácticas de programación** — se explica no solo *qué* se hizo, sino *por qué*, en lenguaje técnico pero introduciendo cada concepto antes de usarlo.
**Documentos relacionados:** [requerimientos_usuario.md](requerimientos_usuario.md), [arquitectura.md](arquitectura.md), [security_checklist.md](security_checklist.md), [aviso_privacidad.md](aviso_privacidad.md)

---

## 1. Cómo leer este manual

Cada decisión técnica del proyecto se explica en tres partes:

- **Qué es** — la definición del concepto, en caso de que no lo conozcas.
- **Para qué sirve** — el problema concreto que resuelve.
- **Por qué se eligió así en este proyecto** — la razón específica, no genérica, de por qué esta opción y no otra.

La Sección 9 contiene los **anexos de defensa legal** (confidencialidad, tratamiento de datos) que debe firmar cualquier persona con acceso al código o a los datos del proyecto.

---

## 2. Glosario mínimo (léelo antes de seguir)

| Término | Qué es |
|---|---|
| **Contenedor (Docker)** | Una "caja" que empaqueta un programa junto con todo lo que necesita para funcionar (librerías, configuración), de modo que corre igual en cualquier computadora, sin importar qué tenga instalado esa computadora. |
| **Imagen Docker** | La plantilla de la que se crea un contenedor (como un molde). |
| **Docker Compose** | Una herramienta que levanta *varios* contenedores a la vez y los conecta entre sí, describiendo todo en un solo archivo (`docker-compose.yml`). |
| **API** | Un punto de entrada por el que un programa le pide algo a otro programa (por ejemplo, "dame la respuesta a esta pregunta legal") y recibe una respuesta, sin que el usuario tenga que saber cómo funciona por dentro. |
| **Backend** | El programa que hace el trabajo "de fondo" (recibe la pregunta, busca en la base de datos, le pide al modelo de IA que responda) — el usuario no lo ve directamente. |
| **Frontend** | La parte visual con la que interactúa el usuario (la página web, los botones, el cuadro de texto). |
| **LLM (Large Language Model)** | El modelo de inteligencia artificial que genera texto en lenguaje natural (la parte que "redacta" la respuesta). |
| **Embedding** | Una forma de convertir un texto en una lista de números que representa su significado, para poder comparar qué tan parecidos son dos textos matemáticamente. |
| **Base de datos vectorial (Vector DB)** | Una base de datos especializada en guardar y buscar esos "embeddings" — permite encontrar, de entre miles de artículos legales, los que son más parecidos en significado a la pregunta del usuario. |
| **RAG (Retrieval-Augmented Generation)** | La técnica que usa este proyecto: primero se *recupera* (retrieval) el texto legal relevante de la base vectorial, y luego se le pide al LLM que *genere* (generation) una respuesta basada solo en ese texto — en vez de dejar que el modelo "invente" desde su memoria general. |
| **Alucinación (en IA)** | Cuando un modelo de lenguaje genera información que suena convincente pero es falsa o no existe en ninguna fuente real. Es el riesgo principal que el diseño de este proyecto busca reducir. |

---

## 3. Por qué el proyecto está "contenerizado" (Docker)

**Qué es:** ya definido en la Sección 2.
**Para qué sirve:** sin Docker, cada persona que quisiera correr el proyecto tendría que instalar manualmente Python, la base de datos vectorial, el motor de IA, etc., y ajustar versiones — un proceso lento y propenso a errores ("en mi computadora sí funciona").
**Por qué se eligió así aquí:** el proyecto tiene **cuatro piezas independientes** (backend, base de datos vectorial, motor de IA, base de datos de usuarios) que deben funcionar coordinadas. Docker Compose permite levantar las cuatro con un solo comando (`docker compose up`), de forma idéntica en la laptop de desarrollo y en el servidor en la nube donde vivirá el sistema en producción. Esto también es lo que exige la regla #2 del proyecto (todo debe estar contenerizado).

---

## 4. Por qué modelos "locales" (Ollama) y no una API de pago (ej. OpenAI)

**Qué es:** Ollama es un programa open source que permite correr modelos de lenguaje de IA (LLMs) directamente en un servidor propio, sin enviar la información a una empresa externa.
**Para qué sirve:** genera las respuestas conversacionales del sistema.
**Por qué se eligió así:** dos razones concretas:

1. **Regla #1 del proyecto:** no depender de APIs de pago, para no tener un costo recurrente por cada consulta y no atarse a las políticas/precios de un tercero.
2. **Privacidad:** las consultas legales pueden contener datos sensibles de clientes ([aviso_privacidad.md §3.3](aviso_privacidad.md)). Si se usara una API externa de pago, cada consulta viajaría a los servidores de esa empresa. Con Ollama corriendo en nuestra propia infraestructura, los datos nunca salen del servidor que controlamos.

El costo de esta decisión: los modelos open source que pueden correr sin tarjeta gráfica (GPU) potente son más pequeños y, en general, algo menos capaces que los modelos de pago más grandes del mercado. Por eso el diseño (Sección 6) prioriza mostrar siempre el texto legal exacto además de la respuesta generada — así el usuario no depende ciegamente de la calidad del modelo.

---

## 5. Por qué Qdrant como base de datos vectorial

**Qué es:** ya definido en la Sección 2 (Vector DB).
**Para qué sirve:** es lo que permite que, cuando un abogado pregunta algo, el sistema encuentre los artículos de ley más relevantes entre todo el corpus indexado, en milisegundos.
**Por qué se eligió así:** es open source (regla #1), tiene imagen oficial de Docker lista para usarse, funciona bien con recursos limitados (relevante porque el servidor en la nube es gratuito y limitado — ver [arquitectura.md §2](arquitectura.md)), y permite guardar "metadata" junto a cada fragmento (de qué ley proviene, qué artículo es), lo cual es indispensable para poder **citar la fuente exacta** en cada respuesta, como exige [requerimientos_usuario.md §3.1](requerimientos_usuario.md).

---

## 6. Por qué la respuesta es "híbrida" (texto generado + fragmento citado)

Este es el patrón de diseño más importante del proyecto contra las alucinaciones de IA. El flujo técnico es:

1. La pregunta del usuario se convierte en un embedding.
2. Se buscan en Qdrant los fragmentos de ley más parecidos (esto es un hecho verificable, no una invención del modelo — es una búsqueda matemática de similitud).
3. Esos fragmentos, **con su fuente exacta**, se le entregan al LLM como "contexto" y se le indica explícitamente: "responde solo basándote en este contexto".
4. El sistema devuelve **ambas cosas por separado**: la interpretación del LLM (que puede tener errores) y el fragmento original tal cual está en la ley (que el abogado puede verificar él mismo).

Este diseño no elimina el riesgo de que el LLM interprete mal un fragmento, pero sí garantiza que el abogado siempre tenga acceso directo al texto original citado, sin depender únicamente de la interpretación de la IA — por eso además se exige el disclaimer visible en cada respuesta ([requerimientos_usuario.md §3.2](requerimientos_usuario.md)).

---

## 6.1 Por qué el frontend es React + Vite + TypeScript, y por qué vive en la misma VM

**Qué es:** React es una librería para construir interfaces web dividiéndolas en piezas reutilizables ("componentes"); Vite es la herramienta que convierte ese código en los archivos HTML/CSS/JS finales que un navegador puede mostrar; TypeScript es una variante de JavaScript que detecta errores de tipos antes de ejecutar el código (por ejemplo, evita que accidentalmente se trate un número como si fuera texto).

**Para qué sirve:** es la pantalla con la que el abogado interactúa — el formulario para preguntar, el filtro por área del derecho, y los paneles donde se muestran la respuesta, los fragmentos citados y el disclaimer.

**Por qué se eligió así:**
- React + Vite es la combinación más estándar y documentada para este tipo de interfaz, lo que facilita que cualquier futuro colaborador (aunque no haya trabajado en este proyecto) entienda el código rápido.
- TypeScript reduce errores silenciosos, algo valioso en una herramienta donde mostrar mal un dato (ej. confundir el fragmento citado con la respuesta generada) tiene implicaciones legales, no solo estéticas.
- Se decidió **no** alojar el frontend en un servicio externo (ej. GitHub Pages, Vercel) y en su lugar servirlo desde la misma VM de Oracle Cloud, a través de Caddy (el mismo "portero" que ya filtra el tráfico hacia el backend). Esto evita el problema técnico de CORS (cuando el navegador bloquea peticiones entre dos dominios distintos por seguridad) y evita depender de una segunda cuenta/servicio gratuito con sus propios límites y posibles cambios de política.
- El frontend se compila ("build") a archivos estáticos (HTML/CSS/JS ya listos) dentro de una imagen Docker de Caddy — no corre un servidor Node.js en producción, solo se sirven archivos, lo cual es más liviano y seguro (menos superficie de ataque).

Ver `frontend/Dockerfile` (build en dos etapas: una que compila con Node, otra que solo sirve los archivos ya compilados con Caddy) y `frontend/Caddyfile` (las reglas de enrutamiento: todo lo que empieza con `/api/` va al backend, el resto sirve la interfaz).

---

## 6.2 Por qué la subida de documentos es temporal y no se mezcla con el corpus legal

**Qué es:** el abogado puede subir un documento (PDF, Word o texto) para hacer preguntas sobre ESE documento específico (ej. "¿qué cláusula de este contrato habla de penalización por retraso?").

**Para qué sirve:** cubre un caso de uso distinto al de consultar la ley general — analizar un documento particular del caso que se está llevando.

**Por qué se eligió así (temporal, aislado por sesión):** existía la alternativa de que los documentos subidos se sumaran permanentemente al corpus legal compartido, pero eso abre un riesgo serio: cualquier usuario podría "contaminar" las respuestas que reciben TODOS los demás usuarios subiendo un documento incorrecto, desactualizado, o incluso malicioso. En vez de eso, cada documento se guarda en una base de datos vectorial separada (`session_documents`), etiquetado con un identificador de sesión que genera el navegador, y **solo se puede recuperar con ese mismo identificador** — es decir, el documento de un abogado nunca aparece en las respuestas de otro. Técnicamente esto se implementa igual que el filtro por área del derecho (Sección 6 más arriba), pero filtrando por sesión en vez de por área. Ver `backend/app/documents.py`.

**Medidas de seguridad aplicadas** (relevantes para la revisión de ciberseguridad): se valida la extensión del archivo contra una lista blanca (`.pdf`, `.docx`, `.txt`), se limita el tamaño máximo (15 MB) para evitar abusos, y el archivo original nunca se guarda en disco — solo el texto ya extraído y trozado. El texto extraído se trata exactamente igual que el resto del contexto recuperado: nunca como instrucciones (mismo principio de la Sección 7.6).

## 6.3 Por qué la generación de documentos es "solo el mecanismo" por ahora

**Qué es:** una funcionalidad para llenar una plantilla con datos y descargar un documento Word (`.docx`) ya redactado.

**Por qué se construyó solo el mecanismo, sin un documento legal real:** redactar el texto de un documento legal real (ej. una demanda alimenticia) es trabajo de un abogado, no de ingeniería — un error en ese texto tiene consecuencias legales directas. Lo que sí es trabajo de ingeniería es construir la "maquinaria" que, una vez que exista un texto ya revisado por un abogado, permita convertirlo en una plantilla usable sin tener que programar nada nuevo. Por eso `backend/app/generation.py` define un registro de plantillas (`TEMPLATES`) donde agregar un caso nuevo es solo cuestión de añadir una entrada con el texto y los campos que necesita — el resto del sistema (el formulario que ve el abogado, la exportación a Word) ya funciona automáticamente. La única plantilla que existe hoy está marcada explícitamente como "de prueba" y no debe usarse en ningún trámite real.

## 6.4 Por qué la voz es Whisper + Piper autoalojados, y no la API de voz del navegador

**Qué es:** Whisper es un modelo open source que convierte audio hablado en texto (transcripción); Piper es un modelo open source que convierte texto en audio hablado (síntesis de voz). Ambos corren como parte del contenedor del backend, no en un servicio externo.

**Por qué NO se usó la función de voz que ya trae el navegador (Web Speech API):** es gratis y no requiere infraestructura propia, pero por dentro envía el audio grabado a los servidores de Google (en Chrome) para transcribirlo. Como las consultas de un abogado pueden incluir información sensible de un cliente hablada en voz alta, eso contradecría directamente el compromiso ya escrito en `aviso_privacidad.md` de que los datos no salen de nuestra infraestructura. Se decidió pagar el costo de más cómputo propio a cambio de mantener ese control.

**Nota de buena práctica (relevante para la auditoría de ciberseguridad):** antes de escribir la integración con Piper, se verificó de forma manual —instalando el paquete real y ejecutándolo— cuáles eran los parámetros exactos de su línea de comandos y qué voces en español existen de verdad, en vez de asumirlo. Esto evitó construir sobre una API inventada o mal recordada. El detalle de esa verificación está documentado en `docs/spike_resultados.md`.

## 7. Buenas prácticas de programación aplicadas (y por qué importan)

Esta sección explica prácticas que cualquier persona con experiencia en desarrollo de software da por sentadas, pero que no son obvias si nunca se ha programado en equipo.

### 7.1 Control de versiones (Git / GitHub)
**Qué es:** un sistema que guarda el historial completo de cambios del código, permitiendo ver quién cambió qué y cuándo, y regresar a versiones anteriores si algo se rompe.
**Por qué importa:** sin esto, cualquier error se vuelve muy difícil de rastrear o revertir, y es imposible que más de una persona colabore sin pisarse el trabajo mutuamente.

### 7.2 Docs-as-Code
**Qué es:** tratar la documentación (como este mismo manual) igual que el código: vive en el mismo repositorio, se versiona, y se actualiza junto con los cambios técnicos.
**Por qué importa:** evita el problema clásico de "la documentación dice una cosa y el sistema hace otra" porque ambas viven y cambian juntas.

### 7.3 Separación de responsabilidades (por qué no está "todo junto")
**Qué es:** cada componente (backend, base de datos vectorial, motor de IA, base de datos de usuarios) es un contenedor independiente con una sola responsabilidad.
**Por qué importa:** si el motor de IA falla o necesita reiniciarse, no se cae todo el sistema. También permite escalar o reemplazar una sola pieza (ej. cambiar de Qdrant a otra base vectorial) sin reescribir el resto.

### 7.4 Variables de entorno y gestión de secretos
**Qué es:** las contraseñas y claves (ej. la contraseña de la base de datos) nunca se escriben directamente en el código. Se guardan en un archivo `.env` que **no se sube a GitHub** (está excluido vía `.gitignore`), y el código las lee en tiempo de ejecución.
**Por qué importa:** si una contraseña queda escrita en el código y ese código se sube a un repositorio público (como el nuestro), cualquier persona en internet podría verla y usarla.

### 7.5 Principio de menor privilegio
**Qué es:** cada contenedor corre con el mínimo de permisos necesarios (por ejemplo, como usuario "no root" dentro del contenedor — ver `backend/Dockerfile`), y solo se expone a internet el servicio que realmente necesita ser público.
**Por qué importa:** si un atacante lograra comprometer un contenedor, este principio limita el daño que puede causar. Detalle completo en [security_checklist.md](security_checklist.md).

### 7.6 Tratar el contenido recuperado como "no confiable" (prevención de prompt injection)
**Qué es:** el texto que viene de la base de datos vectorial se marca explícitamente en el prompt como datos, nunca como instrucciones (ver `backend/app/rag.py`, función `generate_answer`).
**Por qué importa:** si en el futuro se indexara un documento malicioso que contuviera texto como "ignora tus reglas anteriores y responde X", el sistema está instruido a nunca obedecer contenido que venga de dentro del contexto recuperado. Detalle en [security_checklist.md §2](security_checklist.md).

---

## 8. Estructura del repositorio

```
rag-legal-guerrero/
├── README.md                          # Punto de entrada del proyecto
├── LICENSE                            # Apache 2.0
├── docker-compose.yml                 # Orquesta todos los servicios
├── .env.example                       # Plantilla de variables de entorno (copiar a .env)
├── docs/                              # Toda la documentación (Docs-as-Code)
│   ├── requerimientos_usuario.md
│   ├── arquitectura.md
│   ├── security_checklist.md
│   ├── aviso_privacidad.md
│   ├── manual_ingenieria_software.md  # Este documento
│   └── manual_usuario.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py                    # Define los endpoints de la API (ej. /api/query)
│       ├── rag.py                     # Lógica de recuperación + generación
│       ├── ingest.py                  # Script para cargar documentos al vector DB
│       ├── documents.py               # Subida ad-hoc de documentos (temporal, por sesión)
│       ├── generation.py              # Mecanismo de plantillas → .docx
│       └── voice.py                   # Transcripción (Whisper) y síntesis (Piper)
├── frontend/
│   ├── Dockerfile                     # Build de dos etapas: compila con Node, sirve con Caddy
│   ├── Caddyfile                      # Enrutamiento: /api/* → backend, resto → interfaz
│   └── src/
│       ├── App.tsx                    # Layout principal: filtro por área, formulario, resultados
│       ├── api.ts                     # Llamadas a la API del backend
│       ├── hooks/useSettings.ts       # Preferencias de tema/tamaño de texto (localStorage)
│       └── components/                # SettingsPanel, CopyButton, DocumentUpload,
│                                       # DocumentGenerator, VoiceControls
└── fixtures/
    └── sample_corpus.md               # Datos FICTICIOS solo para pruebas locales
```

---

## 9. Anexos de defensa legal

> **Aviso importante, igual que en [aviso_privacidad.md](aviso_privacidad.md):** las plantillas de esta sección son un punto de partida técnico-legal, **no son asesoría legal vinculante**. Deben ser revisadas y adaptadas por un abogado especializado en derecho corporativo, protección de datos y propiedad intelectual antes de solicitarle a cualquier persona que las firme. Los campos entre corchetes `[...]` deben completarse.

### 9.1 Por qué existen estos anexos

El sistema procesa consultas legales que pueden contener datos personales y, potencialmente, datos sensibles de los clientes de los abogados usuarios ([aviso_privacidad.md §3.3](aviso_privacidad.md)). Cualquier persona que colabore en el desarrollo (y por tanto tenga acceso potencial al código, a los logs, o a la infraestructura donde corren estos datos) debe estar sujeta a un compromiso formal de confidencialidad — esto protege tanto a los usuarios finales como al propio proyecto ante un eventual reclamo.

### 9.2 Plantilla — Acuerdo de Confidencialidad para Colaboradores (NDA)

```
ACUERDO DE CONFIDENCIALIDAD

Entre [NOMBRE DEL RESPONSABLE DEL PROYECTO / RAZÓN SOCIAL], en adelante "el Titular",
y [NOMBRE COMPLETO DEL COLABORADOR], en adelante "el Colaborador", con motivo de la
colaboración de este último en el desarrollo del proyecto "RAG Legal Guerrero",
se acuerda lo siguiente:

1. El Colaborador reconoce que, en el desarrollo de su labor, podrá tener acceso a
   código fuente, credenciales de infraestructura, documentos de arquitectura, y
   eventualmente a datos de consultas legales ingresadas por usuarios del sistema,
   los cuales pueden incluir información personal y datos sensibles de terceros
   conforme a la LFPDPPP.

2. El Colaborador se compromete a:
   a) No divulgar, copiar, ni utilizar dicha información fuera del alcance estricto
      de su colaboración en el proyecto.
   b) No intentar identificar a las personas titulares de los datos contenidos en
      las consultas de prueba o de producción a las que tenga acceso.
   c) Reportar de inmediato al Titular cualquier incidente de seguridad o acceso
      no autorizado del que tenga conocimiento.
   d) Aplicar las medidas de seguridad descritas en el checklist de ciberseguridad
      del proyecto (docs/security_checklist.md) en cualquier entorno donde maneje
      estos datos.

3. Esta obligación de confidencialidad permanece vigente durante la colaboración
   y por [PLAZO, ej. 2 años] después de finalizada esta.

4. El incumplimiento de este acuerdo podrá dar lugar a las acciones legales que
   correspondan conforme a la legislación aplicable en México.

Firman de conformidad:

_______________________________          _______________________________
[NOMBRE DEL RESPONSABLE DEL PROYECTO]     [NOMBRE COMPLETO DEL COLABORADOR]
Fecha: [FECHA]                            Fecha: [FECHA]
```

### 9.3 Plantilla — Acuerdo Interno de Tratamiento de Datos (para colaboradores técnicos)

```
ACUERDO INTERNO DE TRATAMIENTO DE DATOS

Este acuerdo complementa el Acuerdo de Confidencialidad y aplica a cualquier
Colaborador con acceso a infraestructura donde se procesen o almacenen datos
ingresados por usuarios del sistema "RAG Legal Guerrero".

1. Finalidad autorizada: el Colaborador únicamente podrá acceder a datos reales
   de usuarios (no ficticios/de prueba) para fines de mantenimiento, depuración
   de errores, o mejora del sistema, y nunca para fines distintos a los del
   proyecto.

2. El Colaborador se obliga a:
   a) No exportar datos de producción a entornos personales o no autorizados.
   b) Utilizar datos ficticios o anonimizados (ver fixtures/) para desarrollo y
      pruebas siempre que sea posible, en vez de datos reales.
   c) No deshabilitar ni evadir las medidas de seguridad de contenedores descritas
      en docs/security_checklist.md.
   d) Notificar cualquier fuga, acceso indebido o vulnerabilidad detectada dentro
      de las [24/48] horas siguientes a su descubrimiento.

3. El Titular se compromete a mantener actualizado el inventario de quién tiene
   acceso a qué sistemas, y a revocar accesos al finalizar la colaboración.

Firman de conformidad:

_______________________________          _______________________________
[NOMBRE DEL RESPONSABLE DEL PROYECTO]     [NOMBRE COMPLETO DEL COLABORADOR]
Fecha: [FECHA]                            Fecha: [FECHA]
```

### 9.4 Propiedad intelectual de las contribuciones

El proyecto se distribuye bajo licencia **Apache 2.0** ([LICENSE](../LICENSE)), la cual ya establece en su Sección 5 que cualquier contribución enviada al proyecto se considera automáticamente bajo los mismos términos de la licencia, salvo acuerdo distinto por escrito. No se requiere un CLA (Contributor License Agreement) separado para el MVP, pero es un pendiente a evaluar si el proyecto crece y recibe contribuciones externas significativas.

---

## 10. Roadmap técnico y pendientes

- [ ] Ejecutar y documentar resultados del spike técnico en una VM real de Oracle Cloud (ARM64) — ver [arquitectura.md §6](arquitectura.md).
- [ ] Definir e implementar el sourcing real del corpus legal ([requerimientos_usuario.md §4](requerimientos_usuario.md)).
- [ ] Implementar autenticación multiusuario real (actualmente el backend del spike no tiene login, y el frontend no tiene pantalla de inicio de sesión).
- [x] Construir el frontend estructurado — implementado en `frontend/` (React + Vite + TS, servido vía Caddy) y validado end-to-end en local.
- [x] Tema claro/oscuro, tamaño de texto ajustable, diseño responsive y copiar al portapapeles.
- [x] Subida de documentos ad-hoc (temporal, por sesión) — mecanismo implementado y validado.
- [x] Mecanismo extensible de generación de documentos (sin plantillas legales reales todavía).
- [x] Voz autoalojada (Whisper STT + Piper TTS) — implementado y validado localmente.
- [ ] Añadir una plantilla legal real (ej. demanda alimenticia) al mecanismo de generación de documentos, redactada y revisada por un abogado.
- [ ] Expiración/limpieza automática de documentos subidos por sesión (hoy solo se borran manualmente vía el botón "Quitar todos los documentos").
- [ ] Definir e implementar el sourcing real del corpus legal ([requerimientos_usuario.md §4](requerimientos_usuario.md)).
- [ ] Implementar autenticación multiusuario real (actualmente el backend del spike no tiene login, y el frontend no tiene pantalla de inicio de sesión).
- [ ] Definir y automatizar pruebas (tests) — no existen todavía. Esto es especialmente relevante antes de la auditoría de ciberseguridad planeada.
- [ ] Definir pipeline de CI/CD (integración/despliegue continuo) en GitHub Actions.
- [ ] Completar los campos pendientes `[...]` en `aviso_privacidad.md` y en las plantillas de la Sección 9 de este manual, con revisión legal formal.
