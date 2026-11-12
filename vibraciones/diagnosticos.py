"""Diagnostico del SM1281 v1.3.2 (NO una prediccion de falla).

Fuente: estados originales almacenados por Node-RED de DB23 y lecturas espejo DB13.
Valores del bitmask por monitor: bit0=NotValid, bit1=Good, bit2=Warning,
bit3=Alarm. Los indicadores binarios de Node-RED son resumenes, NO sustituyen
los diez estados RAW: algunos espectros pueden ser NotValid.
"""
from __future__ import annotations

import math
from typing import Any

MONITORES = (
    'vrms', 'arms', 'dkw', 'espectro_a', 'espectro_v', 'envolvente',
    'bpfo', 'bpfi', 'ftf', 'bsf',
)
SENSOR_FLAGS = ('tiene_aviso', 'tiene_alarma', 'sensor_conectado',
                'sensor_corto', 'sensor_cable_roto')
ESPEJO = ('vrms_mm_s', 'arms_m_s2', 'dkw', 'peak_m_s2')


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if math.isfinite(n) else None


def _int(value: Any) -> int | None:
    n = _float(value)
    return int(n) if n is not None and n.is_integer() and 0 <= n <= 255 else None


def _bool(value: Any) -> bool | None:
    if value is None:
        return None
    if value in (0, False):
        return False
    if value in (1, True):
        return True
    return None


def monitor_estado(raw: Any) -> dict:
    """No inferir que el monitor 1 (NotValid) este sano."""
    value = _int(raw)
    if value is None:
        return {'raw': raw, 'estado': 'SIN_DATO', 'valido': False,
                'aviso': None, 'alarma': None}
    if value & 1 or not value & 14:
        return {'raw': value, 'estado': 'NO_VALIDO', 'valido': False,
                'aviso': None, 'alarma': None}
    alarm, warning = bool(value & 8), bool(value & 4)
    return {'raw': value,
            'estado': 'ALARMA' if alarm else 'AVISO' if warning else 'BUENO',
            'valido': True, 'aviso': warning, 'alarma': alarm}


def resumen_monitores(row: dict, sensor: int) -> dict:
    monitors = {k: monitor_estado(row.get(f's{sensor}_sm1281_mon_{k}_bits'))
                for k in MONITORES}
    valid = [m for m in monitors.values() if m['valido']]
    aviso = (any(m['aviso'] for m in valid) if valid else None)
    alarma = (any(m['alarma'] for m in valid) if valid else None)
    return {
        'valido_total': len(valid),
        'no_validos': sum(m['estado'] == 'NO_VALIDO' for m in monitors.values()),
        'sin_dato': sum(m['estado'] == 'SIN_DATO' for m in monitors.values()),
        'diagnostico_parcial': len(valid) != len(MONITORES),
        'tiene_aviso_calculado': aviso, 'tiene_alarma_calculada': alarma,
        'monitores': monitors,
    }


def espejo_db13(row: dict, sensor: int, *, rtol: float = .10,
                 atol: float = .05) -> dict:
    """DB13 copia del mismo valor, no sensor ni feature independiente.

    Debido al desfase entre lecturas no interpretamos una discrepancia como falla.
    """
    resultados = {}
    diferencias = []
    medidos = 0
    for name in ESPEJO:
        a = _float(row.get(f's{sensor}_{name}'))
        b = _float(row.get(f'db13_s{sensor}_{name}'))
        comparable = a is not None and b is not None
        different = comparable and abs(a - b) > max(atol, rtol * max(abs(a), abs(b)))
        if comparable:
            medidos += 1
        if different:
            diferencias.append(name)
        resultados[name] = {
            'db23': a, 'db13': b, 'diferencia_absoluta': round(abs(a-b), 6) if comparable else None,
            'coincide_aproximadamente': None if not comparable else not different,
        }
    estado = 'SIN_DATOS_COMPARABLES' if medidos == 0 else (
        'DIFERENCIA_DETECTADA' if diferencias else 'COINCIDENTE_APROXIMADO')
    return {'estado': estado, 'campos_comparados': medidos,
            'campos_diferentes': diferencias, 'valores': resultados,
            'nota': 'DB13 es un espejo; una diferencia puede ser desfase de captura.'}


