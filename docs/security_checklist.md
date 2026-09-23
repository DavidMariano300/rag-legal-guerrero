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
- [ ] Usar un system prompt robusto que defina explícitamente el rol ("asistente de investigación legal, no eres un abogado, no tomas decisiones"), los límites de la tarea y qué hacer ante instrucciones sospechosas.
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

## Próximos pasos sugeridos
1. Priorizar los ítems de la sección 1.2 y 1.3 (aislamiento de red y privilegios) antes del primer despliegue, ya que son la base de todo lo demás.
2. Definir el set de pruebas de red-teaming de prompt injection (sección 2.4) como parte del pipeline de CI/CD.
3. Revisar este checklist junto con `docs/aviso_privacidad.md` para asegurar que el logging (sección 2.4 y 3.5) sea consistente con lo que se le informa al usuario.
