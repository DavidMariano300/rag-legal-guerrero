# Despliegue de la demo en la nube

**Objetivo:** un link HTTPS para el cliente que no dependa de la laptop, sin gastar dinero hasta que el cliente
apruebe el producto.

**Estado (2026-10-28):** desplegado en **Azure for Students**, en
<https://amate-demo.northcentralus.cloudapp.azure.com>. Solo CPU, sin terceros: el LLM, los embeddings y la base
vectorial corren en la VM.

## 1. Por qué Azure for Students

- **Oracle Always Free** (2 OCPU / 12 GB, gratis permanente) rechazó la tarjeta de débito en el registro y luego
  bloqueó los reintentos ("Se ha superado el número máximo de solicitudes"). Oracle no acepta débito con NIP,
  tarjetas virtuales ni prepagadas. Sigue siendo la opción gratuita de largo plazo si se registra con tarjeta
  de crédito; esta misma configuración sirve tal cual.
- **Azure for Students**, con el correo institucional: **100 USD de crédito por 12 meses, sin tarjeta.** Sin
  tarjeta registrada, cuando se agota el crédito la suscripción se deshabilita y **no puede generar cobros**.
- **Restricciones de la suscripción de estudiante** (verificadas con `az`):
  - **Regiones permitidas:** canadacentral, francecentral, norwayeast, northcentralus y swedencentral.
  - **Cuota:** 6 vCPU por región.
  - **Sin cuota** para las VM ARM Cobalt (Dpsv6/Epsv6) ni para las de GPU vigentes.

## 2. La VM

| | |
|---|---|
| Tamaño | `Standard_B4ps_v2`: 4 núcleos ARM (Ampere Altra), 16 GB, *burstable* |
| Región | North Central US (Illinois), la permitida más cercana a México |
| Costo | $0.134/h + disco Standard SSD de 64 GB + IP pública ≈ **107 USD/mes encendida 24/7** → los 100 USD alcanzan ~4 semanas |
| Imagen | Ubuntu 24.04 LTS ARM64 |
| Red (NSG `amate-demo-nsg`) | 80/443 abiertos a internet; **22 (SSH) solo desde la IP de la casa del administrador** |
| Acceso | `ssh -i ~/.ssh/amate_oracle ubuntu@amate-demo.northcentralus.cloudapp.azure.com` (solo llave; la privada no sale de la laptop) |

*Burstable:* la VM acumula créditos de CPU mientras está ociosa y los gasta a toda velocidad durante las
consultas. A una demo con consultas esporádicas le basta; un uso continuo la frenaría a su línea base.

**Para que el crédito dure más**, apagar la VM cuando no se use (*Stop* en el portal la desasigna y deja de
cobrar el cómputo, no el disco) o programar el apagado nocturno (*Auto-shutdown*). Mientras esté apagada, el link
no responde.

**Si la IP de la casa cambia** y el SSH deja de conectar:

```bash
docker run --rm -v ~/.azure:/root/.azure mcr.microsoft.com/azure-cli:2.89.1 az network nsg rule update -g amate-demo --nsg-name amate-demo-nsg -n ssh-solo-casa --source-address-prefixes "$(curl -s https://api.ipify.org)/32"
```

## 3. Cómo se montó (reproducible)

La CLI de Azure corre en un contenedor (`mcr.microsoft.com/azure-cli`), con la sesión en `~/.azure`. El inicio
de sesión es por código de dispositivo: la contraseña la escribe la persona dueña de la cuenta en
microsoft.com/devicelogin.

1. `az group create`, NSG con las dos reglas de arriba y `az vm create` (imagen
   `Canonical:ubuntu-24_04-lts:server-arm64:latest`, `--public-ip-address-dns-name amate-demo`).
2. `ssh … 'bash -s' < scripts/preparar_vm.sh`: Docker, Compose y swap de 4 GB. El paso de iptables solo aplica a
   Oracle.
3. `.env` propio de la VM con secretos nuevos (no se copia el de la laptop): `JWT_SECRET_KEY`,
   `POSTGRES_PASSWORD`, `PERMITIR_INVITADOS=true`,
   `COMPOSE_FILE=docker-compose.yml:docker-compose.nube.yml` y
   `SITIO=amate-demo.northcentralus.cloudapp.azure.com`.
4. `scripts/desplegar.sh <dominio>`: copia el código por rsync (sin `.git`, `node_modules` ni `.env`) y construye
   las imágenes **en la VM**, porque son ARM.
5. `docker compose exec ollama ollama pull qwen3.5:4b`.
6. **Corpus sin re-embeber:** snapshot de la colección `legal_corpus_bge_m3` de la Qdrant local, `scp` a la VM y
   restauración por la API de Qdrant. Re-embeber 22,769 fragmentos con bge-m3 en CPU ARM tomaría horas.

Caddy obtiene el certificado HTTPS de Let's Encrypt para `SITIO` automáticamente y lo guarda en el volumen
`caddy_data`.

## 4. Actualizar la demo

```bash
scripts/desplegar.sh amate-demo.northcentralus.cloudapp.azure.com
```

## 5. Latencia

En CPU cada respuesta tarda **111–117 s** (medido el 2026-10-28 por el link público, contexto 8192). La interfaz
muestra los segundos transcurridos y avisa que puede tardar un par de minutos. Se probó la cuantización Q4_0
(~20 % más rápida en ARM) y se descartó: bajó a 73 % de respuestas correctas y citó un número de artículo equivocado.
Ojo con la memoria: con dos modelos cargados la VM entra a swap y una consulta pasa de 2 a 3+ min. Las mediciones están en [investigacion_nube_gpu.md](investigacion_nube_gpu.md).
