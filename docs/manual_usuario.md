# Manual de Usuario — RAG Legal Guerrero

**Para:** Edgar David Mariano Ruiz (Product Owner)
**Estado:** Borrador — ya existe una interfaz visual funcional (React) validada en entorno local, con formulario de consulta, filtro por área del derecho, y paneles de respuesta/fragmentos/disclaimer tal como se describe abajo. Aún no está desplegada en la nube ni tiene inicio de sesión, así que las secciones sobre autenticación y disponibilidad pública siguen siendo previsión, no realidad todavía.
**Última actualización:** 2026-09-23
**Documentos relacionados:** [aviso_privacidad.md](aviso_privacidad.md) (léelo completo antes de usar la herramienta con datos reales de clientes)

---

## 1. ¿Qué es esta herramienta?

Es un asistente que te ayuda a **recordar o verificar rápidamente** información legal (leyes, códigos, plazos, requisitos procesales) aplicable en Guerrero, sin tener que buscar manualmente en varios documentos. Funciona parecido a preguntarle a un colega que tiene la ley siempre a la mano — con la diferencia de que quien responde es un sistema de inteligencia artificial, no una persona.

## 2. Qué SÍ hace y qué NO hace

**Sí hace:**
- Busca en la legislación indexada los artículos más relevantes para tu pregunta.
- Te da un resumen breve en lenguaje natural.
- Te muestra el **texto exacto** del artículo o ley de donde salió esa información, para que lo puedas verificar tú mismo.

**NO hace (y es importante tenerlo claro):**
- No es un abogado ni sustituye tu criterio profesional.
- No da asesoría legal vinculante.
- No garantiza que la información esté 100% actualizada o libre de errores — los modelos de IA pueden equivocarse o "alucinar" (inventar información que suena correcta pero no lo es).
- No crea una relación abogado-cliente entre tú, tus clientes y la plataforma.

Por esto, **cada respuesta del sistema incluye un aviso de que fue generada por IA y debe verificarse** antes de usarse en cualquier trámite, escrito o asesoría real. Ver el detalle legal completo en [aviso_privacidad.md](aviso_privacidad.md).

## 2.1 Funciones adicionales (agregadas 2026-09-23)

- **Preferencias (⚙ arriba a la derecha):** puedes cambiar entre tema claro/oscuro y ajustar el tamaño de texto a tu gusto; la interfaz también se adapta a pantallas de celular/tablet.
- **Copiar:** cada respuesta y cada fragmento citado tiene un botón para copiarlo directamente al portapapeles.
- **Subir un documento:** puedes adjuntar un PDF, Word o texto (máx. 15 MB) para preguntar sobre ese documento en particular (ej. un contrato). Es **temporal**: solo dura mientras tengas la pestaña abierta, no se agrega al corpus legal general ni lo ve ningún otro usuario.
- **Voz:** puedes dictar tu pregunta con el botón del micrófono (🎤) y escuchar la respuesta en voz alta (🔊 Escuchar). Todo el procesamiento de voz ocurre en nuestra propia infraestructura, nunca se envía a un servicio externo.
- **Generar documento:** al final de la página hay un mecanismo para generar documentos `.docx` a partir de una plantilla. **Importante:** por ahora solo existe una plantilla de prueba ficticia para validar que el mecanismo funciona — todavía no hay ninguna plantilla de un documento legal real disponible.

## 3. Cómo se ve una respuesta

Cuando hagas una pregunta, la respuesta llegará dividida en tres partes claramente separadas (no mezcladas en un solo bloque de texto):

1. **Respuesta breve** — un resumen en lenguaje natural de lo que dice la ley al respecto.
2. **Fragmento(s) citado(s)** — el texto textual del artículo o ley, con su fuente exacta (ej. "Art. 45, Código Civil del Estado de Guerrero"), para que lo puedas revisar tú mismo antes de usarlo.
3. **Aviso de IA** — un recordatorio visible de que la respuesta puede tener errores y debe verificarse.

**Regla de oro:** si el resumen y el fragmento citado parecen decir cosas distintas, o el fragmento no respalda claramente el resumen, confía en el fragmento textual (o mejor aún, verifica directamente con la fuente oficial) y no en el resumen generado.

## 4. Cómo hacer una buena pregunta

El sistema responde mejor con preguntas concretas que con preguntas muy abiertas. Ejemplos:

| En vez de... | Pregunta mejor... |
|---|---|
| "Háblame de pensión alimenticia" | "¿Qué porcentaje de los ingresos se puede fijar como pensión alimenticia provisional?" |
| "Dime sobre despidos" | "¿Cuánto es la indemnización por despido injustificado según la Ley Federal del Trabajo?" |

## 5. Manejo de datos de tus clientes — importante

Cuando uses la herramienta con casos reales:

- **Evita escribir nombres completos, domicilios exactos u otros identificadores innecesarios** de tus clientes directamente en la consulta. Pregunta en términos generales del supuesto legal, no con los datos identificables del caso.
- Esto es responsabilidad tuya como usuario profesional (ver [aviso_privacidad.md §3.3](aviso_privacidad.md)), y protege tanto a tus clientes como a ti mismo.

## 6. ¿Qué hacer si una respuesta parece incorrecta o desactualizada?

1. No la uses en ningún trámite hasta verificarla contra la fuente oficial (Periódico Oficial del Estado, Diario Oficial de la Federación, etc.).
2. Repórtalo (mientras el proyecto es un prototipo, repórtalo directamente en el repositorio de GitHub como un "issue", o al equipo de desarrollo).
3. Recuerda que el corpus de leyes se actualiza periódicamente, pero puede haber un desfase entre una reforma reciente y su incorporación al sistema.

## 7. Estado actual del proyecto (léelo para no llevarte sorpresas)

Este manual describe el funcionamiento **previsto** del producto terminado. Al día de hoy (2026-09-23):

- Ya existe una interfaz visual funcional (formulario, filtro por área, paneles de respuesta/fragmentos), pero **solo probada en entorno local de desarrollo** — todavía no está publicada en un enlace accesible desde internet.
- El corpus indexado actualmente son **datos de prueba ficticios**, no legislación real — ver `fixtures/sample_corpus.md` en el repositorio.
- No existe todavía inicio de sesión (login) ni gestión de múltiples usuarios.

Este manual se irá actualizando a medida que estas piezas se construyan, siguiendo la metodología Docs-as-Code del proyecto.

## 8. Preguntas frecuentes

**¿Puedo confiar ciegamente en las respuestas?**
No. Trata cada respuesta como el punto de partida de tu investigación, no como la conclusión.

**¿Mis consultas se comparten con terceros?**
No — todo el procesamiento ocurre en infraestructura propia del proyecto (modelos open source auto-alojados), no se envía a ninguna API externa de pago. Detalle completo en [aviso_privacidad.md](aviso_privacidad.md).

**¿Qué áreas del derecho cubre?**
Por diseño, cubre de forma amplia varias ramas (penal, civil/familiar, laboral, administrativo/fiscal, amparo) — ver [requerimientos_usuario.md §2](requerimientos_usuario.md). La cobertura real dependerá de qué tan completo esté el corpus indexado en cada momento.
