# Checklist de Ciberseguridad Inicial — Sistema RAG Jurídico (Guerrero)

**Estado:** Borrador inicial — para revisión antes de cada fase de despliegue (dev → staging → producción).
**Alcance:** Sistema RAG contenerizado (Docker) con LLMs locales vía Ollama, orientado a consultas legales para abogados en Guerrero.

Marca cada ítem como `[ ]` pendiente, `[~]` en progreso o `[x]` completado. Este documento debe vivir en el repo y actualizarse en cada sprint de seguridad.

---

## 1. Endurecimiento de Contenedores Docker

### 1.1 Imágenes base
- [ ] Usar imágenes base oficiales y mínimas (`-slim`, `-alpine`, o `distroless`) — nunca `latest` sin pin de versión/digest.
- [ ] Fijar versiones exactas con hash (`image@sha256:...`) para builds reproducibles y evitar sustitución silenciosa de imágenes.
- [ ] Escanear imágenes con un scanner de vulnerabilidades (Trivy, Grype, Docker Scout) en CI, con umbral de bloqueo (ej. no permitir CVEs `CRITICAL`).
- [ ] Reconstruir y re-escanear imágenes periódicamente (no solo al hacer build inicial) para capturar CVEs nuevos en dependencias del OS.

### 1.2 Configuración de contenedores en runtime
- [ ] Ejecutar todos los contenedores como usuario no-root (`USER` en Dockerfile, no confiar en el `root` por defecto).
- [ ] Usar `--read-only` en el filesystem raíz del contenedor donde sea posible, con volúmenes explícitos `tmpfs`/montados para lo que sí necesite escritura.
- [ ] Eliminar capabilities de Linux innecesarias: `cap_drop: ALL` y solo agregar (`cap_add`) las estrictamente necesarias.
- [ ] Establecer `no-new-privileges: true` para evitar escalación vía binarios setuid.
- [ ] Definir límites de recursos (`mem_limit`, `cpus`, `pids_limit`) para mitigar DoS por agotamiento de recursos (relevante para el contenedor de Ollama, que puede ser intensivo en RAM/GPU).
- [ ] No montar el socket de Docker (`/var/run/docker.sock`) dentro de ningún contenedor de la aplicación (evita escape a control total del host).
- [ ] Aplicar perfiles `seccomp` y `AppArmor`/`SELinux` (no usar `--privileged` bajo ninguna circunstancia).

### 1.3 Red y aislamiento
- [ ] Definir redes Docker internas (`internal: true`) para servicios que no necesitan salida a Internet (ej. la red entre el servicio RAG y Ollama).
- [ ] Exponer al host únicamente el puerto del frontend/API gateway; el resto de servicios (vector DB, Ollama, backend) permanecen solo en red interna.
- [ ] Segmentar por servicio: contenedor de la base de datos vectorial, contenedor de Ollama, contenedor de la app RAG y proxy inverso en redes/segmentos separados según el principio de menor privilegio.
- [ ] Configurar TLS interno o al menos autenticación entre servicios si el tráfico interno maneja datos sensibles (consultas legales).

### 1.4 Gestión de secretos
- [ ] Nunca incluir credenciales, API keys o tokens en el `Dockerfile` o en variables de entorno versionadas en `docker-compose.yml`.
- [ ] Usar `docker secrets`, un vault (HashiCorp Vault, SOPS) o variables de entorno inyectadas en runtime desde un `.env` no versionado (`.gitignore`).
- [ ] Rotar credenciales de servicios (ej. contraseñas de la base de datos vectorial) periódicamente.

### 1.5 Supply chain / build
- [ ] Usar multi-stage builds para no incluir herramientas de compilación ni dependencias de desarrollo en la imagen final.
- [ ] Congelar dependencias (`requirements.txt` con hashes, `poetry.lock`, `package-lock.json`) para evitar ataques de tipo dependency confusion.
- [ ] Firmar imágenes (Docker Content Trust / cosign) si se publican en un registry propio.
- [ ] Mantener un `docker-compose.yml` de producción separado del de desarrollo (sin bind-mounts de código fuente, sin puertos de debug expuestos).

---

## 2. Prevención de Prompt Injection en el RAG

### 2.1 Aislamiento del contenido recuperado
- [ ] Tratar todo el texto recuperado del vector store (documentos legales, jurisprudencia, plantillas) como **datos no confiables**, nunca como instrucciones.
- [ ] Delimitar explícitamente en el prompt de sistema qué es "contexto recuperado" vs. "instrucción del sistema" (ej. con tags claros tipo `<contexto>...</contexto>`) y reforzar en el system prompt que el contenido dentro de esos tags nunca debe interpretarse como una orden.
- [ ] Instruir explícitamente al modelo (system prompt) a ignorar cualquier instrucción, orden o intento de cambio de rol que aparezca dentro de los documentos recuperados o en el input del usuario que contradiga las reglas del sistema.

