"""Fonte OBD-II direta via python-can / SocketCAN (HAT MCP2515).

Envia pedidos Mode 01 no ID funcional 0x7DF (11-bit, 500 kbit/s) e lê a
resposta da ECU em 0x7E8. Quadros únicos ISO-TP (até 7 bytes de dados)
cobrem a maioria dos PIDs Mode 01.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .. import cvt_uds
from ..signals import SIGNALS, SUPPORT_PIDS, decode_mode01, parse_support_bitmask
from ..store import DataStore
from .base import VehicleSource

log = logging.getLogger(__name__)

DTC_HINTS = {
    "P0420": "Eficiência do catalisador abaixo do limiar (Banca 1)",
    "P0171": "Mistura pobre banca 1",
    "P0300": "Falhas de ignição múltiplas",
}


def _decode_dtc_bytes(a: int, b: int) -> str:
    class_map = {0: "P", 1: "C", 2: "B", 3: "U"}
    kind = class_map[(a & 0xC0) >> 6]
    d1 = (a & 0x30) >> 4
    d2 = a & 0x0F
    return f"{kind}{d1}{d2:X}{b:02X}"


class CanVehicleSource(VehicleSource):
    name = "can"

    def __init__(self, store: DataStore, cfg: dict) -> None:
        super().__init__(store, cfg)
        self._bus = None
        self._connected = False
        can_cfg = cfg.get("can", {})
        self.request_id = int(can_cfg.get("request_id", 0x7DF))
        self.response_id = int(can_cfg.get("response_id", 0x7E8))
        self.timeout_s = float(can_cfg.get("timeout_s", 0.08))

    @property
    def poll_budget_per_s(self) -> float:
        return float(self.cfg.get("scheduler", {}).get("can_budget_per_s", 40))

    def connect(self) -> bool:
        try:
            import can
        except ImportError as exc:
            log.error("python-can não instalado: %s", exc)
            return False

        can_cfg = self.cfg.get("can", {})
        channel = can_cfg.get("channel", "can0")
        bustype = can_cfg.get("interface", "socketcan")
        bitrate = int(can_cfg.get("bitrate", 500000))
        try:
            self._bus = can.interface.Bus(
                channel=channel,
                bustype=bustype,
                bitrate=bitrate,
                receive_own_messages=False,
            )
            self._connected = True
        except Exception as exc:
            log.error("Falha ao abrir SocketCAN %s: %s", channel, exc)
            self._connected = False
            return False
        self.store.set_meta("vehicle_connected", True)
        self.store.set_meta("source", self.name)
        log.info("CAN aberto em %s (%s, %s bit/s)", channel, bustype, bitrate)
        return True

    def disconnect(self) -> None:
        try:
            if self._bus:
                self._bus.shutdown()
        except Exception:
            pass
        self._connected = False
        self.store.set_meta("vehicle_connected", False)

    @property
    def connected(self) -> bool:
        return bool(self._connected and self._bus)

    def _drain(self) -> None:
        if not self._bus:
            return
        try:
            while self._bus.recv(timeout=0):
                pass
        except Exception:
            pass

    def _request(self, mode: int, pid: int | None = None, extra: bytes = b"") -> list[int] | None:
        """Envia um quadro ISO-TP de quadro único e espera 0x7E8."""
        if not self.connected:
            return None
        import can

        if pid is None:
            payload = bytes([mode]) + extra
        else:
            payload = bytes([mode, pid]) + extra
        # PCI: comprimento (número de bytes de payload)
        data = bytes([len(payload)]) + payload
        data = data.ljust(8, b"\x00")
        msg = can.Message(arbitration_id=self.request_id, data=data, is_extended_id=False)
        self._drain()
        try:
            self._bus.send(msg)
        except Exception as exc:
            log.debug("CAN send falhou: %s", exc)
            return None

        deadline = time.time() + self.timeout_s
        while time.time() < deadline:
            recv = self._bus.recv(timeout=max(0.0, deadline - time.time()))
            if recv is None:
                break
            if recv.arbitration_id != self.response_id:
                continue
            raw = list(recv.data)
            if not raw:
                continue
            length = raw[0] & 0x0F if (raw[0] & 0xF0) == 0x00 else raw[0]
            body = raw[1 : 1 + length]
            if not body:
                continue
            # 0x40 + mode para respostas positivas
            if body[0] == (0x40 | mode):
                return body[1:]  # começa no PID (mode 01) ou nos dados
            if body[0] == 0x7F:
                log.debug("NRC CAN modo %02X: %s", mode, body)
                return None
        return None

    def discover(self) -> set[int]:
        supported: set[int] = set()
        if not self.connected:
            self.supported_pids = supported
            self.after_discover()
            return supported
        for base in SUPPORT_PIDS:
            body = self._request(0x01, base)
            if not body or body[0] != base:
                continue
            supported.add(base)
            supported |= parse_support_bitmask(base, body[1:])
        self.supported_pids = supported
        self.after_discover()
        log.info("PIDs CAN suportados (%d): %s", len(supported), sorted(supported))
        return supported

    def read_pid(self, pid: int) -> float | None:
        body = self._request(0x01, pid)
        if not body or body[0] != pid:
            return None
        return decode_mode01(pid, body[1:])

    def read_battery_voltage(self) -> float | None:
        return self.read_pid(0x42)

    def read_dtcs(self) -> list[dict[str, Any]]:
        # Mode 03 — DTCs armazenados. Resposta: 43 <count> n pares.
        body = self._request(0x03)
        out: list[dict[str, Any]] = []
        mil = False
        if body:
            # body[0] pode ser a quantidade, depois pares
            data = body
            # alguns ECUs devolvem count no primeiro byte
            idx = 1 if data and len(data) % 2 == 1 else 0
            while idx + 1 < len(data):
                a, b = data[idx], data[idx + 1]
                idx += 2
                if a == 0 and b == 0:
                    continue
                code = _decode_dtc_bytes(a, b)
                out.append({"code": code, "status": "stored", "description": DTC_HINTS.get(code, "")})
        status = self._request(0x01, 0x01)
        if status and len(status) >= 2:
            # PID 01: byte A bit 7 = MIL
            mil = bool(status[1] & 0x80)
        self.store.set_meta("dtcs", out)
        self.store.set_meta("mil", mil or bool(out))
        return out

    def clear_dtcs(self) -> bool:
        body = self._request(0x04)
        # resposta positiva 44
        self.store.set_meta("dtcs", [])
        self.store.set_meta("mil", False)
        return True


    def read_cvt_temp(self) -> float | None:
        if not cvt_uds.is_enabled(self.cfg) or not self.connected:
            return None
        p = cvt_uds.params(self.cfg)
        did = p["did"]
        payload = bytes([0x22, (did >> 8) & 0xFF, did & 0xFF])
        data = bytes([len(payload)]) + payload
        data = data.ljust(8, b"\x00")
        import can
        msg = can.Message(arbitration_id=p["request_id"], data=data, is_extended_id=False)
        self._drain()
        try:
            self._bus.send(msg)
        except Exception as exc:
            log.debug("CAN Mode 22 send: %s", exc)
            return None
        import time
        deadline = time.time() + self.timeout_s
        while time.time() < deadline:
            recv = self._bus.recv(timeout=max(0.0, deadline - time.time()))
            if recv is None:
                break
            if recv.arbitration_id != p["response_id"]:
                continue
            raw = list(recv.data)
            if not raw:
                continue
            length = raw[0] & 0x0F if (raw[0] & 0xF0) == 0x00 else raw[0]
            body = raw[1 : 1 + length]
            # 0x62 = resposta positiva de 0x22; em seguida o DID de 2 bytes
            if len(body) >= 3 and body[0] == 0x62 and ((body[1] << 8) + body[2]) == did:
                temp = cvt_uds.decode_temp(body[3:], p["decode"])
                if temp is not None:
                    self.store.update("cvt_temp", round(temp, 1), "°C", self.name, "Temp. fluido CVT")
                return temp
            if body and body[0] == 0x7F:
                log.debug("NRC Mode 22 TCM: %s", body)
                return None
        return None


    def read_vin(self) -> str | None:
        """Mode 09 PID 02 com ISO-TP multi-quadro (o VIN não cabe num único frame)."""
        if not self.connected:
            return None
        from ..vin import parse_mode09_pid02
        data = self._request_isotp(0x09, 0x02, expected_len=20)
        if not data:
            return None
        return parse_mode09_pid02(data)

    def _request_isotp(self, mode: int, pid: int, expected_len: int = 20) -> bytes | None:
        """Pedido ISO-TP que aceita first-frame + consecutive frames (VIN, etc.)."""
        if not self.connected:
            return None
        import can

        payload = bytes([mode, pid])
        frame = bytes([len(payload)]) + payload
        frame = frame.ljust(8, b"\x00")
        self._drain()
        try:
            self._bus.send(can.Message(arbitration_id=self.request_id, data=frame, is_extended_id=False))
        except Exception as exc:
            log.debug("CAN VIN send: %s", exc)
            return None

        deadline = time.time() + max(self.timeout_s * 4, 0.25)
        buf = bytearray()
        need = expected_len
        while time.time() < deadline:
            recv = self._bus.recv(timeout=max(0.0, deadline - time.time()))
            if recv is None or recv.arbitration_id != self.response_id:
                continue
            raw = bytes(recv.data)
            if not raw:
                continue
            pci = raw[0] & 0xF0
            if pci == 0x00:  # single
                length = raw[0] & 0x0F
                return bytes(raw[1:1 + length])
            if pci == 0x10:  # first frame
                need = ((raw[0] & 0x0F) << 8) | raw[1]
                buf.extend(raw[2:])
                # flow control: continue, no block, no delay
                try:
                    self._bus.send(can.Message(
                        arbitration_id=self.request_id,
                        data=bytes([0x30, 0x00, 0x00, 0, 0, 0, 0, 0]),
                        is_extended_id=False,
                    ))
                except Exception:
                    return None
                continue
            if pci == 0x20:  # consecutive
                buf.extend(raw[1:])
                if len(buf) >= need:
                    return bytes(buf[:need])
        return bytes(buf) if buf else None
