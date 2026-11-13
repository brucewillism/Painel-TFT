"""Leitura experimental da temperatura do fluido da CVT (UDS Mode 22 / TCM).

O Lancer HL 2016 usa uma Jatco (provavelmente JF011E / F1CJA). A temperatura
do ATF/CVT **não** é um PID Mode 01 padrão: ela mora na TCM, tipicamente via
UDS Mode 22 (ReadDataByIdentifier) no ID CAN 0x7E1 (resposta 0x7E9).

O identificador (DID) varia de um ano/ECU para outro. O valor padrão 0x2101
é só um ponto de partida — confirme com um log CAN do seu carro antes de
confiar no número. Por isso a função vem **desligada** no config.yaml
(`cvt.fluid_temp_enabled: false`).

Caminhos suportados:
  - Fonte CAN (SocketCAN / HAT MCP2515): pedido direto 22 DID para 0x7E1.
  - Fonte OBD (ELM327): exige ATSH para trocar o header. Clones v2.1
    muitas vezes ignoram ou travam; se isso acontecer, deixe desligado
    até ter o HAT CAN.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def as_int(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, str):
        return int(value, 0)
    return int(value)


def decode_temp(payload: list[int], mode: str = "a_minus_40") -> float | None:
    if not payload:
        return None
    kind = (mode or "a_minus_40").lower()
    if kind == "u16_minus_40":
        if len(payload) < 2:
            return None
        return float((payload[0] << 8) + payload[1]) - 40.0
    if kind == "raw_a":
        return float(payload[0])
    return float(payload[0]) - 40.0


def is_enabled(cfg: dict) -> bool:
    return bool((cfg.get("cvt") or {}).get("fluid_temp_enabled", False))


def params(cfg: dict) -> dict:
    c = cfg.get("cvt") or {}
    return {
        "request_id": as_int(c.get("tcm_request_id"), 0x7E1),
        "response_id": as_int(c.get("tcm_response_id"), 0x7E9),
        "did": as_int(c.get("did"), 0x2101),
        "decode": c.get("decode") or "a_minus_40",
        "interval_s": float(c.get("interval_s", 5)),
    }
