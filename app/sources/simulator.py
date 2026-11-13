"""Simulador do Lancer HL 2016 — permite desenvolver a UI sem o carro."""

from __future__ import annotations

import math
import random
import threading
import time
from typing import Any

from ..store import DataStore
from .base import VehicleSource

# PIDs que um Lancer 2.0 2016 tipicamente expõe via OBD2 genérico.
# (varia por ECU; o modo real descobre na hora).
_LANCER_PIDS = {
    0x01, 0x04, 0x05, 0x06, 0x07, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11,
    0x14, 0x15, 0x1C, 0x1F, 0x21, 0x2F, 0x31, 0x33, 0x42, 0x46, 0x51,
}

# Percurso simulado: volta pela Av. Paulista / região (São Paulo).
# Lista de waypoints (lat, lon) interpolados em runtime.
_WAYPOINTS = [
    (-23.5614, -46.6559),  # Trianon-Masp
    (-23.5650, -46.6505),
    (-23.5681, -46.6460),  # Consolação
    (-23.5710, -46.6418),
    (-23.5735, -46.6390),  # Brigadeiro
    (-23.5702, -46.6448),
    (-23.5662, -46.6498),
    (-23.5620, -46.6548),
]


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _interp_path(t: float) -> tuple[float, float, float]:
    """t em [0, 1) ao longo do anel. Retorna lat, lon, heading graus."""
    n = len(_WAYPOINTS)
    pos = (t % 1.0) * n
    i = int(pos) % n
    j = (i + 1) % n
    frac = pos - int(pos)
    lat1, lon1 = _WAYPOINTS[i]
    lat2, lon2 = _WAYPOINTS[j]
    lat = _lerp(lat1, lat2, frac)
    lon = _lerp(lon1, lon2, frac)
    heading = (math.degrees(math.atan2(lon2 - lon1, lat2 - lat1)) + 360) % 360
    return lat, lon, heading


