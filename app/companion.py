"""Autenticação simples por PIN do app companheiro (PWA no celular)."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Any

log = logging.getLogger(__name__)

TOKEN_TTL_S = 12 * 3600


class CompanionAuth:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self._tokens: dict[str, float] = {}

    def pin(self) -> str:
        env = os.environ.get("LANCER_COMPANION_PIN")
        if env:
            return str(env)
        return str((self.cfg.get("companion") or {}).get("pin") or "2016")

    def enabled(self) -> bool:
        return bool((self.cfg.get("companion") or {}).get("enabled", True))

    def pair(self, pin: str | None) -> dict[str, Any] | None:
        expected = self.pin()
        given = (pin or "").strip()
        if not expected or not hmac.compare_digest(given, expected):
            return None
        self._gc()
        token = secrets.token_hex(24)
        self._tokens[token] = time.time() + TOKEN_TTL_S
        return {"token": token, "expires_in": TOKEN_TTL_S}

    def check(self, token: str | None) -> bool:
        if not token:
            return False
        self._gc()
        exp = self._tokens.get(token)
        return bool(exp and exp > time.time())

    def _gc(self) -> None:
        now = time.time()
        dead = [k for k, exp in self._tokens.items() if exp <= now]
        for k in dead:
            self._tokens.pop(k, None)


def is_local(host: str | None) -> bool:
    if not host:
        return False
    return host in {"127.0.0.1", "::1", "localhost"}


def token_from_request(authorization: str | None, cookie: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if cookie:
        for part in cookie.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "lancer_token":
                return v.strip()
    return None


def settings_digest(settings: dict) -> str:
    raw = repr(sorted((settings.get("ui") or {}).items())).encode()
    return hashlib.sha1(raw).hexdigest()[:12]
