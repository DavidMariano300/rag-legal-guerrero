"""Rate limiting por IP (slowapi/limits). Ver security_checklist.md §4 y §3.4.

Limitar por usuario autenticado en vez de por IP sería más preciso, pero por IP ya
cubre el riesgo principal (abuso/scraping) con mucha menos complejidad — suficiente
para el MVP. Mejorarlo a por-usuario queda como pendiente en el roadmap.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def ip_del_cliente(request: Request) -> str:
    # Detrás de Caddy todas las peticiones llegan con la IP del proxy, y el límite era global (5 entradas
    # de invitado por minuto para TODOS). Caddy escribe X-Real-IP (frontend/Caddyfile) y el backend solo
    # es accesible a través de Caddy, así que el encabezado no lo controla el cliente.
    return request.headers.get("x-real-ip") or get_remote_address(request)


limiter = Limiter(key_func=ip_del_cliente)
