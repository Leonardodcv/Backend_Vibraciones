"""v1.3: indice de anomalia POR REGIMEN de velocidad, con referencia de reposo opcional.

El eje por defecto usa la FRECUENCIA DE SALIDA ELECTRICA DEL VFD como proxy;
no se presenta como una medicion de vueltas por segundo de la barra. No se
extrapola un modelo de 20Hz a una velocidad nueva. No predice falla ni RUL.
"""
from __future__ import annotations

import json
import math
import os
import secrets
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from django.conf import settings
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

from . import operacion, diagnosticos

APP_VERSION = '1.3.0'
MODEL_NAME = 'IsolationForest3S_Regimenes_SM1281'
RAW_REQUIRED = tuple(
    f's{i}_{s}' for i in (1, 2, 3)
    for s in ('vrms_mm_s', 'arms_m_s2', 'peak_m_s2', 'dkw')
)
CORE_FEATURES = (
    *RAW_REQUIRED,
    's1_factor_cresta', 's2_factor_cresta', 's3_factor_cresta',
    'vrms_diff_1_2', 'vrms_diff_1_3', 'vrms_diff_2_3',
    'vrms_diff_rel_1_2', 'vrms_diff_rel_1_3', 'vrms_diff_rel_2_3',
)
FEATURES = CORE_FEATURES


class InsufficientData(ValueError):
    pass


def _number(value: Any) -> float | None:
    return operacion.num(value)


def rpm_with_source(row: dict) -> tuple[float | None, str | None]:
    sm = _number(row.get('rpm_sm1281'))
    if sm is not None and sm > 0 and _number(row.get('qc_rpm_sm1281')) != 0:
        return sm, 'SM1281'
    vfd = _number(row.get('rpm_vfd'))
    if vfd is not None and vfd > 0:
        return vfd, 'VFD'
    return None, None


def rpm_for(row: dict) -> float | None:
    return rpm_with_source(row)[0]


def _ms(row: dict) -> int:
    return operacion.stamp(row)


def feature_vector(row: dict, features: tuple[str, ...] | None = None) -> tuple[list[float] | None, str | None]:
    """21 atributos de vibracion; sin RPM ni velocidad como feature directa.

    Cada velocidad tiene su propio scaler, bosque y calibracion. Por eso el
    cambio normal de magnitud de vRMS por velocidad no es una falla por si solo.
    """
    values: dict[str, float] = {}
    for name in RAW_REQUIRED:
        val = _number(row.get(name))
        if val is None or val < 0:
            return None, 'sensor_incompleto_o_invalido:' + name
        values[name] = val
    if all(values[f's{i}_vrms_mm_s'] == 0 for i in (1, 2, 3)):
        return None, 'vibracion_tres_sensores_en_cero'
    for i in (1, 2, 3):
        denom = values[f's{i}_arms_m_s2']
        if denom <= 0:
            return None, 'aceleracion_no_positiva:s' + str(i)
        values[f's{i}_factor_cresta'] = values[f's{i}_peak_m_s2'] / denom
    for i, j in ((1, 2), (1, 3), (2, 3)):
        a = values[f's{i}_vrms_mm_s']
        b = values[f's{j}_vrms_mm_s']
        values[f'vrms_diff_{i}_{j}'] = abs(a - b)
        values[f'vrms_diff_rel_{i}_{j}'] = abs(a - b) / max(a + b, 1e-6)
    keys = CORE_FEATURES if features is None else features
    if any(k not in values for k in keys):
        return None, 'feature_desconocida'
    return [float(values[k]) for k in keys], None


def _configured_speed_source() -> str:
    return getattr(settings, 'VIBRATIONS_SPEED_SOURCE', 'vfd_hz').strip().lower()


def _configured_speed_width(source: str) -> float:
    default = 2.0 if source != 'vfd_hz' else 2.0
    value = float(getattr(settings, 'VIBRATIONS_SPEED_BAND_WIDTH', default))
    if not 0.1 <= value <= 60:
        raise ValueError('VIBRATIONS_SPEED_BAND_WIDTH debe ser 0.1..60')
    return value


