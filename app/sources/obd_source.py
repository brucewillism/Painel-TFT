"""Fonte OBD-II via python-OBD (ELM327 Bluetooth em /dev/rfcomm0 ou serial)."""

from __future__ import annotations

import logging
import time
from typing import Any

from .. import cvt_uds
from ..signals import SIGNALS, SUPPORT_PIDS, parse_support_bitmask
from ..store import DataStore
from .base import VehicleSource

log = logging.getLogger(__name__)

# Tradução mínima de códigos comuns (o restante fica só com o código).
DTC_HINTS = {
    "P0128": "Termostato do arrefecimento — temperatura abaixo",
    "P0133": "Sonda lambda B1S1 resposta lenta",
    "P0171": "Mistura pobre banca 1",
    "P0172": "Mistura rica banca 1",
    "P0300": "Falhas de ignição múltiplas",
    "P0301": "Falha de ignição cilindro 1",
    "P0420": "Eficiência do catalisador abaixo do limiar (Banca 1)",
    "P0442": "Vazamento pequeno no canister/EVAP",
    "P0456": "Vazamento muito pequeno EVAP",
    "P0500": "Sensor de velocidade do veículo",
}


def _cmd_for_pid(obd, pid: int):
    """Encontra o comando python-OBD correspondente ao PID Mode 01."""
    try:
        from obd import commands, ObdCommand, Mode01

        for cmd in commands.modes[1]:
            if getattr(cmd, "pid", None) == pid:
                return cmd
    except Exception:
        return None
    return None