### 2.2 Control de la cadena de recuperación (retrieval)
- [ ] Curar y validar la fuente de los documentos indexados (ingestión controlada) — evitar indexar contenido de fuentes públicas no verificadas sin revisión, ya que un documento envenenado podría contener instrucciones ocultas ("injection indirecto").
- [ ] Sanitizar documentos antes de indexarlos: remover metadatos ejecutables, scripts, texto oculto (blanco sobre blanco, fuente tamaño 0) o caracteres de control Unicode usados para ofuscar instrucciones.
- [ ] Limitar el tamaño/cantidad de chunks inyectados en el contexto para reducir superficie de ataque y controlar costos.

### 2.3 Diseño del prompt y del modelo
- [x] **Cerrado 2026-09-24:** system prompt robusto que define el rol, exige responder solo con el contexto proporcionado, y exige un rechazo explícito cuando el contexto no corresponde a la materia preguntada (`backend/app/rag.py`, `SYSTEM_PROMPT`) — mitiga alucinación por desajuste entre la pregunta y un corpus incompleto. Validado con preguntas fuera del corpus (ver [spike_resultados.md §5.3](spike_resultados.md)). **Limitación conocida:** el modelo pequeño (`llama3.2:3b`) rechaza correctamente pero no siempre usa la frase exacta pedida — no depender de un match de string exacto para detectar rechazos de forma automatizada.
- [x] **Cerrado 2026-10-10:** verificación determinista de la salida. Cada cita entre comillas de la respuesta debe aparecer literalmente en el fragmento del artículo que se cita; si no, se sustituye por el rechazo y la API devuelve `respaldada=false` (`rag.verificar_citas`, tests en `tests/test_verificar_citas.py`). Las cifras de aguinaldo, vacaciones y prima se calculan en Python, no en el LLM (`calculos.py`). **Limitación conocida:** no detecta un artículo real aplicado al supuesto equivocado; ver [refactorizacion_rag.md §8](refactorizacion_rag.md).
- [x] **Cerrado 2026-10-10:** `/api/query` responde 503 (no un 500 sin manejar) cuando Ollama no responde a tiempo.
- [ ] Evaluar el uso de un modelo separado y más pequeño (o reglas heurísticas) como "guardia" (guardrail) que analice el input del usuario y el contexto recuperado antes de pasarlo al LLM principal, buscando patrones de inyección conocidos.
- [ ] No permitir que la salida del LLM ejecute acciones automáticamente (function calling / tool use) sin validación humana o de reglas — especialmente si en el futuro se agregan herramientas (ej. generación de documentos, envío de correos, consultas a APIs externas).
- [ ] Si se usa function calling, validar y limitar estrictamente qué funciones puede invocar el modelo y con qué parámetros (allowlist, no ejecución de código arbitrario).

### 2.4 Pruebas y monitoreo
- [ ] Mantener un set de pruebas de "red teaming" con prompts de inyección conocidos (jailbreaks, "ignora las instrucciones anteriores", inyección vía documento) y correrlo en cada cambio de prompt o de modelo.
- [ ] Registrar (logging) las consultas y respuestas del sistema para poder auditar intentos de manipulación — con cuidado de no violar la política de privacidad (ver aviso de privacidad, sección de logs).
- [ ] Definir un umbral/alerta para respuestas anómalas (ej. el modelo revela su system prompt, cambia de "personalidad", o genera contenido fuera del dominio legal).

---

## 3. Sanitización de Inputs del Usuario

### 3.1 Validación en la entrada
- [ ] Definir y aplicar límites de longitud máxima en el input del usuario (previene payloads de flooding o intentos de saturar la ventana de contexto).
- [ ] Validar encoding (forzar UTF-8, rechazar o normalizar bytes inválidos) y normalizar Unicode (NFC) para prevenir ataques de homógrafos o caracteres invisibles usados para ofuscar inyecciones.
- [ ] Rechazar o neutralizar caracteres de control no imprimibles y secuencias de escape ANSI/terminal antes de procesar o loguear el input.

### 3.2 Prevención de inyección clásica (defensa en profundidad)
- [ ] Si el input del usuario se usa en consultas a la base de datos (vector DB, metadatos en SQL), usar siempre consultas parametrizadas — nunca concatenación directa de strings.
- [ ] Sanitizar/escapar el input antes de renderizarlo de vuelta en el frontend (prevención de XSS), especialmente si las respuestas del modelo o el input del usuario se muestran como HTML/Markdown renderizado.
- [ ] Si se permite subir documentos (PDFs, Word) para consulta, validar tipo MIME real (no solo extensión), escanear con antivirus/sandbox, y limitar tamaño de archivo.