def _speed(row: dict, fuente: str, eventos: tuple[operacion.Evento, ...]) -> tuple[float | None, str]:
    factor = getattr(settings, 'VIBRATIONS_BAR_RPS_PER_VFD_HZ', None)
    return operacion.velocidad_referencia(
        row, fuente=fuente, eventos=eventos, factor_barras_por_hz=factor,
    )


def _band(speed: float, width: float) -> int:
    return int(math.floor(speed / width + 0.5))


def _calibrate(rows: list[tuple[dict, list[float]]]) -> dict:
    """Holdout cronologico por velocidad; no mezcla niveles para calibrar."""
    n = len(rows)
    count = int(n * .8)
    vectors = np.asarray([vec for _, vec in rows], dtype=np.float64)
    pipeline = Pipeline([
        ('scaler', RobustScaler()),
        ('forest', IsolationForest(n_estimators=150, contamination='auto',
                                   random_state=42, n_jobs=-1)),
    ])
    pipeline.fit(vectors[:count])
    raw = -pipeline.score_samples(vectors[count:])
    q50, q995 = float(np.quantile(raw, .5)), float(np.quantile(raw, .995))
    if q995 - q50 < 1e-7:
        raise InsufficientData('Calibracion sin variabilidad; revisar referencia del regimen')
    return {
        'pipeline': pipeline,
        'q50': q50,
        'q995': q995,
        'filas_entrenamiento': count,
        'filas_calibracion': n - count,
    }