def sensor_quality(row: dict, sensor: int) -> dict:
    """Bloqueos de CALIDAD DE INSTRUMENTACION, no alarma mecanica DKW."""
    prefix = f's{sensor}_sm1281_'
    flags = {k: _bool(row.get(prefix + k)) for k in SENSOR_FLAGS}
    rawstate = _int(row.get(prefix + 'sensorstate_bits'))
    rawfault = _int(row.get(prefix + 'faulttype_bits'))
    # Priorizar estados RAW cuando existan; las banderas SQL viejas pudieron
    # ser NULL por el bug v1.3.1. Su ausencia no equivale a sensor averiado.
    connected = (bool(rawstate & 2) if rawstate is not None and not rawstate & 1
                 else flags['sensor_conectado'])
    short = (bool(rawfault & 2) if rawfault is not None and rawfault & 7
             else flags['sensor_corto'])
    broken = (bool(rawfault & 4) if rawfault is not None and rawfault & 7
              else flags['sensor_cable_roto'])
    reasons = []
    if connected is False:
        reasons.append('SENSOR_DESCONECTADO_REPORTADO')
    if short is True:
        reasons.append('CORTOCIRCUITO_REPORTADO')
    if broken is True:
        reasons.append('CABLE_ROTO_REPORTADO')
    for qc in ('qc_vrms', 'qc_arms', 'qc_dkw'):
        val = _int(row.get(f's{sensor}_{qc}'))
        if val == 0:
            reasons.append('CALIDAD_' + qc.upper() + '_CERO')
    return {'apto_para_modelo': not reasons,
            'bloqueos': reasons,
            'sensor_conectado': connected,
            'sensor_corto': short, 'sensor_cable_roto': broken,
            'flags_guardados': flags}


def diagnostic_summary(row: dict, *, rtol: float = .10, atol: float = .05,
                       include_raw: bool = True) -> dict:
    sensors = {}
    alertas = []
    quality_issues = []
    partial = []
    for i in (1, 2, 3):
        res = resumen_monitores(row, i)
        quality = sensor_quality(row, i)
        mirror = espejo_db13(row, i, rtol=rtol, atol=atol)
        saved_alarm = _bool(row.get(f's{i}_sm1281_tiene_alarma'))
        saved_warn = _bool(row.get(f's{i}_sm1281_tiene_aviso'))
        discrepancias_flags = []
        for label, actual, expected in (
            ('alarma', saved_alarm, res['tiene_alarma_calculada']),
            ('aviso', saved_warn, res['tiene_aviso_calculado']),
        ):
            if actual is not None and expected is not None and actual != expected:
                discrepancias_flags.append(label)
        level = ('FALLA_DE_INSTRUMENTACION' if not quality['apto_para_modelo'] else
                 'ALARMA_PLC' if res['tiene_alarma_calculada'] else
                 'AVISO_PLC' if res['tiene_aviso_calculado'] else
                 'SIN_MONITORES_VALIDOS' if res['valido_total'] == 0 else
                 'SIN_ALERTA_EN_MONITORES_VALIDOS')
        if res['diagnostico_parcial']:
            partial.append(i)
        if not quality['apto_para_modelo']:
            quality_issues.append(i)
        if level in ('ALARMA_PLC', 'AVISO_PLC'):
            alertas.append({'sensor': i, 'nivel': level})
        sensors[f'sensor_{i}'] = {
            'estado': level,
            'alerta_plc_almacenada': saved_alarm,
            'aviso_plc_almacenado': saved_warn,
            'discrepancias_flags': discrepancias_flags,
            'monitores_validos': res['valido_total'],
            'monitores_no_validos': res['no_validos'],
            'monitores_sin_dato': res['sin_dato'],
            'diagnostico_parcial': res['diagnostico_parcial'],
            'calidad_instrumentacion': quality,
            'espejo_db13': mirror,
            **({'monitores': res['monitores']} if include_raw else {}),
        }
    return {
        'fuente': 'SM1281_DB23_y_espejo_DB13',
        'sensores': sensors,
        'sensores_con_alerta': alertas,
        'sensores_con_calidad_invalida': quality_issues,
        'sensores_con_diagnostico_parcial': partial,
        'datos_electrometericos_no_interpretados': True,
        'advertencia': 'Las alarmas PLC no son probabilidades ni prueba de causa de falla.',
    }


def quality_gate(row: dict) -> tuple[bool, list[str]]:
    """NUNCA bloquear solo por alarma DKW: no es un defecto del sensor."""
    reasons = []
    for i in (1, 2, 3):
        quality = sensor_quality(row, i)
        reasons.extend(f'S{i}_{r}' for r in quality['bloqueos'])
    return not reasons, reasons