class SimulatorVehicleSource(VehicleSource):
    name = "simulator"

    def __init__(self, store: DataStore, cfg: dict) -> None:
        super().__init__(store, cfg)
        self._connected = False
        self._t0 = time.time()
        self._values: dict[int, float] = {}
        self._dtcs: list[dict[str, Any]] = []
        self._mil = False
        self._path_t = 0.0
        self._speed = 0.0
        self._rpm = 850.0
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._mode = "urban"
        self._sprint_t = 0.0
        self._crank_t: float | None = 0.0  # queda de tensão na primeira partida
        self._demo_crank = False
        self._coolant = 88.0
        self._cvt_fluid = 88.0
        # Avança o modelo em background para o GPS e as grandezas
        # evoluírem mesmo entre polls do scheduler.

    def start_sprint(self) -> None:
        """Arrancada 0–130 km/h e depois 100–0, para o cronômetro de desempenho."""
        with self._lock:
            self._mode = "sprint"
            self._sprint_t = 0.0
            self._speed = 0.0
            self._rpm = 850.0
            self._demo_crank = False

    def start_ignition(self) -> None:
        """Ignição ligada, motor parado (painel acende, ~12,4 V, RPM 0)."""
        with self._lock:
            self._mode = "ignition"
            self._crank_t = None
            self._demo_crank = True
            self._sprint_t = 0.0
            self._speed = 0.0
            self._rpm = 0.0
            self._coolant = 44.0
            self._cvt_fluid = 36.0

    def start_launch_0_100(self) -> None:
        """Arrancada 0–100 km/h em ~9,5–10 s, RPM da CVT no patamar, e segura em 100."""
        with self._lock:
            self._mode = "launch"
            self._sprint_t = 0.0
            self._speed = 0.0
            self._demo_crank = False

    def start_crank(self) -> None:
        """Simula a queda de tensão da partida."""
        with self._lock:
            self._crank_t = 0.0
            self._rpm = 0.0
            self._speed = 0.0
            if self._mode == "ignition":
                self._mode = "idle"
                self._demo_crank = True

    @property
    def poll_budget_per_s(self) -> float:
        return 40.0

    def connect(self) -> bool:
        self._connected = True
        self._t0 = time.time()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="sim-physics", daemon=True)
        self._thread.start()
        self.store.set_meta("vehicle_connected", True)
        self.store.set_meta("gps_connected", True)
        self.store.set_meta("source", self.name)
        return True

    def disconnect(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._connected = False
        self.store.set_meta("vehicle_connected", False)

    @property
    def connected(self) -> bool:
        return self._connected

    def discover(self) -> set[int]:
        self.supported_pids = set(_LANCER_PIDS)
        # inclui os PIDs de suporte para parecer uma descoberta real
        self.supported_pids.update({0x00, 0x20, 0x40})
        self.after_discover()
        return self.supported_pids

    def _run(self) -> None:
        last = time.time()
        while not self._stop.wait(0.05):
            now = time.time()
            dt = min(now - last, 0.2)
            last = now
            self._step(dt, now)

    def _step(self, dt: float, now: float) -> None:
        elapsed = now - self._t0
        # Partida: RPM sai do zero e a tensão cai (~10.8 V) por ~0.6 s.
        # No modo demo (ignição → partida) o pico vai a ~1200 e o lento a ~750.
        demo = self._demo_crank or self._mode in {"ignition", "idle", "launch"}
        crank_window = 1.6 if demo else 1.4
        cranking = self._crank_t is not None and self._crank_t < crank_window
        if cranking:
            self._crank_t += dt
            ct = self._crank_t
            target_speed = 0.0
            self._speed = 0.0
            throttle = 5.0
            load = 25.0
            if demo:
                if ct < 0.22:
                    self._rpm = 0.0
                elif ct < 0.55:
                    self._rpm = 180 + (ct - 0.22) / 0.33 * 400
                elif ct < 0.95:
                    self._rpm = 580 + (ct - 0.55) / 0.40 * 620  # sobe até ~1200
                elif ct < 1.55:
                    self._rpm = 1200 - (ct - 0.95) / 0.60 * 450  # assenta em ~750
                else:
                    self._rpm = 750 + random.uniform(-20, 20)
                    self._crank_t = None
                    if self._mode == "ignition":
                        self._mode = "idle"
            else:
                if ct < 0.25:
                    self._rpm = 0.0
                elif ct < 0.7:
                    self._rpm = (ct - 0.25) / 0.45 * 900
                else:
                    self._rpm = 850 + random.uniform(-20, 20)
        elif self._mode == "ignition":
            target_speed = 0.0
            self._speed = 0.0
            self._rpm = 0.0
            throttle = 0.0
            load = 4.0
        elif self._mode == "idle":
            target_speed = 0.0
            self._speed = 0.0
            self._rpm = 750 + random.uniform(-18, 18)
            throttle = 0.0
            load = 18 + random.uniform(-2, 2)
        elif self._mode == "launch":
            self._sprint_t += dt
            t = self._sprint_t
            # ~9,6 s de 0 a 100, depois segura ~102 km/h.
            launch_s = 9.6
            if t < launch_s:
                # curva levemente côncava (mais puxada no começo, típico de CVT)
                u = t / launch_s
                target_speed = 100.0 * (1.0 - (1.0 - u) ** 1.12)
                # integração contínua: acompanha o alvo
                self._speed = max(0.0, target_speed)
                plateau = 5200.0 + min(300.0, t * 40.0)  # 5200 → ~5500
                if t < 0.45:
                    self._rpm = 750 + (plateau - 750) * (t / 0.45)
                else:
                    self._rpm = plateau + random.uniform(-50, 50)
                throttle = 92 + random.uniform(-3, 3)
                load = 88 + random.uniform(-3, 3)
            else:
                # Segura exatamente 100 km/h para o 0–100 encerrar limpo
                # (80–120 / 402 m não devem continuar RUNNING no HUD).
                target_speed = 100.0
                self._speed = 100.0
                self._rpm = 2200 + random.uniform(-40, 40)
                throttle = 22 + random.uniform(-3, 3)
                load = 28 + random.uniform(-3, 3)
        elif self._mode == "sprint":
            self._sprint_t += dt
            t = self._sprint_t
            # 0–2 s parado (arma o cronômetro), 2–13 s arranca até 130,
            # 13–15 s mantém, 15–19 s freia 100–0, depois volta ao urbano.
            if t < 2.0:
                target_speed = 0.0
                accel = 30.0
            elif t < 13.0:
                target_speed = 130.0
                accel = 9.26  # ~10.8 s de 0 a 100 (a partir de t=2)
            elif t < 15.0:
                target_speed = 128.0
                accel = 8.0
            elif t < 19.2:
                target_speed = 0.0
                accel = 29.2  # ~3.4 s de 100 a 0
            else:
                self._mode = "urban"
                target_speed = 0.0
                accel = 20.0
            if abs(target_speed - self._speed) < abs(accel) * dt:
                self._speed = max(0.0, target_speed)
            else:
                self._speed += math.copysign(abs(accel) * dt, target_speed - self._speed)
                self._speed = max(0.0, self._speed)
        else:
            # Perfil de condução urbana: acelera, cruza, para no sinal, etc.
            cycle = 90.0  # segundos por "volta" de comportamento
            phase = (elapsed % cycle) / cycle

            if phase < 0.12:
                target_speed = 0.0  # parado no sinal
            elif phase < 0.35:
                target_speed = 48.0
            elif phase < 0.50:
                target_speed = 62.0
            elif phase < 0.58:
                target_speed = 20.0  # desacelera
            elif phase < 0.80:
                target_speed = 55.0
            else:
                target_speed = 0.0

            # inércia simples
            accel = 18.0 if target_speed > self._speed else -22.0  # km/h por s
            if abs(target_speed - self._speed) < abs(accel) * dt:
                self._speed = target_speed
            else:
                self._speed += math.copysign(abs(accel) * dt, target_speed - self._speed)
            self._speed = max(0.0, self._speed)

        # Transmissão: CVT Jatco (padrão) ou manual 5 marchas.
        # Nos modos demo (ignição/lento/arrancada) RPM e carga já foram definidos.
        from ..derived import transmission_mode
        trans = transmission_mode(self.cfg)
        if self._mode in {"ignition", "idle", "launch"} or (demo and cranking):
            pass
        elif cranking:
            throttle, load = 5.0, 25.0
        elif trans != "manual":
            throttle, load = self._step_cvt(dt, target_speed)
        elif self._speed < 1:
            self._rpm = 850 + random.uniform(-20, 20)
            throttle = 0.0
            load = 18 + random.uniform(-3, 3)
        else:
            if self._speed < 20:
                gear = 1
            elif self._speed < 35:
                gear = 2
            elif self._speed < 50:
                gear = 3
            elif self._speed < 70:
                gear = 4
            else:
                gear = 5
            ratios = {1: 3.538, 2: 1.913, 3: 1.218, 4: 0.888, 5: 0.687}
            speed_ms = self._speed / 3.6
            self._rpm = (speed_ms / 2.025) * 60 * ratios[gear] * 4.235
            self._rpm = max(850, min(6500, self._rpm + random.uniform(-40, 40)))
            throttle = 8 if target_speed <= self._speed else min(75, 20 + (target_speed - self._speed) * 3)
            load = 20 + throttle * 0.7 + random.uniform(-2, 2)

        if demo:
            # Motor frio na ignição, sobe devagar com o motor ligado.
            if self._mode == "ignition" and not cranking:
                self._coolant = min(48.0, self._coolant + 0.05 * dt)
                self._cvt_fluid = min(42.0, self._cvt_fluid + 0.04 * dt)
            else:
                rise = 0.55 if cranking or self._mode == "idle" else 0.9
                self._coolant = min(92.0, self._coolant + rise * dt)
                self._cvt_fluid = min(110.0, self._cvt_fluid + (0.4 + load * 0.012) * dt)
            coolant = self._coolant + random.uniform(-0.15, 0.15)
        else:
            coolant = 88 + 6 * math.sin(elapsed / 40.0) + (4 if self._speed > 40 else 0)
            self._coolant = coolant
        intake = 28 + 8 * (self._speed / 80.0) + random.uniform(-0.5, 0.5)
        ambient = 24 + 2 * math.sin(elapsed / 120.0)
        maf = 3.5 + (self._rpm / 1000.0) * 4.2 * (0.4 + load / 100.0)
        map_kpa = 30 + load * 0.7 + random.uniform(-1, 1)
        if cranking:
            # curva típica: 12.4 em repouso → ~10.8 no pico do arranque → 13.9 / 14.2 no demo
            ct = self._crank_t or 0.0
            if demo:
                if ct < 0.18:
                    voltage = 12.4
                elif ct < 0.55:
                    voltage = 10.8 + 0.12 * random.uniform(-1, 1)
                elif ct < 1.15:
                    voltage = 11.4 + (ct - 0.55) / 0.60 * 2.8  # sobe a ~14.2
                else:
                    voltage = 14.2 + random.uniform(-0.05, 0.05)
            else:
                if ct < 0.15:
                    voltage = 12.4
                elif ct < 0.55:
                    voltage = 10.8 + 0.15 * random.uniform(-1, 1)
                elif ct < 1.1:
                    voltage = 12.2 + (ct - 0.55) / 0.55 * 1.6
                else:
                    voltage = 13.8
                    self._crank_t = None
        elif self._mode == "ignition":
            voltage = 12.4 + random.uniform(-0.04, 0.04)
        elif demo:
            voltage = 14.2 + 0.06 * math.sin(elapsed / 5.0) + random.uniform(-0.03, 0.03)
        else:
            voltage = 13.9 + 0.15 * math.sin(elapsed / 8.0) + random.uniform(-0.03, 0.03)
            if self._speed < 1 and throttle < 1:
                voltage = 13.7 + random.uniform(-0.05, 0.08)

        stft = 2.0 * math.sin(elapsed / 3.0) + random.uniform(-0.4, 0.4)
        ltft = 1.5 + 0.3 * math.sin(elapsed / 30.0)
        timing = 8 + (self._rpm / 1000.0) * 3 + random.uniform(-0.5, 0.5)
        o2_1 = 0.1 + 0.7 * (0.5 + 0.5 * math.sin(elapsed * 2.5))  # oscila rico/pobre
        o2_2 = 0.45 + 0.05 * math.sin(elapsed / 2.0)  # pós-cat mais estável
        fuel_level = max(12.0, 62.0 - elapsed / 3600.0 * 8)
        # Fluido da CVT: sobe com carga e velocidade, mais inerte que o motor.
        if demo:
            cvt_temp = max(20.0, min(130.0, self._cvt_fluid))
        else:
            cvt_temp = 88 + 10 * (load / 100.0) + 0.08 * self._speed + 3 * math.sin(elapsed / 50.0)
            cvt_temp = max(70.0, min(130.0, cvt_temp))
        runtime = elapsed
        baro = 101.0
        throttle = max(0.0, min(100.0, throttle + random.uniform(-0.5, 0.5)))

        # GPS: avança conforme a velocidade ao longo do anel (~4 km)
        # distância da volta aproximada
        loop_km = 3.6
        if self._speed > 0:
            self._path_t = (self._path_t + (self._speed * dt / 3600.0) / loop_km) % 1.0
        lat, lon, heading = _interp_path(self._path_t)
        # ruído de GPS de alguns metros
        lat += random.uniform(-0.00001, 0.00001)
        lon += random.uniform(-0.00001, 0.00001)
        sats = 10 + int(2 * math.sin(elapsed / 15.0))
        alt = 780 + 8 * math.sin(self._path_t * 2 * math.pi)

        with self._lock:
            self._values = {
                0x04: max(0, min(100, load)),
                0x05: coolant,
                0x06: stft,
                0x07: ltft,
                0x0B: map_kpa,
                0x0C: self._rpm,
                0x0D: self._speed,
                0x0E: timing,
                0x0F: intake,
                0x10: maf,
                0x11: throttle,
                0x14: o2_1,
                0x15: o2_2,
                0x1F: runtime,
                0x21: 0,
                0x2F: fuel_level,
                0x31: 124,
                0x33: baro,
                0x42: voltage,
                0x46: ambient,
                0x51: 16,  # híbrido mistura / flex aproximado
            }
            self._voltage = voltage
            self._cvt_temp = cvt_temp
            self._gps = (lat, lon, heading, alt, sats, self._speed)

        # publica GPS direto no store (o simulador é também fonte GPS)
        self.store.update("gps_lat", round(lat, 7), "°", "simulator", "Latitude")
        self.store.update("gps_lon", round(lon, 7), "°", "simulator", "Longitude")
        self.store.update("gps_heading", round(heading, 1), "°", "simulator", "Rumo")
        self.store.update("gps_alt", round(alt, 1), "m", "simulator", "Altitude")
        self.store.update("gps_sats", sats, "", "simulator", "Satélites")
        self.store.update("gps_speed", round(self._speed, 1), "km/h", "simulator", "Velocidade GPS")
        self.store.update("gps_fix", 3, "", "simulator", "Fix GPS")
        self.store.update("cvt_temp", round(cvt_temp, 1), "°C", "simulator", "Temp. fluido CVT")
        # O agendador só lê 1 PID médio por ciclo (acelerador/carga entram no rodízio).
        # No simulador publicamos os instrumentos direto, no ritmo da física.
        self.store.update("rpm", round(self._rpm, 0), "rpm", "simulator", "RPM")
        self.store.update("speed", round(self._speed, 1), "km/h", "simulator", "Velocidade")
        self.store.update("throttle", round(throttle, 1), "%", "simulator", "Posição do acelerador")
        self.store.update("engine_load", round(max(0.0, min(100.0, load)), 1), "%", "simulator", "Carga do motor")
        self.store.update("coolant_temp", round(coolant, 1), "°C", "simulator", "Temperatura do motor")
        self.store.update("battery_voltage", round(voltage, 2), "V", "simulator", "Tensão da bateria")
        decelerating = target_speed < self._speed - 2.0
        accelerating = target_speed > self._speed + 2.0
        if demo:
            brake = 0.0
            turn_left = 0.0
            turn_right = 0.0
        else:
            brake = 1.0 if decelerating or (self._speed < 1 and target_speed <= 0) else 0.0
            # seta: ocasional em baixa velocidade (só simulador — o OBD em geral não traz isso)
            phase_i = int(elapsed / 4)
            turn_left = 1.0 if self._speed < 12 and (phase_i % 9) == 2 else 0.0
            turn_right = 1.0 if self._speed < 12 and (phase_i % 9) == 6 else 0.0
        self.store.update("brake", brake, "", "simulator", "Freio")
        self.store.update("turn_left", turn_left, "", "simulator", "Seta esquerda")
        self.store.update("turn_right", turn_right, "", "simulator", "Seta direita")
        self.store.update("headlights", 1, "", "simulator", "Faróis")
        self.store.update("accel_state", 1 if accelerating else (-1 if decelerating else 0), "", "simulator", "Aceleração")
        # Telltales do HUD — o simulador aciona todos (fonte lights=sim).
        ign = self._mode == "ignition" and not (self._demo_crank or (self._crank_t is not None and self._crank_t < 1.6))
        running = (self._rpm or 0) > 400
        # farol baixo e lanterna ligados com a ignição; alto só em modo noturno simulado
        self.store.update("low_beam", 1, "", "simulator", "Farol baixo")
        self.store.update("high_beam", 0, "", "simulator", "Farol alto")
        self.store.update("parking_lights", 1, "", "simulator", "Lanterna")
        # freio de mão puxado com o motor desligado; cinto solto só na ignição
        self.store.update("parking_brake", 1.0 if ign or (not running and self._speed < 1) else 0.0, "", "simulator", "Freio de mão")
        self.store.update("door_open", 0, "", "simulator", "Porta aberta")
        self.store.update("seatbelt", 1.0 if ign else 0.0, "", "simulator", "Cinto")
        self.store.update("check_engine", 1.0 if self._mil else 0.0, "", "simulator", "Check engine")
        mode = "SPORT" if self._mode == "launch" else "NORMAL"
        self.store.update("drive_mode", mode, "", "simulator", "Modo de condução")

        # setas: no demo piscam ~2,4 s após a partida (antes da arrancada)
        if demo:
            if self._mode == "idle" and running:
                # 1 Hz, só nos primeiros ~2,2 s de lento (depois da partida)
                blink_on = (int(elapsed * 2) % 2 == 0)
                # usa o tempo de lenta: após o crank o elapsed continua
                show = True
                # durante a arrancada as setas apagam
                self.store.update("turn_left", 1.0 if blink_on else 0.0, "", "simulator", "Seta esquerda")
                self.store.update("turn_right", 0, "", "simulator", "Seta direita")
            elif self._mode == "launch":
                self.store.update("turn_left", 0, "", "simulator", "Seta esquerda")
                self.store.update("turn_right", 0, "", "simulator", "Seta direita")
            else:
                self.store.update("turn_left", 0, "", "simulator", "Seta esquerda")
                self.store.update("turn_right", 0, "", "simulator", "Seta direita")

    def read_vin(self) -> str | None:
        # VIN sintético de um Lancer 2016 2.0 CVT brasileiro (dígito verificador válido).
        if not hasattr(self, "_vin"):
            from ..vin import build_vin
            self._vin = build_vin("93Y", "AA26C", 2016, "C", "123456")
        return self._vin

    def read_pid(self, pid: int) -> float | None:
        if pid in (0x00, 0x20, 0x40, 0x60):
            # bitmask sintético — não usado no display
            return 0
        with self._lock:
            value = self._values.get(pid)
        return None if value is None else float(value)

    def read_battery_voltage(self) -> float | None:
        with self._lock:
            return getattr(self, "_voltage", 13.8)

    def read_dtcs(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._dtcs)

    def clear_dtcs(self) -> bool:
        with self._lock:
            self._dtcs.clear()
            self._mil = False
        self.store.set_meta("dtcs", [])
        self.store.set_meta("mil", False)
        return True


    def _step_cvt(self, dt: float, target_speed: float) -> tuple[float, float]:
        """Efeito 'elástico' da CVT: o RPM sobe e segura enquanto a velocidade sobe."""
        if not hasattr(self, "_rpm_hold"):
            self._rpm_hold = 850.0
        accelerating = target_speed > self._speed + 2.0
        decelerating = target_speed < self._speed - 2.0
        if self._speed < 1 and not accelerating:
            self._rpm_hold = 850.0
            self._rpm = 850 + random.uniform(-20, 20)
            throttle = 0.0
            load = 18 + random.uniform(-3, 3)
            return throttle, load
        if accelerating:
            # quanto maior a diferença de velocidade, mais alto o patamar de RPM
            demand = min(1.0, (target_speed - self._speed) / 25.0 + 0.35)
            throttle = min(85.0, 25 + demand * 70)
            plateau = 2000 + demand * 2800  # ~2000–4800
            # RPM corre rápido até o patamar e segura
            rate = 4200.0  # rpm/s de subida
            if self._rpm < plateau:
                self._rpm = min(plateau, self._rpm + rate * dt)
            else:
                self._rpm = plateau + random.uniform(-40, 40)
            self._rpm_hold = plateau
        elif decelerating:
            throttle = 4.0
            # relação alonga, RPM cai em direção a um litoral/idle proporcional à velocidade
            coast = max(850.0, 900.0 + self._speed * 14.0)
            self._rpm += (coast - self._rpm) * min(1.0, dt * 2.2)
            self._rpm_hold = coast
        else:
            # cruzeiro: RPM baixo e estável, relação longa
            throttle = 12.0 + self._speed * 0.08
            cruise = 1300.0 + self._speed * 12.0  # 48 km/h ≈ 1876 rpm
            self._rpm += (cruise - self._rpm) * min(1.0, dt * 1.2)
            self._rpm_hold = cruise
        self._rpm = max(850.0, min(6500.0, self._rpm + random.uniform(-15, 15)))
        load = 18 + throttle * 0.7 + random.uniform(-2, 2)
        return throttle, max(0.0, min(100.0, load))

    def read_cvt_temp(self) -> float | None:
        with self._lock:
            return getattr(self, "_cvt_temp", None)

    def inject_dtc(self, code: str = "P0420", desc: str = "Eficiência do catalisador abaixo do limiar (Banca 1)") -> None:
        with self._lock:
            self._dtcs.append({"code": code, "status": "stored", "description": desc})
            self._mil = True
        self.store.set_meta("dtcs", list(self._dtcs))
        self.store.set_meta("mil", True)


class SimulatorGpsSource:
    """No modo simulador o GPS já é emitido por SimulatorVehicleSource."""

    name = "simulator-gps"

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    @property
    def connected(self) -> bool:
        return True
