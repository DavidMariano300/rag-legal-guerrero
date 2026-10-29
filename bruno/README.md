# Colección de Bruno — RAG Legal Guerrero

Colección de peticiones para probar la API manualmente o en lote, usando [Bruno](https://www.usebruno.com/)
(cliente de API 100% open source — coherente con la regla #1 del proyecto). Las peticiones se guardan como
archivos de texto `.bru`, versionables en git; no hay ninguna cuenta ni sincronización en la nube involucrada.

## Cómo usarla

1. Abre Bruno → **Open Collection** → selecciona la carpeta `bruno/RAG-Legal-Guerrero`.
2. Arriba a la derecha, selecciona el entorno **Local** (stack en `docker compose`) o **Tunnel-temporal**
   (el túnel público de Cloudflare, si sigue activo — revisa con quien lo levantó).
3. Abre `Auth/Registro.bru` o `Auth/Login.bru`, pon tu correo/contraseña reales, y presiona **Send**.
   El script de la petición guarda el token automáticamente en la variable de entorno `token`.
4. Ya puedes correr cualquier otra petición de la colección — usan `{{token}}` automáticamente.

## Qué incluye

- **Auth/** — Registro y Login (guardan el token solos).
- **Consultas/** — una pregunta que sí tiene respuesta en el corpus, y una pregunta fuera de tema con una
  prueba automatizada (`tests {}`) que verifica que el sistema rechace en vez de alucinar — el mismo tipo
  de prueba de estrés que originó el mecanismo anti-alucinación (ver `docs/spike_resultados.md §5.3`).
- **Documentos/** — listar las plantillas de generación de documentos disponibles.

## Correr todo desde la terminal (sin abrir la app de Bruno)

```bash
npx @usebruno/cli run --env Local bruno/RAG-Legal-Guerrero
```

Requiere Node 20+ (el CLI usa `crypto.subtle`, no disponible por defecto en Node 18 sin el flag
`--experimental-global-webcrypto`).
