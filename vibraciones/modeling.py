"""Modelo v1.1: IsolationForest con TRES sensores y contexto VFD opcional.

No estima probabilidad de averia ni vida util restante. No usa campos
Jaritza hasta validar escalamiento, unidades y calibracion en planta.
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

from .fields import VFD_CONTEXT_CANDIDATES

APP_VERSION = '1.1.0'
MODEL_NAME = 'IsolationForest3S'
RAW_REQUIRED = tuple(
    f's{i}_{suffix}'
    for i in (1, 2, 3)
    for suffix in ('vrms_mm_s', 'arms_m_s2', 'peak_m_s2', 'dkw')
)

CORE_FEATURES = (
    'rpm',
    *RAW_REQUIRED,
    's1_factor_cresta', 's2_factor_cresta', 's3_factor_cresta',
    'vrms_diff_1_2', 'vrms_diff_1_3', 'vrms_diff_2_3',
    'vrms_diff_rel_1_2', 'vrms_diff_rel_1_3', 'vrms_diff_rel_2_3',
)
# Compatibilidad del codigo cliente que consulte FEATURES.
FEATURES = CORE_FEATURES


class InsufficientData(ValueError):
    """Condiciones o periodo de referencia insuficientes para el modelo."""


def _number(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        n = float(v)
    except (ValueError, TypeError, OverflowError):
        return None
    return n if math.isfinite(n) else None


def rpm_with_source(row: dict) -> tuple[float | None, str | None]:
    sm = _number(row.get('rpm_sm1281'))
    if sm is not None and sm > 0:
        return sm, 'SM1281'
    vfd = _number(row.get('rpm_vfd'))
    if vfd is not None and vfd > 0:
        return vfd, 'VFD'
    return None, None


def rpm_for(row: dict) -> float | None:
    return rpm_with_source(row)[0]


def _computed_features(row: dict) -> tuple[dict[str, float] | None, str | None]:
    rpm = rpm_for(row)
    if rpm is None or rpm < settings.VIBRATIONS_MIN_RPM:
        return None, 'sin_rpm_de_marcha'
    if rpm > 15000:
        return None, 'rpm_no_plausible'
    if row.get('modo_captura') in ('REPOSO', 'POST_PARO') or row.get('motor_activo') in (0, False):
        return None, 'motor_no_estable'

    values: dict[str, float] = {'rpm': rpm}
    for field in RAW_REQUIRED:
        v = _number(row.get(field))
        if v is None or v < 0:
            return None, 'sensor_incompleto_o_invalido:' + field
        values[field] = v

    if all(values[f's{i}_vrms_mm_s'] == 0 for i in (1, 2, 3)):
        return None, 'vibracion_tres_sensores_en_cero'
    for i in (1, 2, 3):
        if values[f's{i}_arms_m_s2'] <= 0:
            return None, f'aceleracion_no_positiva:s{i}'
        values[f's{i}_factor_cresta'] = (
            values[f's{i}_peak_m_s2'] / values[f's{i}_arms_m_s2']
        )
    for i, j in ((1, 2), (1, 3), (2, 3)):
        a = values[f's{i}_vrms_mm_s']
        b = values[f's{j}_vrms_mm_s']
        values[f'vrms_diff_{i}_{j}'] = abs(a - b)
        values[f'vrms_diff_rel_{i}_{j}'] = abs(a - b) / max(a + b, 1e-6)
    return values, None


def feature_vector(row: dict, features: tuple[str, ...] | None = None) -> tuple[list[float] | None, str | None]:
    """Calcular caracteristicas sin rellenar silenciosamente sensores faltantes."""
    wanted = CORE_FEATURES if features is None else features
    values, reason = _computed_features(row)
    if values is None:
        return None, reason
    for field in wanted:
        if field in values:
            continue
        if field not in VFD_CONTEXT_CANDIDATES:
            return None, 'caracteristica_desconocida:' + field
        v = _number(row.get(field))
        if v is None or v <= 0:
            return None, 'contexto_vfd_incompleto:' + field
        values[field] = v
    return [float(values[f]) for f in wanted], None


def _ms(row: dict) -> int:
    try:
        return int(row['captura_unix_ms'])
    except (TypeError, ValueError, KeyError, OverflowError):
        return 0


def _select_context(rows: list[dict]) -> tuple[str, ...]:
    if not getattr(settings, 'VIBRATIONS_USE_VFD_CONTEXT', True):
        return ()
    selected = []
    for name in VFD_CONTEXT_CANDIDATES:
        numbers = [_number(row.get(name)) for row in rows]
        # Ningun caso de imputacion: contexto ausente o 0 no se usa para ML.
        if not numbers or any(v is None or v <= 0 for v in numbers):
            continue
        values = np.asarray(numbers, dtype=np.float64)
        med = float(np.median(values))
        spread = float(np.quantile(values, .95) - np.quantile(values, .05))
        # Evitar incorporar indicadores practicamente constantes o solo ruido
        # de cuantizacion; la validacion de unidades sigue siendo obligatoria.
        if spread / max(abs(med), 1.0) >= 0.01:
            selected.append(name)
    return tuple(selected)


def train_rows(rows: list[dict], *, min_samples: int | None = None,
               min_span_minutes: float | None = None) -> dict:
    min_samples = settings.VIBRATIONS_MIN_TRAIN_SAMPLES if min_samples is None else min_samples
    min_span_minutes = (settings.VIBRATIONS_MIN_TRAIN_MINUTES
                        if min_span_minutes is None else min_span_minutes)
    valid: list[dict] = []
    for row in sorted(rows, key=lambda r: (_ms(r), int(r.get('id', 0)))):
        vec, _ = feature_vector(row)
        if vec is not None and _ms(row) > 0:
            valid.append(row)
    if len(valid) < min_samples:
        raise InsufficientData(
            f'Solo {len(valid)} lecturas completas de 3 sensores; se requieren {min_samples}. '
            'No mezclar periodos anteriores a la instalacion del canal 3.'
        )
    span_minutes = (_ms(valid[-1]) - _ms(valid[0])) / 60000
    if span_minutes < min_span_minutes:
        raise InsufficientData(
            f'Cobertura {span_minutes:.1f} min; se requieren {min_span_minutes} min.'
        )
    train_size = int(len(valid) * .8)
    if train_size < 20 or len(valid) - train_size < 10:
        raise InsufficientData('No hay suficientes filas para la particion temporal 80/20.')

    # Seleccionar contexto usando el 80% ANTERIOR: no mirar al futuro.
    extras = _select_context(valid[:train_size])
    # Solo emplear atributos presentes en el conjunto completo de referencia;
    # si uno falta en el 20% final, se elimina sin imputacion.
    extras = tuple(name for name in extras if all(
        _number(row.get(name)) is not None and _number(row.get(name)) > 0
        for row in valid[train_size:]
    ))
    selected = CORE_FEATURES + extras
    vectors = np.asarray([feature_vector(row, selected)[0] for row in valid], dtype=np.float64)
    pipeline = Pipeline([
        ('scaler', RobustScaler()),
        ('forest', IsolationForest(n_estimators=200, contamination='auto',
                                   random_state=42, n_jobs=-1)),
    ])
    pipeline.fit(vectors[:train_size])
    raw = -pipeline.score_samples(vectors[train_size:])
    q50, q995 = float(np.quantile(raw, .5)), float(np.quantile(raw, .995))
    if q995 - q50 < 1e-6:
        raise InsufficientData('La referencia no presenta variabilidad suficiente para calibrar.')
    speed = vectors[:train_size, 0]
    rpm_low = float(np.quantile(speed, .01))
    rpm_high = float(np.quantile(speed, .99))
    timestamp = datetime.now(timezone.utc)
    version = f'v{APP_VERSION}-{timestamp.strftime("%Y%m%dT%H%M%SZ")}-{secrets.token_hex(3)}'
    metadata = {
        'algoritmo': MODEL_NAME,
        'version': version,
        'version_backend': APP_VERSION,
        'fecha_entrenamiento_utc': timestamp.isoformat(),
        'filas_validas': len(valid),
        'filas_descartadas': len(rows) - len(valid),
        'filas_entrenamiento': train_size,
        'filas_calibracion': len(valid) - train_size,
        'desde_unix_ms': _ms(valid[0]),
        'hasta_unix_ms': _ms(valid[-1]),
        'duracion_minutos': round(span_minutes, 2),
        'rpm_entrenamiento_p01': round(rpm_low, 2),
        'rpm_entrenamiento_p99': round(rpm_high, 2),
        'sensores_requeridos': 3,
        'features': list(selected),
        'features_vfd_activas': list(extras),
        'medidor_jaritza_en_modelo': False,
        'calibracion': {'percentil50': q50, 'percentil99_5': q995},
        'advertencia': 'Indice relativo de anomalia. No equivale a probabilidad de falla.',
    }
    return {
        'pipeline': pipeline,
        'metadata': metadata,
        'q50': q50, 'q995': q995,
        'rpm_low': rpm_low, 'rpm_high': rpm_high,
        'features': selected,
    }


def bundle_path() -> Path:
    return Path(settings.VIBRATIONS_MODEL_DIR) / 'modelo_vibraciones_v1_1.joblib'


def save_bundle(bundle: dict, path: Path | None = None) -> Path:
    """Guardar archivo local atomicamente; NO aceptar joblib de usuarios."""
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
    # joblib utiliza pickle, se carga solo un artefacto creado localmente.
    bundle = joblib.load(path)
    selected = tuple(bundle.get('features', ()))
    if selected[:len(CORE_FEATURES)] != CORE_FEATURES or any(
        f not in VFD_CONTEXT_CANDIDATES for f in selected[len(CORE_FEATURES):]
    ):
        raise ValueError('Esquema de caracteristicas incompatible con version 1.1')
    if bundle.get('metadata', {}).get('version_backend') != APP_VERSION:
        raise ValueError('Modelo de otra version: reentrenar v1.1')
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
            'estado': 'NO_ENTRENADO',
            'version_backend': APP_VERSION,
            'mensaje': 'Entrenar v1.1 con un periodo normal de 3 sensores (train_vibration_model).',
        }
    return {'estado': 'ENTRENADO', **bundle['metadata']}


def score_row(row: dict, bundle: dict | None = None) -> dict:
    bundle = bundle if bundle is not None else load_bundle()
    if bundle is None:
        return {'estado': 'NO_ENTRENADO', 'indice_anomalia': None}
    metadata = bundle['metadata']
    speed, speed_origin = rpm_with_source(row)
    base = {
        'modelo': MODEL_NAME,
        'version_modelo': metadata['version'],
        'indice_anomalia': None,
        'es_probabilidad_falla': False,
        'sensores_requeridos': 3,
        'fuente_rpm': speed_origin,
    }
    vector, reason = feature_vector(row, tuple(bundle['features']))
    if vector is None:
        if row.get('modo_captura') == 'REPOSO' and (speed is None or speed < settings.VIBRATIONS_MIN_RPM):
            return {**base, 'estado': 'REPOSO', 'razon': 'Motor detenido; no se calcula anomalia.'}
        if row.get('modo_captura') == 'POST_PARO':
            return {**base, 'estado': 'TRANSICION', 'razon': 'Post-paro; no es un regimen comparable.'}
        return {**base, 'estado': 'SIN_DATOS', 'razon': reason}
    rpm = vector[0]
    padding = max(100., .10 * float(bundle['rpm_high']))
    if not bundle['rpm_low'] - padding <= rpm <= bundle['rpm_high'] + padding:
        return {**base, 'estado': 'FUERA_RANGO_RPM',
                'razon': 'RPM fuera del regimen usado para entrenar'}

    raw_score = float(-bundle['pipeline'].score_samples(np.asarray([vector], dtype=np.float64))[0])
    estimate = 100 * (raw_score - float(bundle['q50'])) / (float(bundle['q995']) - float(bundle['q50']))
    index = round(float(np.clip(estimate, 0, 100)), 2)
    if index >= settings.VIBRATIONS_SCORE_ALERT:
        state = 'ANOMALIA'
    elif index >= settings.VIBRATIONS_SCORE_WARNING:
        state = 'OBSERVACION'
    else:
        state = 'NORMAL'
    names = bundle['features']
    values = dict(zip(names, vector))
    qc = {
        f's{i}': {k: row.get(f's{i}_qc_{k}') for k in ('vrms', 'arms', 'dkw')}
        for i in (1, 2, 3)
    }
    qc['rpm_sm1281'] = row.get('qc_rpm_sm1281')
    return {
        **base,
        'estado': state,
        'indice_anomalia': index,
        'rpm': round(rpm, 2),
        'sensores': {
            f'sensor_{i}': {
                'vrms_mm_s': round(values[f's{i}_vrms_mm_s'], 4),
                'arms_m_s2': round(values[f's{i}_arms_m_s2'], 4),
                'factor_cresta': round(values[f's{i}_factor_cresta'], 3),
            } for i in (1, 2, 3)
        },
        'diferencias_vrms_mm_s': {
            f'{i}_{j}': round(values[f'vrms_diff_{i}_{j}'], 4)
            for i, j in ((1, 2), (1, 3), (2, 3))
        },
        'caracteristicas_vfd_usadas': metadata.get('features_vfd_activas', []),
        'calidad_sensor': qc,
        'nota_calidad': 'Codigos QC expuestos sin asumir semantica hasta verificar manual SM1281.',
    }


def details_for_sql(score: dict) -> str:
    """Resumen auditado de <=1000 caracteres para NVARCHAR(1000)."""
    detail = {
        'estado': score['estado'],
        'version': score['version_modelo'],
        'rpm': score.get('rpm'),
        'fuente_rpm': score.get('fuente_rpm'),
        'tres_sensores': True,
        'sensores_vrms': {
            k: v.get('vrms_mm_s') for k, v in score.get('sensores', {}).items()
        },
        'vfd_usadas': score.get('caracteristicas_vfd_usadas', []),
    }
    encoded = json.dumps(detail, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    if len(encoded) > 1000:
        raise ValueError('Detalle de puntuacion demasiado largo')
    return encoded