class ObdVehicleSource(VehicleSource):
    name = "obd"

    def __init__(self, store: DataStore, cfg: dict) -> None:
        super().__init__(store, cfg)
        self._conn = None
        self._connected = False
        self._cmd_cache: dict[int, Any] = {}

    @property
    def poll_budget_per_s(self) -> float:
        return float(self.cfg.get("scheduler", {}).get("elm_budget_per_s", 5))

    def connect(self) -> bool:
        try:
            import obd
        except ImportError as exc:
            log.error("python-OBD não instalado: %s", exc)
            return False

        port = self.cfg.get("obd", {}).get("port", "/dev/rfcomm0")
        baud = int(self.cfg.get("obd", {}).get("baudrate", 38400))
        timeout = float(self.cfg.get("obd", {}).get("timeout_s", 1.5))
        log.info("Conectando ELM327 em %s (baud %s)", port, baud)
        try:
            self._conn = obd.OBD(portstr=port, baudrate=baud, timeout=timeout, fast=False)
        except Exception as exc:
            log.error("Falha ao abrir OBD: %s", exc)
            self._connected = False
            return False

        self._connected = bool(self._conn and self._conn.is_connected())
        self.store.set_meta("vehicle_connected", self._connected)
        self.store.set_meta("source", self.name)
        if self._connected:
            log.info("ELM327 conectado. Protocolo: %s", self._conn.protocol_name())
        else:
            log.warning("ELM327 não conectou (pareamento / /dev/rfcomm0?).")
        return self._connected

    def disconnect(self) -> None:
        try:
            if self._conn:
                self._conn.close()
        except Exception:
            pass
        self._connected = False
        self.store.set_meta("vehicle_connected", False)

    @property
    def connected(self) -> bool:
        return bool(self._connected and self._conn and self._conn.is_connected())

    def discover(self) -> set[int]:
        supported: set[int] = set()
        if not self.connected:
            self.supported_pids = supported
            self.after_discover()
            return supported

        # 1) tenta a lista que o python-OBD já descobriu
        try:
            for cmd in self._conn.supported_commands:
                pid = getattr(cmd, "pid", None)
                mode = getattr(cmd, "mode", None)
                if pid is not None and mode in (1, 0x01):
                    supported.add(int(pid))
        except Exception as exc:
            log.warning("supported_commands falhou: %s", exc)

        # 2) consulta explícita dos bitmasks 00/20/40/60
        for base in SUPPORT_PIDS:
            raw = self._query_raw(base)
            if raw and len(raw) >= 4:
                supported |= parse_support_bitmask(base, raw)
                supported.add(base)

        self.supported_pids = supported
        self.after_discover()
        log.info("PIDs suportados (%d): %s", len(supported), sorted(supported))
        return supported

    def _query_raw(self, pid: int) -> list[int] | None:
        """Envia 01 PID e devolve os bytes de dados (sem modo/pid)."""
        if not self.connected:
            return None
        try:
            resp = self._conn.query_string(f"01{pid:02X}") if hasattr(self._conn, "query_string") else None
            if resp:
                return None
        except Exception:
            pass
        # Caminho padrão: comando conhecido ou mensagem crua.
        cmd = self._command(pid)
        if cmd is None:
            return self._query_msg(pid)
        try:
            r = self._conn.query(cmd, force=True)
        except Exception as exc:
            log.debug("query pid %02X: %s", pid, exc)
            return None
        if r is None or r.is_null():
            return None
        try:
            messages = getattr(r, "messages", None) or []
            if messages and getattr(messages[0], "data", None) is not None:
                data = list(messages[0].data)
                # data pode incluir modo+pid
                if len(data) >= 2 and data[0] in (0x41, 0x01):
                    return data[2:]
                return data
        except Exception:
            return None
        return None

    def _query_msg(self, pid: int) -> list[int] | None:
        try:
            import obd
            from obd.protocols.protocol import Message

            raw = self._conn.interface.send_and_parse(f"01{pid:02X}")
            if not raw:
                return None
        except Exception:
            return None
        return None

    def _command(self, pid: int):
        if pid in self._cmd_cache:
            return self._cmd_cache[pid]
        try:
            import obd

            found = None
            for cmd in obd.commands.modes[1]:
                if int(getattr(cmd, "pid", -1) or -1) == pid:
                    found = cmd
                    break
            self._cmd_cache[pid] = found
            return found
        except Exception:
            self._cmd_cache[pid] = None
            return None

    def read_pid(self, pid: int) -> float | None:
        if not self.connected:
            return None
        cmd = self._command(pid)
        delay = float(self.cfg.get("obd", {}).get("fast_delay_s", 0.05))
        try:
            if cmd is not None:
                r = self._conn.query(cmd, force=True)
                if r is not None and not r.is_null() and r.value is not None:
                    val = r.value
                    # python-OBD devolve pint Quantities
                    magnitude = getattr(val, "magnitude", val)
                    try:
                        return float(magnitude)
                    except (TypeError, ValueError):
                        pass
                # fallback: decodifica bytes
            from ..signals import decode_mode01

            raw = self._query_raw(pid)
            if raw:
                return decode_mode01(pid, raw)
        except Exception as exc:
            log.debug("read_pid %02X falhou: %s", pid, exc)
        finally:
            if delay:
                time.sleep(delay)
        return None

    def read_battery_voltage(self) -> float | None:
        if not self.connected:
            return None
        try:
            import obd

            if hasattr(obd.commands, "ELM_VOLTAGE"):
                r = self._conn.query(obd.commands.ELM_VOLTAGE)
                if r is not None and not r.is_null() and r.value is not None:
                    return float(getattr(r.value, "magnitude", r.value))
        except Exception as exc:
            log.debug("ATRV falhou: %s", exc)
        # fallback: PID 0x42
        return self.read_pid(0x42)

    def read_dtcs(self) -> list[dict[str, Any]]:
        if not self.connected:
            return []
        out: list[dict[str, Any]] = []
        mil = False
        try:
            import obd

            if hasattr(obd.commands, "GET_DTC"):
                r = self._conn.query(obd.commands.GET_DTC)
                if r is not None and not r.is_null() and r.value:
                    for item in r.value:
                        # típico: (code, description)
                        if isinstance(item, (list, tuple)) and item:
                            code = str(item[0])
                            desc = str(item[1]) if len(item) > 1 else DTC_HINTS.get(code, "")
                        else:
                            code = str(item)
                            desc = DTC_HINTS.get(code, "")
                        out.append({"code": code, "status": "stored", "description": desc})
            if hasattr(obd.commands, "STATUS"):
                st = self._conn.query(obd.commands.STATUS)
                if st is not None and not st.is_null() and st.value is not None:
                    mil = bool(getattr(st.value, "MIL", False) or getattr(st.value, "mil", False))
        except Exception as exc:
            log.warning("leitura de DTCs falhou: %s", exc)
        self.store.set_meta("dtcs", out)
        self.store.set_meta("mil", mil or bool(out))
        return out

    def clear_dtcs(self) -> bool:
        if not self.connected:
            return False
        try:
            import obd

            self._conn.query(obd.commands.CLEAR_DTC)
            self.store.set_meta("dtcs", [])
            self.store.set_meta("mil", False)
            return True
        except Exception as exc:
            log.error("falha ao limpar DTCs: %s", exc)
            return False

    def read_cvt_temp(self) -> float | None:
        """Tenta Mode 22 na TCM trocando o header do ELM (ATSH). Experimental."""
        if not cvt_uds.is_enabled(self.cfg) or not self.connected:
            return None
        p = cvt_uds.params(self.cfg)
        iface = getattr(self._conn, "interface", None)
        if iface is None or not hasattr(iface, "send_and_parse"):
            log.debug("ELM sem send_and_parse; Mode 22 indisponível")
            return None
        req_h = f"{p['request_id']:03X}"
        resp_h = f"{p['response_id']:03X}"
        did = p["did"]
        cmd = f"22{did:04X}"
        try:
            try:
                iface.send_and_parse(f"ATSH {req_h}")
            except Exception as exc:
                log.debug("ATSH %s falhou: %s", req_h, exc)
                return None
            try:
                iface.send_and_parse(f"ATCRA {resp_h}")
            except Exception:
                pass
            raw = iface.send_and_parse(cmd)
            payload: list[int] = []
            messages = raw if isinstance(raw, list) else ([raw] if raw else [])
            for msg in messages:
                data = getattr(msg, "data", None)
                if data is None and isinstance(msg, (bytes, bytearray, list)):
                    data = msg
                if not data:
                    continue
                body = list(data)
                # pode vir com PCI / 62 DID
                if body and body[0] == 0x62 and len(body) >= 3:
                    payload = body[3:]
                    break
                if len(body) >= 4 and body[1] == 0x62:
                    payload = body[4:]
                    break
                # alguns ELM devolvem só os dados
                if len(body) >= 1:
                    payload = body
                    break
            if not payload:
                return None
            temp = cvt_uds.decode_temp(payload, p["decode"])
            if temp is not None:
                self.store.update("cvt_temp", round(temp, 1), "°C", self.name, "Temp. fluido CVT")
            return temp
        except Exception as exc:
            log.debug("Mode 22 ELM falhou: %s", exc)
            return None
        finally:
            try:
                iface.send_and_parse("ATSH 7DF")
            except Exception:
                pass
            try:
                iface.send_and_parse("ATCRA 7E8")
            except Exception:
                pass


    def read_vin(self) -> str | None:
        """Mode 09 PID 02 via python-OBD, com fallback de comando cru 0902."""
        if not self.connected:
            return None
        from ..vin import normalize_vin, parse_mode09_pid02
        # 1) comando oficial do python-OBD
        try:
            import obd
            cmd = getattr(obd.commands, "VIN", None)
            if cmd is not None:
                r = self._conn.query(cmd, force=True)
                if r is not None and not r.is_null() and r.value is not None:
                    val = r.value
                    if hasattr(val, "magnitude"):
                        val = val.magnitude
                    vin = normalize_vin(str(val))
                    if vin:
                        return vin
        except Exception as exc:
            log.debug("VIN python-OBD: %s", exc)
        # 2) bytes crus (clones v2.1 às vezes só respondem assim, ou falham de vez)
        try:
            raw = None
            if hasattr(self._conn, "interface") and hasattr(self._conn.interface, "send_and_parse"):
                raw = self._conn.interface.send_and_parse("0902")
            text = ""
            if raw:
                for msg in raw:
                    data = getattr(msg, "data", None)
                    if data:
                        text += " ".join(f"{b:02X}" for b in data) + " "
                    raw_str = getattr(msg, "raw", None) or getattr(msg, "original", None)
                    if raw_str:
                        text += str(raw_str) + " "
            if text:
                vin = parse_mode09_pid02(text)
                if vin:
                    return vin
        except Exception as exc:
            log.debug("VIN 0902 cru: %s", exc)
        log.info("VIN não lido no ELM327 (comum em clones v2.1 no Mode 09).")
        return None
