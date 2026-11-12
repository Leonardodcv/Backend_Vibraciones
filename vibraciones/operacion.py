"""Estados operativos y trazabilidad de la velocidad de la barra.

No confundir Hz de salida electrica del VFD, RPM del motor y vueltas/s de la barra.
La alimentacion del bus DC confirma tension EN EL VARIADOR, no rotacion ni
alimentacion completa de la maquina. Un rele danado exige confirmacion externa.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

ESTADOS_EVENTO = frozenset({
    'REPOSO_CONFIRMADO', 'OPERACION_NORMAL_CONFIRMADA',
    'FALLA_ELECTRICA_CONFIRMADA', 'MANTENIMIENTO', 'PRUEBA_CONTROLADA',
})
ESTADOS_NO_ENTRENABLES = frozenset({
    'FALLA_ELECTRICA_CONFIRMADA', 'MANTENIMIENTO', 'PRUEBA_CONTROLADA',
})


def num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return out if math.isfinite(out) else None


def stamp(row: dict) -> int:
    try:
        return int(row['captura_unix_ms'])
    except (KeyError, TypeError, ValueError, OverflowError):
        return 0


def iso_ms(text: str) -> int:
    """Aceptar SOLO ISO 8601 timezone-aware. CSV usa UTC Z preferiblemente."""
    value = datetime.fromisoformat(text.strip().replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('Todas las fechas CSV deben incluir Z u offset UTC-06:00')
    return int(value.astimezone(timezone.utc).timestamp() * 1000)


@dataclass(frozen=True)
class Evento:
    inicio_ms: int
    fin_ms: int
    estado_real: str
    barra_rps: float | None
    normal_confirmado: bool
    descripcion: str


def leer_eventos(path: str | Path | None) -> tuple[Evento, ...]:
    if not path:
        return ()
    file = Path(path)
    if not file.is_file():
        raise ValueError(f'No existe archivo de eventos: {file}')
    parsed: list[Evento] = []
    with file.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        required = {'inicio_utc', 'fin_utc', 'estado_real', 'barra_rps',
                    'normal_confirmado', 'descripcion'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('CSV de eventos sin columnas requeridas: ' + ', '.join(sorted(required)))
        for index, r in enumerate(reader, start=2):
            if not any(str(v or '').strip() for v in r.values()):
                continue
            try:
                a, b = iso_ms(r['inicio_utc']), iso_ms(r['fin_utc'])
                if not 0 < a < b:
                    raise ValueError('fin debe ser posterior al inicio')
                state = r['estado_real'].strip().upper()
                if state not in ESTADOS_EVENTO:
                    raise ValueError('estado_real desconocido')
                speed = num(r.get('barra_rps'))
                if str(r.get('barra_rps') or '').strip() and speed is None:
                    raise ValueError('barra_rps no numerico')
                if speed is not None and not (0 <= speed <= 300):
                    raise ValueError('barra_rps fuera de rango')
                verified = r['normal_confirmado'].strip().lower()
                if verified not in ('si', 'no'):
                    raise ValueError('normal_confirmado debe ser si/no')
                if state in ESTADOS_NO_ENTRENABLES and verified == 'si':
                    raise ValueError('Una falla/mantenimiento/prueba no es referencia sana')
                parsed.append(Evento(a, b, state, speed, verified == 'si',
                                      (r.get('descripcion') or '')[:240]))
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError(f'Error en eventos CSV, linea {index}: {exc}') from exc
    parsed.sort(key=lambda e: e.inicio_ms)
    for previous, following in zip(parsed, parsed[1:]):
        if following.inicio_ms < previous.fin_ms:
            raise ValueError('Intervalos superpuestos en CSV de eventos')
    return tuple(parsed)


@lru_cache(maxsize=4)
def _cache_eventos(path: str, mtime_ns: int) -> tuple[Evento, ...]:
    return leer_eventos(path)


def eventos_configurados() -> tuple[Evento, ...]:
    from django.conf import settings
    path = getattr(settings, 'VIBRATIONS_EVENTS_CSV', None)
    if not path:
        return ()
    path = Path(path)
    if not path.exists():
        return ()  # El archivo opcional puede no estar configurado todavia.
    return _cache_eventos(str(path), path.stat().st_mtime_ns)


def evento_de(row: dict, eventos: tuple[Evento, ...] = ()) -> Evento | None:
    ms = stamp(row)
    # Se toleran 30 intervalos; detener en el primero (sin superposiciones).
    for event in eventos:
        if event.inicio_ms <= ms < event.fin_ms:
            return event
    return None


def velocidad_referencia(row: dict, *, fuente: str = 'vfd_hz',
                          eventos: tuple[Evento, ...] = (),
                          factor_barras_por_hz: float | None = None) -> tuple[float | None, str]:
    """La referencia vfd_hz es un PROXY ELECTRICO, no velocidad mecanica de barra."""
    hz = num(row.get('vfd_frecuencia_salida_hz'))
    if fuente == 'vfd_hz':
        return (hz if hz is not None and hz >= 0 else None), 'VFD_HZ_PROXY'
    if fuente == 'barra_rps':
        speed = num(row.get('barra_rps'))
        if speed is not None and speed >= 0:
            return speed, 'BARRA_RPS_MEDIDA'
        evento = evento_de(row, eventos)
        if evento is not None and evento.barra_rps is not None:
            return evento.barra_rps, 'BARRA_RPS_ETIQUETADA'
        return None, 'BARRA_RPS_NO_REGISTRADA'
    if fuente == 'barra_rps_calibrada':
        if factor_barras_por_hz is None or not math.isfinite(factor_barras_por_hz) or factor_barras_por_hz <= 0:
            return None, 'FACTOR_CALIBRACION_NO_CONFIGURADO'
        return ((hz * factor_barras_por_hz) if hz is not None and hz >= 0 else None), 'BARRA_RPS_ESTIMADA_DE_VFD'
    raise ValueError('Fuente de velocidad debe ser vfd_hz, barra_rps o barra_rps_calibrada')


def estado_operativo(row: dict, previous: dict | None = None, *,
                      eventos: tuple[Evento, ...] = (),
                      dc_min_v: float = 100.0,
                      hz_movimiento: float = 0.5,
                      rpm_movimiento: float = 20.0,
                      delta_hz_transicion: float = 1.0) -> dict:
    event = evento_de(row, eventos)
    ms = stamp(row)
    hz, rpm = num(row.get('vfd_frecuencia_salida_hz')), num(row.get('rpm_vfd'))
    bus = num(row.get('vfd_voltaje_bus_dc_v'))
    fault = num(row.get('vfd_fault'))
    orden = row.get('orden_marcha_vfd')
    raw_mode = (row.get('modo_captura') or '').strip().upper()
    detalle_node_red = (row.get('estado_operativo_detalle') or '').strip().upper()
    warnings: list[str] = []
    if rpm is not None and rpm == 0 and num(row.get('rpm_sm1281')) in (0, None):
        warnings.append('RPM_SM1281_NO_DISPONIBLE_COMO_REFERENCIA')
    if orden in (1, True) and (rpm == 0 and hz == 0):
        warnings.append('ORDEN_MARCHA_SIN_MOVIMIENTO_MEDIDO')
    if raw_mode == 'ACTIVO' and rpm == 0 and hz == 0:
        warnings.append('CAPTURA_ACTIVA_NO_SIGNIFICA_GIRO')
    if event and event.estado_real in ('FALLA_ELECTRICA_CONFIRMADA', 'MANTENIMIENTO', 'PRUEBA_CONTROLADA'):
        state = event.estado_real
    elif fault is not None and fault != 0:
        state = 'FALLA_VFD_REPORTADA'
    elif rpm is None and hz is None:
        state = 'SIN_TELEMETRIA_VELOCIDAD'
    else:
        moving = (rpm is not None and rpm > rpm_movimiento) or (hz is not None and hz > hz_movimiento)
        if raw_mode == 'POST_PARO' or detalle_node_red in (
            'CAMBIO_VELOCIDAD', 'GIRO_ESTABILIZANDO', 'POST_PARO'
        ):
            state = 'TRANSICION'
        elif moving:
            state = 'EN_MARCHA_ESTABLE'
            if previous is not None:
                before = stamp(previous)
                prev_hz, prev_rpm = num(previous.get('vfd_frecuencia_salida_hz')), num(previous.get('rpm_vfd'))
                if before > 0 and ms > before and ms - before <= 30000:
                    if (prev_hz is not None and hz is not None and abs(hz - prev_hz) >= delta_hz_transicion) or (
                            prev_rpm is not None and rpm is not None and abs(rpm - prev_rpm) >= 35):
                        state = 'TRANSICION'
        elif orden in (1, True):
            state = 'ORDEN_MARCHA_SIN_GIRO'
        elif bus is not None and bus >= dc_min_v:
            state = 'ENERGIZADO_EN_REPOSO'
        else:
            state = 'SIN_GIRO_ENERGIA_NO_CONFIRMADA'
    if event and event.estado_real == 'REPOSO_CONFIRMADO' and state == 'EN_MARCHA_ESTABLE':
        state = 'INCONSISTENCIA_ETIQUETA_VELOCIDAD'
    return {
        'estado': state,
        'rotacion_vfd_detectada': (rpm is not None and rpm > rpm_movimiento) or
                                  (hz is not None and hz > hz_movimiento),
        'bus_dc_v': bus,
        'voltaje_bus_indica_variante_energizado': (bus is not None and bus >= dc_min_v),
        'rpm_vfd': rpm,
        'hz_vfd': hz,
        'modo_captura_original': raw_mode,
        'estado_reportado_node_red': detalle_node_red or None,
        'etiqueta_operador': event.estado_real if event else None,
        'velocidad_barra_rps_etiquetada': event.barra_rps if event else None,
        'advertencias': warnings,
        'nota': 'Estado operativo inferido; el bus DC no confirma alimentacion de toda la maquina.',
    }


def estados_serie(rows: list[dict], eventos: tuple[Evento, ...] = ()) -> list[dict]:
    ordered = sorted(rows, key=lambda r: (stamp(r), int(r.get('id') or 0)))
    out, last = [], None
    for row in ordered:
        out.append(estado_operativo(row, previous=last, eventos=eventos))
        last = row
    return out