def train_rows(rows: list[dict], *, eventos: tuple[operacion.Evento, ...] = (),
               confirm_normal: bool = False,
               min_samples: int | None = None, min_span_minutes: float | None = None,
               fuente: str | None = None) -> dict:
    """Entrenar solo ventanas verificadas. `confirm_normal` aplica a rango unico.

    Para un manifiesto multisesion, cada fila debe caer en un evento aprobado
    OPERACION_NORMAL_CONFIRMADA / REPOSO_CONFIRMADO; otras se excluyen.
    """
    from collections import Counter, defaultdict
    source = fuente or _configured_speed_source()
    width = _configured_speed_width(source)
    minimum = int(min_samples if min_samples is not None else settings.VIBRATIONS_MIN_TRAIN_SAMPLES)
    minutes = float(min_span_minutes if min_span_minutes is not None else settings.VIBRATIONS_MIN_TRAIN_MINUTES)
    if minimum < 30 or minutes < 1:
        raise ValueError('Minimos de entrenamiento no plausibles')
    if not confirm_normal and not eventos:
        raise InsufficientData('Se requiere rango normal confirmado o eventos aprobados en CSV')
    if source == 'barra_rps' and not eventos and not all('barra_rps' in r for r in rows):
        raise InsufficientData('La tabla SQL no tiene barra_rps; usar CSV de eventos con barra_rps')

    policy = getattr(settings, 'VIBRATIONS_TRAIN_SM1281_ALERT_POLICY', 'annotate')
    if policy not in ('annotate', 'exclude_alarm', 'exclude_warning_alarm'):
        raise ValueError('VIBRATIONS_TRAIN_SM1281_ALERT_POLICY invalida')
    strict_mirror = bool(getattr(settings, 'VIBRATIONS_DB13_STRICT', False))
    valid_marcha: list[tuple[dict, list[float], float]] = []
    rest_rows: list[dict] = []
    skipped_states: dict[str, int] = defaultdict(int)
    plc_alerts_in_training = {'alarma': 0, 'aviso': 0, 'monitores_parciales': 0}
    prev = None
    for row in sorted(rows, key=lambda r: (_ms(r), int(r.get('id') or 0))):
        event = operacion.evento_de(row, eventos)
        if eventos and (event is None or not event.normal_confirmado):
            skipped_states['sin_etiqueta_normal_confirmada'] += 1
            prev = row
            continue
        state = operacion.estado_operativo(row, previous=prev, eventos=eventos)['estado']
        prev = row
        # Solo fallas de instrumentacion verificables bloquean el entrenamiento.
        # Una alarma DKW puede venir de un umbral configurado por automatizacion:
        # por defecto NO es una etiqueta de falla fisica ni feature de ML.
        apt, blocks = diagnosticos.quality_gate(row)
        if not apt:
            skipped_states['CALIDAD_INSTRUMENTACION_INVALIDA'] += 1
            continue
        if strict_mirror and any(
            diagnosticos.espejo_db13(
                row, i, rtol=getattr(settings, 'VIBRATIONS_DB13_REL_TOL', .10),
                atol=getattr(settings, 'VIBRATIONS_DB13_ABS_TOL', .05),
            )['estado'] == 'DIFERENCIA_DETECTADA'
            for i in (1, 2, 3)
        ):
            skipped_states['DIFERENCIA_DB23_DB13'] += 1
            continue
        mon_summaries = [diagnosticos.resumen_monitores(row, i) for i in (1, 2, 3)]
        has_alarm = any(m['tiene_alarma_calculada'] for m in mon_summaries)
        has_warn = any(m['tiene_aviso_calculado'] for m in mon_summaries)
        if has_alarm:
            plc_alerts_in_training['alarma'] += 1
        if has_warn:
            plc_alerts_in_training['aviso'] += 1
        if any(m['diagnostico_parcial'] for m in mon_summaries):
            plc_alerts_in_training['monitores_parciales'] += 1
        if (policy == 'exclude_alarm' and has_alarm) or (
            policy == 'exclude_warning_alarm' and (has_alarm or has_warn)
        ):
            skipped_states['EXCLUIDO_POR_POLITICA_ALERTAS_PLC'] += 1
            continue
        if event and event.estado_real == 'REPOSO_CONFIRMADO':
            if state == 'ENERGIZADO_EN_REPOSO':
                rest_rows.append(row)
            else:
                skipped_states['reposo_no_coincide_telemetria'] += 1
            continue
        if event and event.estado_real != 'OPERACION_NORMAL_CONFIRMADA':
            skipped_states['estado_no_entrenable'] += 1
            continue
        if state != 'EN_MARCHA_ESTABLE':
            skipped_states[state] += 1
            continue
        if row.get('modo_captura') in ('REPOSO', 'POST_PARO'):
            skipped_states['modo_captura_no_apto'] += 1
            continue
        speed, origin = _speed(row, source, eventos)
        if speed is None or speed <= 0:
            skipped_states['velocidad_no_disponible'] += 1
            continue
        if source == 'barra_rps' and event is None and 'barra_rps' not in row:
            skipped_states['barra_rps_sin_etiqueta'] += 1
            continue
        vec, reason = feature_vector(row)
        if vec is None:
            skipped_states[reason or 'sensor_invalido'] += 1
            continue
        valid_marcha.append((row, vec, speed))

    # Centros aprendidos de plateaus reales: evita que 5 Hz caiga en dos
    # bandas por efecto del redondeo 4.99/5.01. No extrapola entre centros.
    bins = {}
    ignored = []
    remaining = list(valid_marcha)
    band_index = 0
    while remaining:
        counts = Counter(round(v, 1) for _, _, v in remaining)
        center_candidate, _ = counts.most_common(1)[0]
        group = [r for r in remaining if abs(r[2] - center_candidate) <= width / 2]
        # Corregir centro con mediana del grupo y reagrupar una vez.
        refined = float(np.median([r[2] for r in group]))
        group = [r for r in remaining if abs(r[2] - refined) <= width / 2]
        remaining = [r for r in remaining if abs(r[2] - refined) > width / 2]
        band_index += 1
        key = band_index
        rows_group = sorted(group, key=lambda rv: (_ms(rv[0]), int(rv[0].get('id') or 0)))
        if len(rows_group) < minimum:
            ignored.append({'centro': round(refined, 3), 'motivo': 'filas_insuficientes',
                            'filas': len(rows_group)})
            continue
        minute_count = len({_ms(row) // 60000 for row, _, _ in rows_group})
        span = (_ms(rows_group[-1][0]) - _ms(rows_group[0][0])) / 60000
        if minute_count < math.ceil(minutes) or span < minutes:
            ignored.append({'centro': round(refined, 3), 'motivo': 'cobertura_insuficiente',
                            'minutos_distintos': minute_count, 'filas': len(rows_group)})
            continue
        try:
            learned = _calibrate([(r, v) for r, v, _ in rows_group])
        except InsufficientData as exc:
            ignored.append({'centro': round(refined, 3), 'motivo': str(exc),
                            'filas': len(rows_group)})
            continue
        speeds = np.asarray([sp for _, _, sp in rows_group], dtype=float)
        learned.update({
            'centro': round(float(np.median(speeds)), 5),
            'filas_validas': len(rows_group),
            'min': round(float(speeds.min()), 5),
            'max': round(float(speeds.max()), 5),
            'mediana': round(float(np.median(speeds)), 5),
            'minutos_distintos': minute_count,
        })
        bins[key] = learned

    if not bins:
        raise InsufficientData(
            'No hay ningun regimen apto. Necesitas >=%s lecturas y >=%s minutos de '
            'funcionamiento normal ESTABLE por velocidad; datos disponibles: %s'
            % (minimum, minutes, ignored[:8])
        )

    # Referencia de vibracion residual en reposo: solo si hay evento de reposo
    # explicitamente aprobado; nunca usar cero como indice de salud de marcha.
    rest = None
    if rest_rows:
        minutes_rest = len({_ms(r) // 60000 for r in rest_rows})
        good = []
        for row in rest_rows:
            measurements = [_number(row.get(f's{i}_vrms_mm_s')) for i in (1, 2, 3)]
            if all(v is not None and v >= 0 for v in measurements):
                good.append(sum(measurements))
        if len(good) >= minimum and minutes_rest >= math.ceil(minutes):
            values = np.asarray(good, dtype=float)
            med = float(np.median(values))
            p995 = float(np.quantile(values, .995))
            # Piso instrumental conservador para no marcar como fallo ruido de cero.
            boundary = max(p995 * 3, med * 5, 0.05)
            rest = {'filas': len(good), 'minutos_distintos': minutes_rest,
                    'mediana_vrms_sum_mm_s': med, 'p995_vrms_sum_mm_s': p995,
                    'umbral_vrms_sum_mm_s': boundary}

    ts = datetime.now(timezone.utc)
    version = f'v{APP_VERSION}-{ts.strftime("%Y%m%dT%H%M%SZ")}-{secrets.token_hex(3)}'
    metadata = {
        'algoritmo': MODEL_NAME,
        'version': version,
        'version_backend': APP_VERSION,
        'fecha_entrenamiento_utc': ts.isoformat(),
        'fuente_velocidad': source,
        'unidad_eje_velocidad': 'Hz electricos VFD (proxy)' if source == 'vfd_hz' else 'vueltas/s barra',
        'ancho_banda_velocidad': width,
        'n_regimenes': len(bins),
        'multivelocidad_validada': len(bins) >= 2,
        'regimenes': [
            {'banda': key, **{k: v for k, v in value.items() if k not in ('pipeline', 'q50', 'q995')}}
            for key, value in bins.items()
        ],
        'bandas_descartadas': ignored,
        'filas_evaluadas': len(rows),
        'filas_validas': sum(b['filas_validas'] for b in bins.values()),
        'exclusiones': dict(skipped_states),
        'referencia_reposo_entrenada': rest is not None,
        'referencia_reposo': rest,
        'sensores_requeridos': 3,
        'features': list(CORE_FEATURES),
        'politica_alertas_sm1281': policy,
        'alarmas_plc_en_ventanas_aprobadas': plc_alerts_in_training,
        'alarmas_sm1281_son_features_modelo': False,
        'db13_espejo_son_features_modelo': False,
        'filtro_calidad_instrumentacion': True,
        'db13_modo_estricto': strict_mirror,
        'medidor_jaritza_en_modelo': False,
        'advertencia': 'Indice condicionado a velocidad. No es probabilidad de falla ni vida util restante.',
    }
    return {'metadata': metadata, 'bins': bins, 'rest': rest,
            'features': CORE_FEATURES, 'speed_source': source, 'width': width}


def bundle_path() -> Path:
    return Path(settings.VIBRATIONS_MODEL_DIR) / 'modelo_vibraciones_v1_3_sm1281_regimenes.joblib'


def save_bundle(bundle: dict, path: Path | None = None) -> Path:
    path = path or bundle_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp-' + secrets.token_hex(5))
    try:
        joblib.dump(bundle, tmp)
        if os.name == 'posix':
            tmp.chmod(0o600)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    _cached_load.cache_clear()
    return path


@lru_cache(maxsize=4)
def _cached_load(path: str, modified_ns: int) -> dict:
    bundle = joblib.load(path)
    if tuple(bundle.get('features', ())) != CORE_FEATURES:
        raise ValueError('Modelo de otra estructura de datos: reentrenar v1.3')
    if bundle.get('metadata', {}).get('version_backend') != APP_VERSION:
        raise ValueError('Modelo incompatible con la version v1.3')
    if bundle.get('speed_source') != _configured_speed_source():
        raise ValueError('La fuente de velocidad del modelo y .env no coinciden')
    return bundle


def load_bundle(path: Path | None = None) -> dict | None:
    path = path or bundle_path()
    if not path.is_file():
        return None
    return _cached_load(str(path), path.stat().st_mtime_ns)


def model_status() -> dict:
    bundle = load_bundle()
    if bundle is None:
        return {
            'estado': 'NO_ENTRENADO', 'version_backend': APP_VERSION,
            'mensaje': 'Entrenar v1.3 con periodos NORMALES por velocidad; modelos anteriores intactos.',
        }
    return {'estado': 'ENTRENADO', **bundle['metadata']}


def score_row(row: dict, bundle: dict | None = None,
              *, previous: dict | None = None,
              eventos: tuple[operacion.Evento, ...] | None = None) -> dict:
    bundle = bundle if bundle is not None else load_bundle()
    events = operacion.eventos_configurados() if eventos is None else eventos
    op = operacion.estado_operativo(row, previous=previous, eventos=events)
    base = {'modelo': MODEL_NAME,
            'version_modelo': bundle['metadata']['version'] if bundle else None,
            'indice_anomalia': None,
            'es_probabilidad_falla': False,
            'sensores_requeridos': 3,
            'estado_operativo': op['estado'],
            'rpm_vfd': op['rpm_vfd'],
            'fuente_rpm': rpm_with_source(row)[1],
            'advertencias_operacion': op['advertencias']}
    diag = diagnosticos.diagnostic_summary(
        row, include_raw=False,
        rtol=getattr(settings, 'VIBRATIONS_DB13_REL_TOL', .10),
        atol=getattr(settings, 'VIBRATIONS_DB13_ABS_TOL', .05),
    )
    base['diagnostico_sm1281'] = {
        'alertas_plc': diag['sensores_con_alerta'],
        'sensores_instrumentacion_no_apta': diag['sensores_con_calidad_invalida'],
        'sensores_diagnostico_parcial': diag['sensores_con_diagnostico_parcial'],
        'espejo_db13': {f's{i}': diag['sensores'][f'sensor_{i}']['espejo_db13']['estado']
                        for i in (1, 2, 3)},
    }
    if bundle is None:
        return {**base, 'estado': 'NO_ENTRENADO'}
    if op['estado'] in ('FALLA_ELECTRICA_CONFIRMADA', 'FALLA_VFD_REPORTADA',
                       'MANTENIMIENTO', 'PRUEBA_CONTROLADA', 'INCONSISTENCIA_ETIQUETA_VELOCIDAD'):
        return {**base, 'estado': op['estado'], 'razon': 'Evento o estado no apto para modelo sano'}
    gate, reasons = diagnosticos.quality_gate(row)
    if not gate:
        return {**base, 'estado': 'CALIDAD_INSTRUMENTACION_INVALIDA',
                'razon': 'Lectura bloqueada por estado de sensores o QC',
                'bloqueos': reasons}
    if getattr(settings, 'VIBRATIONS_DB13_STRICT', False) and any(
        diag['sensores'][f'sensor_{i}']['espejo_db13']['estado'] == 'DIFERENCIA_DETECTADA'
        for i in (1, 2, 3)
    ):
        return {**base, 'estado': 'DIFERENCIA_DB23_DB13',
                'razon': 'Control de consistencia DB13 en modo estricto'}
    if op['estado'] == 'TRANSICION':
        return {**base, 'estado': 'TRANSICION', 'razon': 'No comparar durante aceleracion/desaceleracion'}
    if op['estado'] == 'ENERGIZADO_EN_REPOSO':
        if not bundle.get('rest'):
            return {**base, 'estado': 'ENERGIZADO_EN_REPOSO',
                    'razon': 'Sin referencia de reposo aprobada; no puntuar como falla'}
        v = [_number(row.get(f's{i}_vrms_mm_s')) for i in (1, 2, 3)]
        if any(x is None or x < 0 for x in v):
            return {**base, 'estado': 'SIN_DATOS_REPOSO', 'razon': 'Sensor de reposo incompleto'}
        total = sum(v)
        ref = bundle['rest']
        if total > ref['umbral_vrms_sum_mm_s']:
            return {**base, 'estado': 'VIBRACION_INESPERADA_EN_REPOSO',
                    'razon': 'Supera referencia de vibracion residual en reposo',
                    'vibracion_total_vrms_mm_s': round(total, 5),
                    'umbral_reposo_vrms_mm_s': round(ref['umbral_vrms_sum_mm_s'], 5)}
        return {**base, 'estado': 'REPOSO_DENTRO_DE_REFERENCIA',
                'vibracion_total_vrms_mm_s': round(total, 5),
                'umbral_reposo_vrms_mm_s': round(ref['umbral_vrms_sum_mm_s'], 5)}
    if op['estado'] != 'EN_MARCHA_ESTABLE':
        return {**base, 'estado': op['estado'], 'razon': 'Sin evidencia de marcha estable'}

    speed, origin = _speed(row, bundle['speed_source'], events)
    if speed is None:
        return {**base, 'estado': 'SIN_VELOCIDAD_BARRA' if bundle['speed_source'] == 'barra_rps'
                else 'SIN_VELOCIDAD_REFERENCIA', 'razon': origin}
    nearest = sorted(bundle['bins'].items(), key=lambda kv: abs(kv[1]['centro'] - speed))
    key, regime = nearest[0] if nearest else (None, None)
    if regime is not None and abs(regime['centro'] - speed) > float(bundle['width'])/2:
        regime = None
    info = {'velocidad_referencia': round(speed, 4),
            'fuente_velocidad': origin,
            'unidad_velocidad': bundle['metadata']['unidad_eje_velocidad'],
            'banda': key}
    if regime is None:
        return {**base, **info, 'estado': 'SIN_MODELO_PARA_ESTA_VELOCIDAD',
                'razon': 'No existe referencia normal aprobada a esta velocidad',
                'bandas_disponibles': [b['centro'] for b in bundle['bins'].values()]}
    vec, reason = feature_vector(row, bundle['features'])
    if vec is None:
        return {**base, **info, 'estado': 'SIN_DATOS', 'razon': reason}
    raw = float(-regime['pipeline'].score_samples(np.asarray([vec], dtype=float))[0])
    q50, q995 = regime['q50'], regime['q995']
    estimate = 100 * (raw - q50) / (q995 - q50)
    index = round(float(np.clip(estimate, 0, 100)), 2)
    state = ('ANOMALIA' if index >= settings.VIBRATIONS_SCORE_ALERT
             else 'OBSERVACION' if index >= settings.VIBRATIONS_SCORE_WARNING else 'NORMAL')
    return {**base, **info, 'estado': state, 'indice_anomalia': index,
            'regimen_centro': regime['centro'],
            'regimen_muestras': regime['filas_validas'],
            'sensores': {f'sensor_{i}': {
                'vrms_mm_s': round(float(row[f's{i}_vrms_mm_s']), 4),
                'arms_m_s2': round(float(row[f's{i}_arms_m_s2']), 4)} for i in (1, 2, 3)},
            'nota': 'Comparacion contra referencia de ESTA velocidad, no probabilidad de falla.'}


def details_for_sql(score: dict) -> str:
    detail = {
        'estado': score['estado'],
        'op': score.get('estado_operativo'),
        'version': score.get('version_modelo'),
        'v': score.get('velocidad_referencia'),
        'fuente_v': score.get('fuente_velocidad'),
        'banda': score.get('banda'),
        'plc_alertas': score.get('diagnostico_sm1281', {}).get('alertas_plc', []),
        'sensores_vrms': {k: v.get('vrms_mm_s') for k, v in score.get('sensores', {}).items()},
    }
    encoded = json.dumps(detail, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    if len(encoded) > 1000:
        raise ValueError('Detalle demasiado largo para NVARCHAR(1000)')
    return encoded
