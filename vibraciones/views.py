"""API REST de consulta; entrenamiento y scoring solo mediante comandos de Django."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from rest_framework.response import Response
from rest_framework.views import APIView

from . import db, forecasting, modeling, operacion, diagnosticos
from .fields import (COLUMNS_BY_GROUP, NEW_SENSOR_OFFSETS, VFD_CONTEXT_CANDIDATES,
                     NEW_COLUMNS, MODEL_COLUMNS)

logger = logging.getLogger('vibraciones')
MEXICO = ZoneInfo('America/Mexico_City')


def _params(request, values):
    """values: nombre:(predeterminado,minimo,maximo,tipo)."""
    parsed = {}
    for key, (default, low, high, typ) in values.items():
        try:
            val = typ(request.query_params.get(key, default))
            if not math.isfinite(val) or not low <= val <= high:
                raise ValueError(key)
            parsed[key] = val
        except (ValueError, TypeError, OverflowError):
            raise ValueError(f'Parametro {key} debe estar entre {low} y {high}')
    return parsed


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _with_local_dates(row: dict) -> dict:
    """No altera fechas SQL; agrega sus representaciones con offset -06:00."""
    item = dict(row)
    if isinstance(item.get('fecha_registro_utc'), datetime):
        item['fecha_registro_mexico'] = _utc(item['fecha_registro_utc']).astimezone(MEXICO).isoformat()
    if isinstance(item.get('fecha_calculo_utc'), datetime):
        item['fecha_calculo_mexico'] = _utc(item['fecha_calculo_utc']).astimezone(MEXICO).isoformat()
    stamp = item.get('captura_unix_ms')
    try:
        if stamp is not None:
            item['fecha_captura_mexico'] = datetime.fromtimestamp(
                int(stamp) / 1000, tz=timezone.utc
            ).astimezone(MEXICO).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        item['fecha_captura_mexico'] = None
    return item


def _json_safe(obj):
    if isinstance(obj, datetime):
        return _utc(obj).isoformat().replace('+00:00', 'Z')
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _db_unavailable(exc: Exception):
    logger.exception('No se pudo consultar SQL Server: %s', type(exc).__name__)
    return Response({'error': 'sql_no_disponible',
                     'mensaje': 'No se pudo consultar la base de datos.'}, status=503)


def _active_version():
    bundle = modeling.load_bundle()
    return bundle['metadata']['version'] if bundle else None


def _diagnosticos(row: dict, *, include_raw: bool = True) -> dict:
    from django.conf import settings
    return diagnosticos.diagnostic_summary(
        row, include_raw=include_raw,
        rtol=settings.VIBRATIONS_DB13_REL_TOL,
        atol=settings.VIBRATIONS_DB13_ABS_TOL,
    )


def _op_brief(row: dict, previous: dict | None = None, eventos=None) -> dict:
    events = operacion.eventos_configurados() if eventos is None else eventos
    status = operacion.estado_operativo(row, previous=previous, eventos=events)
    fuente = modeling._configured_speed_source()
    speed, origin = modeling._speed(row, fuente, events)
    status['velocidad_referencia'] = round(speed, 4) if speed is not None else None
    status['fuente_velocidad'] = origin
    status['unidad_referencia'] = 'Hz electricos del VFD' if fuente == 'vfd_hz' else 'vueltas/s barra'
    return status


class HealthView(APIView):
    allow_public_health = True

    def get(self, request):
        try:
            ok = db.ping()
        except Exception:
            ok = False
        return Response({'estado': 'ok' if ok else 'degradado',
                         'sql': 'conectado' if ok else 'no_disponible',
                         'version': modeling.APP_VERSION}, status=200 if ok else 503)


class ModelStatusView(APIView):
    def get(self, request):
        try:
            return Response(modeling.model_status())
        except Exception:
            logger.exception('Modelo incompatible o danado')
            return Response({'error': 'modelo_incompatible_o_danado'}, status=503)


class LatestView(APIView):
    def get(self, request):
        try:
            row = db.latest()
        except Exception as exc:
            return _db_unavailable(exc)
        if not row:
            return Response({'estado': 'sin_lecturas', 'lectura': None, 'prediccion': None})
        try:
            score = modeling.score_row(row)
        except Exception:
            logger.exception('No se pudo evaluar el modelo')
            return Response({'error': 'modelo_no_disponible'}, status=503)
        return Response(_json_safe({
            'lectura': _with_local_dates(row),
            'prediccion': score,
            'estado_operativo': _op_brief(row),
            'diagnosticos_sm1281': _diagnosticos(row),
        }))


class HistoryView(APIView):
    def get(self, request):
        try:
            p = _params(request, {'hours': (6, 1, 168, int), 'limit': (2000, 1, 5000, int)})
            version = _active_version()
            rows = db.history_rows(**p, version=version)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        except Exception as exc:
            return _db_unavailable(exc)
        events = operacion.eventos_configurados()
        states = operacion.estados_serie(rows, eventos=events)
        enriched = []
        for row, state in zip(rows, states):
            speed, origin = modeling._speed(row, modeling._configured_speed_source(), events)
            item = _with_local_dates(row)
            item['estado_operativo'] = state['estado']
            item['velocidad_referencia'] = round(speed, 4) if speed is not None else None
            item['fuente_velocidad'] = origin
            # Se incluyen las 193 columnas SQL originales, sin completar NULLs.
            enriched.append(item)
        return Response(_json_safe({**p, 'count': len(rows), 'version_modelo': version,
                                    'timezone_presentacion': 'America/Mexico_City',
                                    'results': enriched}))


class TimelineView(APIView):
    def get(self, request):
        try:
            p = _params(request, {'hours': (6, 1, 168, int),
                                  'interval_minutes': (1, 1, 60, int)})
            if p['interval_minutes'] not in (1, 5, 15, 30, 60):
                raise ValueError('interval_minutes debe ser 1, 5, 15, 30 o 60')
            version = _active_version()
            rows = db.timeline_rows(**p, version=version)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        except Exception as exc:
            return _db_unavailable(exc)
        return Response(_json_safe({**p, 'count': len(rows), 'version_modelo': version,
                                    'timezone_presentacion': 'America/Mexico_City',
                                    'results': [_with_local_dates(row) for row in rows]}))


class AnomaliesView(APIView):
    def get(self, request):
        try:
            p = _params(request, {'hours': (24, 1, 168, int),
                                  'min_score': (60.0, 0., 100., float),
                                  'limit': (200, 1, 1000, int)})
            version = _active_version()
            rows = db.anomalies_rows(**p, version=version)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        except Exception as exc:
            return _db_unavailable(exc)
        return Response(_json_safe({'count': len(rows), 'version_modelo': version,
                                    'results': [_with_local_dates(row) for row in rows]}))


class ForecastView(APIView):
    def get(self, request):
        try:
            p = _params(request, {'window_minutes': (60, 30, 60, int),
                                  'horizon_minutes': (30, 5, 60, int)})
            # Datos limitados para proteger SQL. Ultima hora maximo 3600 muestras a 1s.
            rows = db.history_rows(hours=1, limit=5000)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        except Exception as exc:
            return _db_unavailable(exc)
        if rows:
            # No proyectar cuando el ultimo estado esta en reposo. La proyeccion
            # v1.1 por RPM estable no debe mezclar regímenes de velocidad nuevos.
            last_row = rows[-1]
            current = operacion.estado_operativo(last_row, previous=rows[-2] if len(rows) > 1 else None)
            gate, blocked = diagnosticos.quality_gate(last_row)
            if not gate:
                return Response({'disponible': False, 'razon': 'calidad_instrumentacion_invalida',
                                 'bloqueos': blocked, 'tiempo_hasta_falla': None})
            if current['estado'] != 'EN_MARCHA_ESTABLE':
                return Response({'disponible': False,
                                 'razon': 'ultimo_estado_no_es_marcha_estable',
                                 'estado_operativo': current['estado'],
                                 'tiempo_hasta_falla': None})
            last = max(int(r['captura_unix_ms']) for r in rows)
            cutoff = last - p['window_minutes'] * 60000
            rows = [r for r in rows if int(r['captura_unix_ms']) >= cutoff]
            freq = modeling._number(last_row.get('vfd_frecuencia_salida_hz'))
            if freq is not None:
                # No concatenar periodos separados por un paro o un cambio de banda.
                continuous = []
                for row in reversed(rows):
                    h = modeling._number(row.get('vfd_frecuencia_salida_hz'))
                    if h is None or h <= 0.5 or abs(h - freq) > 1.0 or \
                            not diagnosticos.quality_gate(row)[0]:
                        break
                    continuous.append(row)
                rows = list(reversed(continuous))
        result = forecasting.forecast_vrms(rows, p['horizon_minutes'])
        return Response(_json_safe(result))


class VariablesView(APIView):
    """Diccionario del esquema para el frontend y trazabilidad de TIA."""
    def get(self, request):
        try:
            bundle = modeling.load_bundle()
        except Exception:
            logger.exception('No se pudo cargar el modelo')
            return Response({'error': 'modelo_incompatible_o_danado'}, status=503)
        return Response({
            'tabla': 'MantenimientoPredictivo.dbo.LecturasVibraciones',
            'plc_ip': '192.168.0.5',
            'campos_total': sum(map(len, COLUMNS_BY_GROUP.values())),
            'grupos': {k: list(v) for k, v in COLUMNS_BY_GROUP.items()},
            'offsets_sensores_confirmados': NEW_SENSOR_OFFSETS,
            'contexto_vfd_candidato': list(VFD_CONTEXT_CANDIDATES),
            'campos_nuevos_v1_3': len(NEW_COLUMNS),
            'campos_utilizados_en_lectura_modelo': len(MODEL_COLUMNS),
            'monitores_sm1281_estados_bits': {
                '1': 'NotValid', '2': 'Good', '4': 'Warning', '8': 'Alarm',
                'nota': 'Bits de estado; puede haber combinaciones; bit 0 tiene prioridad.',
            },
            'sm1281_velocidades_raw_sin_escala_confirmada': True,
            'db13_espejo_de_db23_no_sensor_independiente': True,
            'flags_v1_3_2_alertas_entre_monitores_validos': True,
            'alarmas_plc_no_son_etiquetas_de_falla': True,
            'features_modelo_actual': list(bundle['features']) if bundle else None,
            'medidor_en_indice_anomalia': False,
            'vfd_hz_no_es_velocidad_barra_rps': True,
            'modelo_condicionado_por_velocidad': True,
            'fecha_registro_utc': 'UTC; fecha_registro_mexico se anade en API',
        })


class QualityView(APIView):
    def get(self, request):
        try:
            p = _params(request, {'hours': (24, 1, 168, int)})
            result = db.coverage_rows(**p)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        except Exception as exc:
            return _db_unavailable(exc)
        if not result:
            return Response({'hours': p['hours'], 'total': 0, 'cobertura_pct': {}})
        total = int(result['total'] or 0)
        coverage = {
            key: round(100. * int(value or 0) / total, 2) if total else 0.
            for key, value in result.items() if key not in ('total', 'ultima_captura_unix_ms')
        }
        last = result.get('ultima_captura_unix_ms')
        age = (db.now_ms() - int(last)) / 1000 if last is not None else None
        return Response({'hours': p['hours'], 'total': total,
                         'ultima_captura_unix_ms': last,
                         'antiguedad_segundos': round(age, 1) if age is not None else None,
                         'cobertura_pct': coverage,
                         'nota': 'Cobertura no implica que los valores del sensor sean fisicamente validos.'})


class EstadoOperativoView(APIView):
    """Estado inferido de las ultimas lecturas, independiente del modelo ML."""
    def get(self, request):
        try:
            p = _params(request, {'samples': (30, 2, 120, int)})
            rows = db.history_rows(hours=1, limit=p['samples'])
            events = operacion.eventos_configurados()
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        except Exception as exc:
            return _db_unavailable(exc)
        if not rows:
            return Response({'estado': 'SIN_LECTURAS', 'muestras': 0})
        previous = rows[-2] if len(rows) > 1 else None
        state = _op_brief(rows[-1], previous, eventos=events)
        try:
            pred = modeling.score_row(rows[-1], previous=previous, eventos=events)
        except Exception:
            logger.exception('No se pudo puntuar ultima lectura')
            return Response({'error': 'modelo_no_disponible'}, status=503)
        return Response(_json_safe({'muestras': len(rows),
                                    'fecha_captura_mexico': _with_local_dates(rows[-1]).get('fecha_captura_mexico'),
                                    'estado_operativo': state, 'prediccion': pred,
                                    'diagnosticos_sm1281': _diagnosticos(rows[-1], include_raw=False)}))


class RegimenesView(APIView):
    """Estado de aprendizaje por bandas y auditoria SQL de estados observados."""
    def get(self, request):
        try:
            p = _params(request, {'hours': (24, 1, 168, int)})
            model = modeling.model_status()
            summary = db.status_summary(hours=p['hours'])
            events = operacion.eventos_configurados()
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        except Exception as exc:
            return _db_unavailable(exc)
        except Exception:
            logger.exception('Modelo no disponible')
            return Response({'error': 'modelo_no_disponible'}, status=503)
        return Response(_json_safe({
            'version_backend': modeling.APP_VERSION,
            'modelo': model,
            'auditoria_telemetria': summary,
            'horas_auditadas': p['hours'],
            'eventos_operador_cargados': len(events),
            'advertencia': 'Las bandas sin referencia normal confirmada no generan indice; '
                           'la frecuencia electrica VFD no es una medicion fisica de la barra.',
        }))


class DiagnosticosUltimaView(APIView):
    """Evidencia PLC por sensor, banderas corregidas y concordancia DB13."""
    def get(self, request):
        try:
            row = db.latest()
        except Exception as exc:
            return _db_unavailable(exc)
        if row is None:
            return Response({'estado': 'SIN_LECTURAS', 'lectura': None, 'diagnosticos': None})
        return Response(_json_safe({
            'lectura': {k: _with_local_dates(row).get(k) for k in (
                'id', 'fecha_registro_utc', 'captura_unix_ms', 'fecha_registro_mexico',
                'fecha_captura_mexico', 'estado_operativo_detalle', 'rpm_vfd',
                'vfd_frecuencia_salida_hz', 'sm1281_modulo_actualspeed_raw',
                'sm1281_cfg_speedsource',
            )},
            'diagnosticos': _diagnosticos(row),
        }))


class DiagnosticosHistoricoView(APIView):
    """Serie ligera de diagnosticos, con los estados originales conservados."""
    def get(self, request):
        try:
            p = _params(request, {'hours': (24, 1, 168, int),
                                  'limit': (200, 1, 1000, int),
                                  'raw': (0, 0, 1, int)})
            rows = db.diagnostics_rows(hours=p['hours'], limit=p['limit'])
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        except Exception as exc:
            return _db_unavailable(exc)
        results = []
        for row in rows:
            item = _with_local_dates(row)
            item['diagnosticos'] = _diagnosticos(row, include_raw=bool(p['raw']))
            if not p['raw']:
                # Campos RAW de monitores, QC y espejo estan en SQL y disponibles
                # en historico/. Evitar respuestas 2x redundantes por defecto.
                item = {k: item.get(k) for k in (
                    'id','fecha_registro_utc','fecha_registro_mexico',
                    'captura_unix_ms','fecha_captura_mexico',
                    'rpm_vfd','vfd_frecuencia_salida_hz','estado_operativo_detalle',
                    'diagnosticos',
                )}
            results.append(item)
        return Response(_json_safe({**p, 'count': len(rows), 'results': results}))


class DiagnosticosResumenView(APIView):
    """Contadores SQL de cobertura y alertas PLC por sensor; no escribe."""
    def get(self, request):
        try:
            p = _params(request, {'hours': (24, 1, 168, int)})
            totals = db.diagnostics_summary(hours=p['hours'])
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        except Exception as exc:
            return _db_unavailable(exc)
        return Response(_json_safe({
            'hours': p['hours'],
            'resumen': totals,
            'nota': 'Contar alarmas PLC no equivale a contar fallas verificadas. '
                    'Los valores NULL historicos no se convierten a cero.',
        }))