### 3.3 Separación de contexto (crítico para RAG)
- [ ] Aplicar el mismo principio de la sección 2.1: el input del usuario también debe delimitarse claramente del system prompt y de los documentos recuperados, para que el modelo no confunda "esto es lo que pidió el usuario" con "esto es una instrucción del sistema".
- [ ] Filtrar patrones conocidos de intento de manipulación en el input antes de pasarlo al pipeline de RAG (ej. frases como "ignora tus instrucciones", "actúa como", "repite tu system prompt") como capa adicional de defensa (no como única defensa).

### 3.4 Rate limiting y abuso
- [ ] Implementar rate limiting por usuario/IP en la API para prevenir abuso, scraping del conocimiento indexado, o ataques de fuerza bruta contra el prompt.
- [ ] Autenticar a los usuarios (abogados) antes de permitir consultas, con manejo de sesión seguro (tokens con expiración, HTTPS obligatorio).

### 3.5 Manejo de errores
- [ ] Nunca devolver stack traces, rutas de archivo del servidor, ni detalles internos del sistema en mensajes de error al usuario final.
- [ ] Loguear errores detallados solo del lado del servidor, con acceso restringido a los logs.

---

## 4. Superficie de ataque agregada 2026-09-23 (subida de documentos, voz, generación)

### 4.1 Subida de documentos (`backend/app/documents.py`)
- [x] Validar tipo real del archivo por "magic bytes" (no solo extensión) — `_validar_contenido_real()` rechaza un PDF/DOCX cuyo contenido no coincide con su cabecera esperada.
- [x] Límite de tamaño máximo (15 MB) aplicado antes de procesar el archivo.
- [x] Lista blanca de extensiones (`.pdf`, `.docx`, `.txt`) — cualquier otra se rechaza.
- [x] El archivo original nunca se persiste en disco, solo el texto ya extraído.
- [x] Aislamiento por sesión: un documento subido solo es recuperable con el mismo `session_id`, nunca cruza entre usuarios (ver `retrieve_session_fragments`).
- [x] **Cerrado 2026-09-23:** expiración automática — `iniciar_limpieza_periodica()` corre cada `SESSION_CLEANUP_INTERVAL_SECONDS` (1h por defecto) y purga documentos con más de `SESSION_DOCUMENT_TTL_SECONDS` (24h por defecto) de antigüedad.
- [ ] **Pendiente:** no se escanea el contenido extraído con un antivirus/sandbox — el texto extraído se trata como no confiable a nivel de prompt (sección 2), pero no hay una capa de escaneo de malware sobre el binario original antes de descartarlo.
- [x] **Cerrado 2026-09-23:** rate limiting de 10/minuto sobre `/api/documents/upload` (ver sección 5).

### 4.2 Generación de documentos (`backend/app/generation.py`)
- [x] Los valores de los campos del formulario se insertan en el `.docx` vía Jinja2 `Template(...).render(**values)` sobre texto de plantilla fijo definido en el código, no sobre una plantilla controlada por el usuario — el usuario nunca puede inyectar su propia sintaxis Jinja2 como plantilla, solo como valores de campo.
- [ ] **Pendiente:** no hay sanitización explícita de los valores de campo contra contenido malicioso incrustado en un `.docx` (ej. macros) — no aplica hoy porque `python-docx` genera el archivo desde cero y no incluye macros, pero debe revisarse si en el futuro se permite subir plantillas `.docx` externas.

### 4.3 Voz (`backend/app/voice.py`)
- [x] Las llamadas a Piper se hacen con `subprocess.run` pasando argumentos como **lista** (nunca como string concatenado ni `shell=True`), lo que evita inyección de comandos de shell.
- [x] Timeouts definidos en las llamadas a `subprocess.run` (60-120s) para evitar que un proceso colgado agote recursos indefinidamente.
- [x] **Cerrado 2026-09-23:** `validar_duracion_audio()` lee solo los metadatos del contenedor de audio (sin decodificar todo el archivo) y rechaza audios de más de `MAX_AUDIO_DURATION_SECONDS` (120s por defecto).
- [ ] **Pendiente:** medir el impacto real en RAM del backend con Whisper + Piper + embeddings cargados simultáneamente en la VM ARM64 real (ver `docs/arquitectura.md §2.2`).

---

## 5. Autenticación y rate limiting (agregado 2026-09-23)

