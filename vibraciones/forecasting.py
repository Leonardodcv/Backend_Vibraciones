"""Proyeccion experimental de vRMS para tres canales. NO predice fallas."""
from __future__ import annotations

from collections import defaultdict
from statistics import median

import numpy as np
from django.conf import settings
from scipy.stats import theilslopes

from .modeling import _number, rpm_for


def forecast_vrms(rows: list[dict], horizon_minutes: int = 30) -> dict:
    """Theil-Sen sobre medianas por minuto en regimen estable, 3 sensores."""
    if not 5 <= horizon_minutes <= 60:
        raise ValueError('horizon_minutes debe estar entre 5 y 60')
    grouped: dict[int, list[tuple[float, float, float, float]]] = defaultdict(list)
    count_missing_sensor_3 = 0
    for row in rows:
        if row.get('modo_captura') in ('REPOSO', 'POST_PARO'):
            continue
        speed = rpm_for(row)
        if speed is None or speed < settings.VIBRATIONS_MIN_RPM:
            continue
        levels = [_number(row.get(f's{i}_vrms_mm_s')) for i in (1, 2, 3)]
        if levels[2] is None:
            count_missing_sensor_3 += 1
        if any(x is None or x < 0 for x in levels) or sum(levels) == 0:
            continue
        try:
            minute = int(row['captura_unix_ms']) // 60000
        except (KeyError, TypeError, ValueError):
            continue
        grouped[minute].append((speed, *levels))

    if len(grouped) < 12:
        return {
            'disponible': False,
            'razon': 'minutos_validos_insuficientes',
            'minutos_validos': len(grouped),
            'filas_sin_sensor_3': count_missing_sensor_3,
            'sensores_requeridos': 3,
            'tiempo_hasta_falla': None,
        }
    minutes = sorted(grouped)
    span = minutes[-1] - minutes[0]
    if span < 20:
        return {'disponible': False, 'razon': 'periodo_menor_a_20_minutos',
                'cobertura_minutos': span, 'tiempo_hasta_falla': None}
    if max(np.diff(minutes)) > 10:
        return {'disponible': False, 'razon': 'huecos_de_datos_mayores_a_10_minutos',
                'tiempo_hasta_falla': None}

    medians = np.array([
        [median(values[i] for values in grouped[m]) for i in range(4)]
        for m in minutes
    ], dtype=float)
    speeds = medians[:, 0]
    cv = float(np.std(speeds) / np.mean(speeds))
    if cv > .10:
        return {'disponible': False, 'razon': 'rpm_variable_no_comparable',
                'cv_rpm': round(cv, 4), 'tiempo_hasta_falla': None}
    x = np.asarray(minutes, dtype=float) - minutes[0]
    sensors: dict[str, dict] = {}
    for i in (1, 2, 3):
        series = medians[:, i]
        slope = float(theilslopes(series, x)[0])
        current = float(median(series[-min(5, len(series)):]))
        projected = max(0., current + horizon_minutes * slope)
        sensors[f'sensor_{i}'] = {
            'vrms_actual_mm_s': round(current, 4),
            'vrms_proyectado_mm_s': round(projected, 4),
            'pendiente_mm_s_por_minuto': round(slope, 6),
            'variacion_proyectada_pct': round(
                100 * (projected - current) / max(current, 1e-6), 2
            ),
        }
    return {
        'disponible': True,
        'metodo': 'extrapolacion_robusta_Theil_Sen',
        'horizonte_minutos': horizon_minutes,
        'minutos_analizados': span,
        'medianas_por_minuto': len(minutes),
        'rpm_media': round(float(np.mean(speeds)), 2),
        'cv_rpm': round(cv, 4),
        'sensores': sensors,
        'tiempo_hasta_falla': None,
        'advertencia': 'Solo tendencia vRMS; no estima una averia ni la vida util restante.',
    }
