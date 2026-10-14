"""Garde HTTP placé devant l'application MCP.

* Résout l'adresse IP du client derrière les proxys de confiance de
  l'hébergeur et l'expose aux outils (``client_ip()``) : le mode « clés
  personnelles » est limité par adresse.
* Refuse en ``429`` avec ``Retry-After`` une rafale de requêtes venue d'une même
  adresse, avant tout travail.
* Refuse de même une adresse qui accumule les jetons refusés (``401``) : deviner
  un jeton personnel ou une clé devient impraticable.

Aucun en-tête n'est journalisé ; seules les décisions le sont.
"""

from __future__ import annotations

import ipaddress
import json
import logging
from contextvars import ContextVar
from typing import Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mcp_server.quotas import SlidingWindow

LOGGER = logging.getLogger("pandecte.mcp")

UNKNOWN_IP = "inconnue"

#: Page de diagnostic (MCP_IP_DIAGNOSTIC=true) : rend à l'appelant sa propre
#: adresse telle que le serveur la voit, pour régler MCP_TRUSTED_PROXY_HOPS ou
#: MCP_CLIENT_IP_HEADER au déploiement. Désactivée par défaut.
DIAGNOSTIC_PATH = "/diagnostic-ip"
_DIAGNOSTIC_HEADERS = (b"x-forwarded-for", b"cf-connecting-ip", b"true-client-ip", b"x-real-ip")

_CLIENT_IP: ContextVar[str] = ContextVar("pandecte_client_ip", default=UNKNOWN_IP)


def client_ip() -> str:
    """Adresse du client de la requête en cours, ou ``"inconnue"``."""
    return _CLIENT_IP.get()


def _valid_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def _header_values(scope: Scope, name: bytes) -> list[str]:
    return [
        value.decode("latin-1") for key, value in scope.get("headers", []) if key == name
    ]


def resolve_client_ip(scope: Scope, trusted_hops: int, ip_header: str = "") -> str:
    """IP cliente, par ordre de priorité :

    1. ``ip_header`` (``MCP_CLIENT_IP_HEADER``) : un en-tête posé par le proxy
       de l'hébergeur et réécrit par lui à chaque requête (par exemple
       ``cf-connecting-ip``), s'il porte une seule adresse valide ;
    2. la n-ième entrée depuis la droite de X-Forwarded-For : seules les
       entrées ajoutées par les proxys de confiance sont crues, ce que le
       client a lui-même écrit se trouve plus à gauche et n'est jamais lu ;
    3. l'adresse de la socket.
    """
    if ip_header:
        values = _header_values(scope, ip_header.encode("latin-1"))
        if len(values) == 1:
            resolved = _valid_ip(values[0])
            if resolved:
                return resolved
    if trusted_hops > 0:
        forwarded = _header_values(scope, b"x-forwarded-for")
        hops = [item for item in ",".join(forwarded).split(",") if item.strip()]
        if len(hops) >= trusted_hops:
            resolved = _valid_ip(hops[-trusted_hops])
            if resolved:
                return resolved
    client = scope.get("client")
    if client:
        resolved = _valid_ip(str(client[0]))
        if resolved:
            return resolved
    return UNKNOWN_IP


class HttpGuard:
    """Middleware ASGI : adresse cliente, rafales et échecs d'authentification."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        trusted_hops: int,
        ip_header: str = "",
        diagnostic: bool = False,
        requests_per_minute: int = 300,
        auth_failures_per_window: int = 30,
        auth_failure_window_seconds: float = 600.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._app = app
        self._trusted_hops = trusted_hops
        self._ip_header = ip_header
        self._diagnostic = diagnostic
        kwargs = {"clock": clock} if clock else {}
        self._requests = SlidingWindow(requests_per_minute, 60.0, **kwargs)
        self._failures = SlidingWindow(
            auth_failures_per_window, auth_failure_window_seconds, **kwargs
        )

    @property
    def inner(self) -> ASGIApp:
        """Application protégée (son cycle de vie est piloté par l'appelant)."""
        return self._app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        ip = resolve_client_ip(scope, self._trusted_hops, self._ip_header)
        if self._diagnostic and scope.get("path") == DIAGNOSTIC_PATH:
            await _diagnostic(send, scope, ip)
            return

        wait = max(self._failures.wait_time(ip), self._requests.wait_time(ip))
        if wait > 0:
            LOGGER.warning("http_throttled reason=ip_rate")
            await _too_many_requests(send, int(wait) + 1)
            return
        self._requests.hit(ip)

        async def watch(message: Message) -> None:
            if message["type"] == "http.response.start" and message.get("status") == 401:
                self._failures.hit(ip)
            await send(message)

        token = _CLIENT_IP.set(ip)
        try:
            await self._app(scope, receive, watch)
        finally:
            _CLIENT_IP.reset(token)


async def _too_many_requests(send: Send, retry_after: int) -> None:
    body = json.dumps(
        {
            "error": "too_many_requests",
            "error_description": (
                f"Trop de requêtes depuis cette adresse ; réessayez dans {retry_after} s."
            ),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"retry-after", str(retry_after).encode("ascii")),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _diagnostic(send: Send, scope: Scope, resolved: str) -> None:
    """Ne renvoie que des données de la requête de l'appelant lui-même."""
    client = scope.get("client")
    body = json.dumps(
        {
            "resolved_ip": resolved,
            "socket_ip": str(client[0]) if client else None,
            "headers": {
                name.decode("ascii"): _header_values(scope, name)
                for name in _DIAGNOSTIC_HEADERS
            },
        },
        indent=2,
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json"),
                (b"cache-control", b"no-store"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