### 5.1 Autenticación (`backend/app/auth.py`, `backend/app/models.py`)
- [x] Contraseñas nunca se guardan en texto plano — hasheadas con `bcrypt` (salt aleatorio por hash, verificado en `tests/test_password_hashing.py`).
- [x] Sesiones vía JWT firmado (`HS256`) con expiración de 24h — no hay sesiones que vivan para siempre.
- [x] `JWT_SECRET_KEY` se lee de variable de entorno; si falta, se genera una clave aleatoria **por proceso** con un warning explícito en el log (evita el error más común: una clave hardcodeada en el código fuente). **Antes de producción es obligatorio definir un valor propio en `.env`** — si no, todas las sesiones se invalidan en cada reinicio del backend.
- [x] Todos los endpoints que exponen datos o consumen cómputo (`/api/query`, `/api/documents/*`, `/api/voice/*`) requieren un JWT válido vía `Depends(get_current_user)`. Verificado en `tests/test_auth.py` (incluye caso de token ausente, token inválido, y acceso exitoso).
- [ ] **Pendiente:** no hay revocación de tokens (logout del lado servidor) ni refresh tokens — el logout actual solo borra el token en el navegador (`localStorage`), el JWT sigue siendo técnicamente válido hasta su expiración natural si alguien lo capturó antes.
- [ ] **Pendiente:** no hay verificación de correo electrónico ni recuperación de contraseña.

- [x] Acceso como invitado (`POST /api/auth/invitado`, agregado 2026-10-27) para la demo con abogados: entrega un JWT de 4 h de un usuario compartido (`invitado@amate.invalid`, dominio `.invalid` que `EmailStr` rechaza, así que nadie puede registrarlo ni entrar con contraseña). Limitado a 5/minuto por IP y **desactivado salvo `PERMITIR_INVITADOS=true`** (Docker Compose lo activa por defecto para la demo). Cualquiera con la URL puede consumir cómputo del LLM: desactivarlo cuando haya usuarios reales.

- [x] **Demo pública por túnel (2026-10-27):** el servicio `tunel` (Cloudflare quick tunnel, perfil `demo`) publica
  SOLO el proxy Caddy; backend, Ollama, Qdrant y Postgres siguen en la red interna. Los puertos de depuración
  de Ollama (11435) y Qdrant (6333) pasaron de `0.0.0.0` a `127.0.0.1`: antes cualquiera en la misma red
  Wi-Fi podía usar Ollama o leer y borrar la base vectorial (Qdrant no tiene autenticación).

### 5.2 Rate limiting (`backend/app/rate_limit.py`, vía `slowapi`)
- [x] Límites aplicados: `/api/auth/login` y `/api/auth/register` 10/min (mitiga fuerza bruta), `/api/query` 20/min, `/api/documents/upload` 10/min, `/api/voice/*` 15/min — todo por dirección IP.
- [x] **Validado con prueba real:** 12 peticiones consecutivas a `/api/auth/login` → las primeras 10 devuelven 200, la 11 y 12 devuelven 429.
- **Nota para quien vuelva a probar esto:** el límite es "N por minuto de ventana", no un tope total fijo. Una prueba de ráfaga contra un endpoint LENTO (ej. `/api/query`, que espera la generación real del LLM) puede tardar más de 60 segundos en completarse, dando la falsa impresión de que el límite no funciona cuando en realidad la ventana ya se reinició a mitad de la prueba. Para probar rate limiting, usar un endpoint rápido (ej. `/api/auth/login`) o cronometrar la ráfaga.
- [x] **Corregido 2026-10-27:** detrás de Caddy todas las peticiones llegaban con la IP del proxy, así que los
  límites eran **globales** (p. ej. 5 entradas de invitado por minuto para todos). Ahora Caddy toma la IP real
  (`Cf-Connecting-Ip` del túnel, solo de proxies de red privada), la manda en `X-Real-IP` (reescrito siempre) y
  `app/rate_limit.py` limita con ella. Prueba: `test_limite_por_ip_real_detras_del_proxy`.
- [ ] **Pendiente:** el límite es por IP, no por usuario autenticado — dos usuarios detrás del mismo NAT/proxy comparten el mismo límite. Mejorar a limitar por `user_id` del JWT es un roadmap razonable.

---

## Próximos pasos sugeridos
1. Priorizar los ítems de la sección 1.2 y 1.3 (aislamiento de red y privilegios) antes del primer despliegue, ya que son la base de todo lo demás.
2. Definir el set de pruebas de red-teaming de prompt injection (sección 2.4) como parte del pipeline de CI/CD.
3. Revisar este checklist junto con `docs/aviso_privacidad.md` para asegurar que el logging (sección 2.4 y 3.5) sea consistente con lo que se le informa al usuario.
4. Antes de la auditoría de ciberseguridad externa: cerrar los pendientes marcados `[ ]` de la sección 4 (rate limiting de subida, expiración de documentos de sesión, límite de duración de audio), ya que son la superficie de ataque más nueva y menos probada del sistema.
